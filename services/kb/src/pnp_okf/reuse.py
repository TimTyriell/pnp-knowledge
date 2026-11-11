"""Which models' cached results may answer a lookup (D1 phase 2).

A cache key contains the model, so switching models used to re-buy every
result. Lookups now try each model that has ever written to this cache and
take the first hit; stores always use the configured model. --strict-model
(PNP_STRICT_MODEL=1) restores the configured-model-only lookup.
"""

from __future__ import annotations

import os
from pathlib import Path

from pnp_okf.config import DEFAULT_LIGHT_MODEL, DEFAULT_MODEL, DeepSeekConfig

MODELS_FILE = "models.txt"


def _listed(cache_dir: Path) -> list[str]:
    path = cache_dir / MODELS_FILE
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def candidate_models(cfg: DeepSeekConfig, cache_dir: Path) -> list[str]:
    """Models to try for a lookup, the configured one first."""
    if os.environ.get("PNP_STRICT_MODEL") == "1":
        return [cfg.model]
    # models.txt covers models that have since left the config: an old
    # extract model's results must still be found after the switch.
    names = [cfg.model, *cfg.step_models().values(), DEFAULT_MODEL, DEFAULT_LIGHT_MODEL,
             *_listed(cache_dir)]
    return list(dict.fromkeys(n for n in names if n))


def remember_model(cache_dir: Path, model: str) -> None:
    """Record that ``model`` wrote to this cache, so later lookups try it."""
    known = _listed(cache_dir)
    if model in known:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / MODELS_FILE).write_text("".join(f"{m}\n" for m in [*known, model]), encoding="utf-8")
