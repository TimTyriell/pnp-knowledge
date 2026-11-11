"""`pnp agent status`: check the agent queue without calling a model (D1 phase 4).

Each answered packet is validated with the same check its step's real code
path applies, so a packet that passes here is one the next run can serve. A
failing answer is moved to ``<step>/rejected/`` with the reason beside it: the
packet is open again and the failure is visible instead of silently retried.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pnp_okf.dedup import _MergeResponse
from pnp_okf.extract import _extract_json_block
from pnp_okf.handoff import agent_dir
from pnp_okf.models import SessionExtraction
from pnp_okf.state import SessionState

STATUSES = ("pending", "answered", "rejected", "unreadable")


def _check(step: str, text: str) -> None:
    """Raise ValueError if the answer would fail the step's real code path.

    Each branch mirrors one caller exactly: extraction accepts a fenced block
    and rejects a recap with no entities; state and dedup parse the raw text,
    so a fence there fails the run and must fail here too; synthesis needs
    only non-empty text.
    """
    if step == "extract":
        parsed = SessionExtraction.model_validate_json(_extract_json_block(text))
        if parsed.recap.strip() and not parsed.entities:
            raise ValueError("extraction returned a recap but zero entities")
    elif step == "state":
        SessionState.model_validate_json(text)
    elif step == "dedup":
        _MergeResponse.model_validate_json(text)
    elif not text.strip():
        raise ValueError("empty response")


def _model_warning(base: Path, pid: str, label: str) -> str | None:
    """Record-only: the worker's self-report is not trusted, so this never rejects."""
    meta_path = base / f"{pid}.meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"{meta_path.name} is not valid JSON"
    want = meta.get("model") if isinstance(meta, dict) else None
    if want and not label.endswith(f":{want}"):
        return f"worker reports model {want!r}, but the packet asks for {label!r}"
    return None


def _packet(req: Path) -> dict:
    data = json.loads(req.read_text(encoding="utf-8"))
    step, pid, label = data["step"], data["id"], data.get("model", "")
    base = req.parent
    ext = "json" if data.get("response_kind") == "json" else "md"
    resp = base / f"{pid}.response.{ext}"
    row = {"id": pid, "step": step, "model": label, "status": "pending",
           "request": str(req), "response": None}
    warning = _model_warning(base, pid, label)
    if warning:
        row["warning"] = warning
    if not resp.exists():
        return row
    try:
        _check(step, resp.read_text(encoding="utf-8"))
    except ValueError as exc:  # pydantic's ValidationError and JSONDecodeError both are
        rejected = base / "rejected"
        rejected.mkdir(parents=True, exist_ok=True)
        # replace, not rename: a second rejection of the same packet overwrites the first.
        resp.replace(rejected / resp.name)
        (rejected / f"{pid}.error.txt").write_text(f"{exc}\n", encoding="utf-8")
        row.update(status="rejected", error=str(exc))
        return row
    row.update(status="answered", response=str(resp))
    return row


def scan(root: Path | None = None) -> dict:
    """Walk ``<root>/<step>/*.request.json`` and report every packet.

    Rejections happen here, as a side effect; the caller decides the exit code
    from ``counts["rejected"]``.
    """
    root = agent_dir() if root is None else root
    packets: list[dict] = []
    for req in sorted(root.glob("*/*.request.json")):
        try:
            packets.append(_packet(req))
        except (OSError, ValueError, KeyError) as exc:
            # A request we did not write, or one damaged on disk. Left alone:
            # it is reported, not moved, because nothing here can answer it.
            packets.append({"id": req.name.split(".")[0], "step": req.parent.name,
                            "model": "", "status": "unreadable", "request": str(req),
                            "response": None, "error": str(exc)})
    counts = Counter(p["status"] for p in packets)
    return {
        "dir": str(root),
        "packets": packets,
        "counts": {s: counts.get(s, 0) for s in STATUSES},
    }


def render(report: dict) -> str:
    """Human text: one block per step and model, then the packets someone must act on."""
    lines = [f"agent queue: {report['dir']}"]
    if not report["packets"]:
        lines.append("no packets")
    groups: dict[tuple[str, str], list[dict]] = {}
    for p in report["packets"]:
        groups.setdefault((p["step"], p["model"] or "-"), []).append(p)
    for (step, model), rows in sorted(groups.items()):
        n = Counter(r["status"] for r in rows)
        lines.append(f"{step}  {model}  pending {n['pending']}  answered {n['answered']}"
                     f"  rejected {n['rejected']}")
        for r in rows:
            if r["status"] == "answered" and "warning" not in r:
                continue
            detail = r.get("error", "").splitlines()[0] if r.get("error") else ""
            lines.append(f"  {r['status']:<10} {r['id']}  {detail}".rstrip())
            if r.get("warning"):
                lines.append(f"  warning    {r['id']}  {r['warning']}")
    c = report["counts"]
    lines.append(f"total: pending {c['pending']}, answered {c['answered']}, "
                 f"rejected {c['rejected']}, unreadable {c['unreadable']}")
    return "\n".join(lines)
