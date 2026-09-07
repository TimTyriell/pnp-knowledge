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


def test_a_second_key_does_not_destroy_the_first(tmp_path):
    """Both caches must be content-addressed, not overwritten in place.

    The cache key includes PROMPT_VERSION and the model, but the cache *path*
    did not -- so bumping either overwrote the only copy of ~$6.50 of paid-for
    LLM output, and reverting the change cost a second full rebuild. Keeping
    each key at its own path makes an experiment reversible for nothing.
    """

    import json

    from pnp_okf.synthesize import _cache_path

    ent = _entity()
    a, b = "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"
    path_a, path_b = _cache_path(tmp_path, ent, a), _cache_path(tmp_path, ent, b)

    assert path_a != path_b, "a different key must not reuse the same file"

    for path, key, body in ((path_a, a, "body under A"), (path_b, b, "body under B")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"_key": key, "body": body}), encoding="utf-8")

    assert json.loads(path_a.read_text(encoding="utf-8"))["body"] == "body under A"
    assert json.loads(path_b.read_text(encoding="utf-8"))["body"] == "body under B"


def test_extract_cache_survives_a_model_switch(tmp_path):
    """Same invariant on the extraction side, where the money actually is."""

    from pnp_okf.extract import _load_cached, _store_cache
    from pnp_okf.extract import _cache_path as extract_path
    from pnp_okf.models import SessionExtraction, SessionTranscript

    transcript = SessionTranscript(
        session_id="2026-01-01_X_abc",
        date="2026-01-01",
        url="https://youtu.be/x",
        title="T",
        segments=[],
    )
    pro = SessionExtraction(recap="unter pro", entities=[])
    flash = SessionExtraction(recap="unter flash", entities=[])

    _store_cache(extract_path(tmp_path, transcript, "pro_key_00000000"), "pro_key_00000000", pro)
    _store_cache(extract_path(tmp_path, transcript, "fla_key_00000000"), "fla_key_00000000", flash)

    back = _load_cached(extract_path(tmp_path, transcript, "pro_key_00000000"), "pro_key_00000000")
    assert back is not None and back.recap == "unter pro", (
        "switching model and switching back must not cost a re-extraction"
    )
