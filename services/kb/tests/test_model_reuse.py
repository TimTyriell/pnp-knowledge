"""Cross-model cache reuse (D1 phase 2).

A cached result made by any known model answers the same inputs by default;
--strict-model (PNP_STRICT_MODEL=1) restores the configured-model-only lookup.
"""

from __future__ import annotations

import json
from pathlib import Path

import pnp_okf.cli as cli
import pytest
from pnp_okf.cache_gc import cache_entries, sweep
from pnp_okf.config import DEFAULT_LIGHT_MODEL, DEFAULT_MODEL, DeepSeekConfig
from pnp_okf.extract import (
    _cache_key,
    _cache_path,
    _store_cache,
    extract_session,
    find_cached_extraction,
)
from pnp_okf.handoff import AgentPending
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import CanonicalEntity, EntityType, MentionRef, Segment, SessionExtraction, SessionTranscript
from pnp_okf.reuse import candidate_models, remember_model
from pnp_okf.state import _cache_path as state_path
from pnp_okf.state import render_glossary, run_state, state_cache_key
from pnp_okf.synthesize import _cache_key as synth_key
from pnp_okf.synthesize import _cache_path as synth_path
from pnp_okf.synthesize import synthesize_entity_body

AGENT = "agent:claude:x"
STEPS = ("extract", "deep", "standard", "state", "dedup")
GLOSS = [{"type": "NPC", "name": "Xenia", "aliases": []}]


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    for var in [f"PNP_MODEL_{s.upper()}" for s in STEPS] + [
        "DEEPSEEK_MODEL", "DEEPSEEK_LIGHT_MODEL", "DEEPSEEK_EXTRACT_MODEL",
        "DEEPSEEK_STATE_MODEL", "PNP_STRICT_MODEL",
    ]:
        monkeypatch.setenv(var, "placeholder")
        monkeypatch.delenv(var)
    monkeypatch.setenv("PNP_AGENT_DIR", str(tmp_path / "agent"))
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")


def _cfg(model: str = AGENT) -> DeepSeekConfig:
    return DeepSeekConfig(api_key="x", model=model, base_url="https://example.invalid", step="extract")


def _transcript() -> SessionTranscript:
    segs = [Segment(start=i, end=i + 1, speaker="GM", text=f"Satz {i}") for i in range(3)]
    return SessionTranscript(session_id="2026-01-01_a", date="2026-01-01",
                             url="https://example.invalid/a", segments=segs)


def _entity() -> CanonicalEntity:
    return CanonicalEntity(
        concept_id="characters/lindo_laut", type=EntityType.CHARACTER, canonical_name="Lindo Laut",
        mentions=[MentionRef(session_id="s1", date="2026-01-01", url="https://example.invalid/a",
                             citation_ts="00:01:00", note="Ein Barde.")],
    )


def _seed_extraction(cache: Path, t: SessionTranscript, model: str, recap: str) -> None:
    key = _cache_key(t, _cfg(model))
    _store_cache(_cache_path(cache, t, key), key, SessionExtraction(recap=recap, entities=[]))


# --- candidates and models.txt ----------------------------------------------


def test_candidates_follow_the_configured_model_then_the_steps_then_the_defaults(tmp_path):
    cfg = DeepSeekConfig(api_key="", model="m-deep", base_url="", extract_model="m-ext",
                         light_model="m-light", state_model="m-state", dedup_model="m-dedup")
    (tmp_path / "models.txt").write_text("old-model\n\nm-dedup\n", encoding="utf-8")
    assert candidate_models(cfg, tmp_path) == [
        "m-deep", "m-ext", "m-light", "m-state", "m-dedup",
        DEFAULT_MODEL, DEFAULT_LIGHT_MODEL, "old-model",
    ]


def test_strict_model_env_restricts_candidates_to_the_configured_model(tmp_path, monkeypatch):
    remember_model(tmp_path, "old-model")
    monkeypatch.setenv("PNP_STRICT_MODEL", "1")
    assert candidate_models(_cfg(), tmp_path) == [AGENT]


def test_remember_model_appends_each_model_once(tmp_path):
    cache = tmp_path / "cache"
    remember_model(cache, "a")
    remember_model(cache, "b")
    remember_model(cache, "a")
    assert (cache / "models.txt").read_text(encoding="utf-8").splitlines() == ["a", "b"]


def test_models_file_is_never_swept(tmp_path):
    cache = tmp_path / "cache"
    _seed_extraction(cache, _transcript(), DEFAULT_MODEL, "alt")
    remember_model(cache, DEFAULT_MODEL)
    assert "models.txt" not in cache_entries(cache)
    # allow_mass: with one entry the whole kind is due, which the guard would hold back.
    sweep(cache, set(), "s1", allow_mass=True)
    sweep(cache, set(), "s9", allow_mass=True)  # two tags later the stale extraction is deleted
    assert not any(p.startswith("extract/") for p in cache_entries(cache))
    assert (cache / "models.txt").exists()


# --- extraction --------------------------------------------------------------


def test_extraction_under_another_model_is_reused_without_a_packet(tmp_path):
    t, cache = _transcript(), tmp_path / "cache"
    _seed_extraction(cache, t, DEFAULT_MODEL, "unter pro")

    assert extract_session(t, _cfg(), cache).recap == "unter pro"
    assert not (tmp_path / "agent").exists()


def test_strict_model_does_not_reuse_another_models_extraction(tmp_path, monkeypatch):
    monkeypatch.setenv("PNP_STRICT_MODEL", "1")
    t, cache = _transcript(), tmp_path / "cache"
    _seed_extraction(cache, t, DEFAULT_MODEL, "unter pro")

    with pytest.raises(AgentPending):
        extract_session(t, _cfg(), cache)


def test_the_configured_models_entry_wins_over_another_models(tmp_path):
    t, cache = _transcript(), tmp_path / "cache"
    _seed_extraction(cache, t, DEFAULT_MODEL, "unter pro")
    _seed_extraction(cache, t, AGENT, "unter agent")

    assert extract_session(t, _cfg(), cache).recap == "unter agent"


def test_find_reports_the_path_it_hit_so_gc_can_keep_it(tmp_path):
    t, cache = _transcript(), tmp_path / "cache"
    _seed_extraction(cache, t, DEFAULT_MODEL, "unter pro")

    ex, path = find_cached_extraction(cache, t, _cfg())
    assert ex.recap == "unter pro"
    assert path == _cache_path(cache, t, _cache_key(t, _cfg(DEFAULT_MODEL)))


# --- synthesis ---------------------------------------------------------------


def _seed_body(cache: Path, model: str, body: str) -> None:
    e = _entity()
    key = synth_key(e, _cfg(model), "", "", "")
    path = synth_path(cache, e, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"_key": key, "body": body}), encoding="utf-8")


def test_synthesis_body_under_another_model_is_reused(tmp_path):
    cache = tmp_path / "cache"
    _seed_body(cache, DEFAULT_MODEL, "# Pro")

    assert synthesize_entity_body(_entity(), _cfg(), cache) == "# Pro"
    assert not (tmp_path / "agent").exists()


def test_strict_model_does_not_reuse_another_models_body(tmp_path, monkeypatch):
    monkeypatch.setenv("PNP_STRICT_MODEL", "1")
    cache = tmp_path / "cache"
    _seed_body(cache, DEFAULT_MODEL, "# Pro")

    with pytest.raises(AgentPending):
        synthesize_entity_body(_entity(), _cfg(), cache)


# --- state -------------------------------------------------------------------


def _seed_state(cache: Path, t: SessionTranscript, model: str) -> None:
    key = state_cache_key(t, _cfg(model), render_glossary(GLOSS), "(keine offenen Fäden)")
    path = state_path(cache, t, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"_key": key, "state": {
        "threads": [], "status_changes": [], "attitudes": []}}), encoding="utf-8")


def test_state_under_another_model_is_reused(tmp_path):
    t, cache = _transcript(), tmp_path / "cache"
    _seed_state(cache, t, DEFAULT_MODEL)

    run = run_state([t], _cfg(), cache, GLOSS)
    assert (run.cached, run.called) == (1, 0)
    assert not (tmp_path / "agent").exists()


def test_strict_model_does_not_reuse_another_models_state(tmp_path, monkeypatch):
    monkeypatch.setenv("PNP_STRICT_MODEL", "1")
    t, cache = _transcript(), tmp_path / "cache"
    _seed_state(cache, t, DEFAULT_MODEL)

    with pytest.raises(AgentPending):
        run_state([t], _cfg(), cache, GLOSS)


# --- estimate ----------------------------------------------------------------


def test_estimate_reports_reused_extractions_separately(tmp_path, capsys):
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    (tdir / "2026-01-01_a.json").write_text(json.dumps({
        "video_date": "2026-01-01", "video_url": "https://youtu.be/x",
        "segments": [{"start": 1.0, "end": 2.0, "speaker": "GM", "text": "Hallo Welt"}],
    }), encoding="utf-8")
    (t,) = load_transcripts(tdir)
    cache = tmp_path / "cache"
    _seed_extraction(cache, t, DEFAULT_MODEL, "unter pro")

    rc = cli.main(["run", "--estimate", "--model", f"extract={AGENT}",
                   "--transcripts", str(tdir),
                   "--bundle", str(tmp_path / "knowledge" / "bundle" / "c"),
                   "--cache", str(cache)])

    assert rc == 0
    assert f"0 cached, 1 reused ({DEFAULT_MODEL}: 1), 0 to call" in capsys.readouterr().out
