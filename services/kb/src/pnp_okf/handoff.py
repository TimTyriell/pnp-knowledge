"""Agent mode: answer LLM requests from a Claude/Codex agent instead of the API.

A step whose model is an ``agent:<host>:<model>`` label gets a HandoffClient
in place of the OpenAI one. On a cache miss it writes the exact request to
``<agent_dir>/<step>/<id>.request.json`` and raises :class:`AgentPending`; a
worker answers by writing ``<id>.response.json`` (or ``.md``) next to it, and
the next run serves that text as the completion. Everything downstream (parse,
validate, cache) is the unchanged API code path.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from pnp_okf.config import DeepSeekConfig


class AgentPending(RuntimeError):
    """A request has no response yet. Not retryable: it propagates at once."""

    def __init__(self, step: str, packet_id: str, path: Path, model: str = "") -> None:
        super().__init__(f"agent packet {packet_id} ({step}) awaits a response: {path}")
        self.step = step
        self.packet_id = packet_id
        self.path = path
        self.model = model


class AgentResponseInvalid(RuntimeError):
    """A response was served and then failed validation; the retry was refused."""


class AgentWorkPending(RuntimeError):
    """Every packet this run could not answer, collected before anything is written."""

    def __init__(self, pending: list[AgentPending]) -> None:
        self.pending = list(pending)
        super().__init__(f"{len(self.pending)} agent packet(s) pending")


# Served responses per (step, model), reported in last_run.json.
AGENT_CALLS: Counter[tuple[str, str]] = Counter()

# Guards the served-set check and the file writes; requests are cheap, so one
# lock across all clients is simpler than one per client.
# ponytail: global lock, per-packet locks if throughput ever matters
_LOCK = threading.Lock()


def agent_dir() -> Path:
    """The request/response queue. Holds transcript text, so it stays gitignored."""
    env = os.environ.get("PNP_AGENT_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return Path(os.environ.get("PNP_STATE_DIR", "./state")) / "agent"


def packet_id(model: str, messages: list) -> str:
    """Identity of one request: a changed prompt or context is a new packet."""
    blob = json.dumps({"model": model, "messages": messages}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class HandoffClient:
    """Stands in for the OpenAI client; answers from the agent queue."""

    def __init__(self, cfg: DeepSeekConfig) -> None:
        self._cfg = cfg
        # Per client, not per process: a retry reuses the client, so a second
        # request for a served packet means the served answer failed validation.
        self._served: set[str] = set()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        # Refused on purpose: extraction's structured-outputs probe catches this
        # and falls back to the JSON-prompt path, which is the one agents answer.
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=self._parse))
        )

    def _parse(self, **kw):
        raise NotImplementedError(
            "agent mode uses the JSON-prompt path; structured outputs are not offered"
        )

    def _create(self, **kw):
        model = kw["model"]
        messages = kw["messages"]
        is_json = bool(kw.get("response_format"))
        pid = packet_id(model, messages)
        step = self._cfg.step or "unknown"
        base = agent_dir() / step
        resp = base / f"{pid}.response.{'json' if is_json else 'md'}"

        with _LOCK:
            if resp.exists():
                if pid in self._served:
                    rejected = base / "rejected"
                    rejected.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(resp), str(rejected / resp.name))
                    raise AgentResponseInvalid(
                        f"{step} packet {pid}: the agent's response failed validation and "
                        f"was moved to {rejected}. Run `pnp agent status` to see why."
                    )
                self._served.add(pid)
                AGENT_CALLS[(step, model)] += 1
                text = resp.read_text(encoding="utf-8")
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=text, parsed=None))],
                    usage=None,
                )

            req = base / f"{pid}.request.json"
            if not req.exists():
                base.mkdir(parents=True, exist_ok=True)
                created = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
                record = {
                    "id": pid,
                    "step": step,
                    "model": model,
                    "response_kind": "json" if is_json else "markdown",
                    "temperature": kw.get("temperature"),
                    "messages": messages,
                    "created": created,
                }
                req.write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            raise AgentPending(step, pid, req, model)
