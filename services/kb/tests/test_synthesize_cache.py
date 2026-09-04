"""The synthesis cache key must track every input that changes the output.

I-002 added a fourth grounding input (``secondary``, context.py) alongside
sources/excerpts. A cache key that ignores it would serve a stale body after
a secondary-only change — no new model call, no error, just wrong content
sitting there looking like a cache hit.
"""

from __future__ import annotations

from pnp_okf.config import DeepSeekConfig
from pnp_okf.models import CanonicalEntity, EntityType
from pnp_okf.synthesize import _cache_key


def _entity() -> CanonicalEntity:
    return CanonicalEntity(
        concept_id="characters/held",
        type=EntityType.CHARACTER,
        canonical_name="Held",
    )


def _cfg() -> DeepSeekConfig:
    return DeepSeekConfig(base_url="http://x", model="test-model", api_key="x")


def test_cache_key_tracks_secondary_sources():
    ent, cfg = _entity(), _cfg()
    base = _cache_key(ent, cfg, sources="", excerpts="", secondary="")
    changed = _cache_key(ent, cfg, sources="", excerpts="", secondary="Nyruk ist ein Eisbär.")
    assert base != changed


def test_cache_key_stable_when_secondary_unchanged():
    ent, cfg = _entity(), _cfg()
    a = _cache_key(ent, cfg, sources="s", excerpts="e", secondary="sec")
    b = _cache_key(ent, cfg, sources="s", excerpts="e", secondary="sec")
    assert a == b


def test_cache_key_defaults_secondary_to_empty():
    ent, cfg = _entity(), _cfg()
    assert _cache_key(ent, cfg, "s", "e") == _cache_key(ent, cfg, "s", "e", "")


if __name__ == "__main__":
    test_cache_key_tracks_secondary_sources()
    test_cache_key_stable_when_secondary_unchanged()
    test_cache_key_defaults_secondary_to_empty()
    print("all checks passed")
