"""Token accounting for LLM calls.

``config.for_tier`` routes deep-tier synthesis to the strong model and
everything else to the cheap one, on the stated reasoning that "the strong
model only where it pays". Nothing measured whether it does: the OpenAI
response carries a ``usage`` block on every call and every call site discarded
it, so the number of calls per model, and their token cost, was unknown.

This module is the accounting. It is deliberately small — a process-wide
counter, not a metrics framework. It records what the API already tells us and
nothing else.

**Cost is opt-in and never guessed.** Token counts are facts reported by the
API; prices are not, they change, and a plausible-looking wrong number in a
status file is worse than no number. Set the per-million-token prices via
environment variables to have cost computed:

    PNP_PRICE_IN_<MODEL>   input price per 1M tokens
    PNP_PRICE_OUT_<MODEL>  output price per 1M tokens

where ``<MODEL>`` is the model name uppercased with non-alphanumerics replaced
by underscores (``deepseek-v4-pro`` -> ``DEEPSEEK_V4_PRO``). Currency is
whatever the prices are given in; ``PNP_PRICE_CURRENCY`` labels it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class ModelUsage:
    """Per-model call and token totals."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _env_key(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", model).upper()


def _price(kind: str, model: str) -> float | None:
    raw = os.environ.get(f"PNP_PRICE_{kind}_{_env_key(model)}", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@dataclass
class UsageLedger:
    """Process-wide LLM usage totals, keyed by model name."""

    by_model: dict[str, ModelUsage] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(self, model: str | None, usage: object | None) -> None:
        """Add one completion's usage. Tolerates a missing usage block.

        A cached or stubbed response has no ``usage``; that is not an error and
        must not break a pipeline run, so this never raises.
        """

        if not model or usage is None:
            return
        prompt = getattr(usage, "prompt_tokens", None) or 0
        completion = getattr(usage, "completion_tokens", None) or 0
        with self._lock:
            entry = self.by_model.setdefault(model, ModelUsage())
            entry.calls += 1
            entry.prompt_tokens += int(prompt)
            entry.completion_tokens += int(completion)

    def reset(self) -> None:
        with self._lock:
            self.by_model.clear()

    def snapshot(self) -> dict:
        """Serializable totals for ``state/last_run.json``.

        Cost keys are present only for models whose prices are configured, so a
        consumer can distinguish "free" from "not priced".
        """

        with self._lock:
            models = {m: ModelUsage(u.calls, u.prompt_tokens, u.completion_tokens)
                      for m, u in self.by_model.items()}

        out: dict = {
            "llm_calls": sum(u.calls for u in models.values()),
            "tokens": {
                "prompt": sum(u.prompt_tokens for u in models.values()),
                "completion": sum(u.completion_tokens for u in models.values()),
            },
            "by_model": {},
        }
        total_cost = 0.0
        priced_any = False
        for model, u in sorted(models.items()):
            entry: dict = {
                "calls": u.calls,
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
            }
            p_in, p_out = _price("IN", model), _price("OUT", model)
            if p_in is not None and p_out is not None:
                cost = (u.prompt_tokens * p_in + u.completion_tokens * p_out) / 1_000_000
                entry["cost"] = round(cost, 6)
                total_cost += cost
                priced_any = True
            out["by_model"][model] = entry

        if priced_any:
            out["cost"] = round(total_cost, 6)
            out["cost_currency"] = os.environ.get("PNP_PRICE_CURRENCY", "USD").strip() or "USD"
        return out


LEDGER = UsageLedger()
