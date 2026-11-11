from __future__ import annotations

import argparse
import json
from pathlib import Path

import pnp_okf.cli as cli
import pnp_okf.extract as extract_mod
import pytest
from pnp_okf.cache_gc import cache_entries, live_entries
from pnp_okf.config import DeepSeekConfig, Paths
from pnp_okf.extract import _cache_key, _cache_path, _store_cache
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import EntityMention, EntityType, SessionExtraction, SessionTranscript


def _write_transcript_json(path: Path, date: str) -> None:
    path.write_text(
        json.dumps(
            {
                "video_date": date,
                "video_url": "https://youtu.be/x",
                "video_title": "Test",
                "language": "de",
                "segments": [{"start": 1.0, "end": 2.0, "speaker": "GM", "text": "Hallo Welt"}],
            }
        ),
        encoding="utf-8",
    )


def _offline_run_args(tmp_path: Path) -> argparse.Namespace:
    """A ``pnp run`` argument set over one transcript, laid out like the real
    repo (``knowledge/bundle/<name>``) so ``Paths`` derives the registry and
    rules path next to the bundle, not inside it."""

    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir()
    _write_transcript_json(transcripts_dir / "2025-03-26_RF_a.json", "2025-03-26")

    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "entity_rules.yaml").write_text("{}\n", encoding="utf-8")

    return argparse.Namespace(
        transcripts=str(transcripts_dir),
        bundle=str(knowledge_dir / "bundle" / "campaign"),
        cache=str(tmp_path / "cache"),
        session=None,
        limit=None,
        force=False,
        reextract=False,
        workers=1,
        clean=False,
        allow_prune=False,
        allow_rename=False,
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    for name in (
        "DEEPSEEK_MODEL",
        "DEEPSEEK_EXTRACT_MODEL",
        "PNP_EXTRACT_FREEZE_BEFORE",
        "PNP_EXTRACT_FREEZE_VERSION",
        "PNP_CACHE_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def _setup(tmp_path: Path, second: bool = False) -> tuple[argparse.Namespace, Paths, list]:
    args = _offline_run_args(tmp_path)
    if second:
        _write_transcript_json(
            Path(args.transcripts) / "2025-04-02_RF_b.json", "2025-04-02"
        )
    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    return args, paths, load_transcripts(paths.transcript_dir)


def _seed(cache: Path, transcript: SessionTranscript, extraction: SessionExtraction) -> None:
    """Put one session in the cache the way a real run would leave it."""
    cfg = DeepSeekConfig.from_env().for_tier("extract")
    key = _cache_key(transcript, cfg)
    _store_cache(_cache_path(cache, transcript, key), key, extraction)


def _by_id(transcripts: list[SessionTranscript], session_id: str) -> SessionTranscript:
    (t,) = [t for t in transcripts if t.session_id == session_id]
    return t


def _npc_extraction(name: str = "Wache Hans") -> SessionExtraction:
    return SessionExtraction(
        recap="Die Gruppe trifft einen NPC.",
        entities=[
            EntityMention(
                name=name,
                type=EntityType.NPC,
                note="Ein Wächter am Tor.",
                citation_ts="00:01:00",
            )
        ],
    )


def _empty_extraction() -> SessionExtraction:
    return SessionExtraction(recap="Eine Sitzung.", entities=[])


def test_live_set_matches_what_a_run_writes(tmp_path: Path, env, monkeypatch):
    args, paths, transcripts = _setup(tmp_path, second=True)
    for t in transcripts:
        _seed(paths.cache_dir, t, _npc_extraction())

    monkeypatch.setattr("pnp_okf.synthesize.build_client", lambda cfg: object())
    monkeypatch.setattr("pnp_okf.synthesize._call_llm", lambda *a, **k: "Text.")
    assert cli._run_pipeline(args, "2026-11-11T00:00:00Z") == 0

    live = live_entries(paths, transcripts)
    assert live is not None
    assert live == cache_entries(paths.cache_dir)
    assert any(p.startswith("synth/") for p in live), "NPC stayed brief; no synth file written"


def test_live_set_keeps_entries_reused_from_another_model(tmp_path: Path, env, monkeypatch):
    # The extract model moved on, but the old model's entries still answer the
    # same inputs by default, so they must stay live or the next sweep deletes them.
    _, paths, transcripts = _setup(tmp_path, second=True)
    for t in transcripts:
        _seed(paths.cache_dir, t, _empty_extraction())
    monkeypatch.setenv("PNP_MODEL_EXTRACT", "agent:claude:claude-opus-5-5")

    live = live_entries(paths, transcripts)
    assert live is not None
    assert live == cache_entries(paths.cache_dir)


def test_missing_extraction_returns_none(tmp_path: Path, env):
    _, paths, transcripts = _setup(tmp_path, second=True)
    _seed(paths.cache_dir, _by_id(transcripts, "2025-03-26_RF_a"), _empty_extraction())

    assert live_entries(paths, transcripts) is None


def test_orphan_session_dir_returns_none(tmp_path: Path, env):
    _, paths, transcripts = _setup(tmp_path)
    _seed(paths.cache_dir, transcripts[0], _empty_extraction())
    (paths.cache_dir / "extract" / "2020-01-01_X_y").mkdir(parents=True)

    assert live_entries(paths, transcripts) is None


def test_no_transcripts_returns_none(tmp_path: Path, env):
    _, paths, _ = _setup(tmp_path)

    assert live_entries(paths, []) is None


def test_prompt_version_change_makes_old_entry_stale(tmp_path: Path, env, monkeypatch):
    _, paths, transcripts = _setup(tmp_path)
    t = transcripts[0]
    _seed(paths.cache_dir, t, _empty_extraction())
    old = cache_entries(paths.cache_dir)

    monkeypatch.setattr(extract_mod, "_frozen_prompt_version", lambda t: "999")
    _seed(paths.cache_dir, t, _empty_extraction())

    live = live_entries(paths, transcripts)
    assert live is not None
    assert len(live) == 1
    assert old - live == old
    assert old <= cache_entries(paths.cache_dir)


def test_model_change_makes_old_entry_stale(tmp_path: Path, env, monkeypatch):
    _, paths, transcripts = _setup(tmp_path)
    _seed(paths.cache_dir, transcripts[0], _empty_extraction())

    monkeypatch.setenv("DEEPSEEK_MODEL", "some-other-model")
    monkeypatch.setenv("PNP_STRICT_MODEL", "1")  # reuse is on by default; see the reuse test below

    # The new model's key has no cached extraction, so the set is unknown rather
    # than "everything under the old model is stale"; a wrong env must not wipe the cache.
    assert live_entries(paths, transcripts) is None


def test_run_entities_are_used_when_given(tmp_path: Path, env):
    _, paths, transcripts = _setup(tmp_path)
    _seed(paths.cache_dir, transcripts[0], _empty_extraction())

    live = live_entries(paths, transcripts, entities=[])
    assert live is not None
    assert live
    assert all(p.startswith("extract/") for p in live)


def test_frozen_session_entries_are_stale(tmp_path: Path, env):
    _, paths, transcripts = _setup(tmp_path, second=True)
    frozen_t, live_t = transcripts[0], transcripts[1]
    _seed(paths.cache_dir, live_t, _empty_extraction())
    _seed(paths.cache_dir, frozen_t, _empty_extraction())

    # Minimal freeze: manifest + extract/<session_id>.json, the shape FrozenStore reads.
    season = paths.knowledge_root / "frozen" / "P"
    (season / "extract").mkdir(parents=True)
    (season / "manifest.json").write_text(
        json.dumps({"schema": 1, "season": "P", "sessions": [{"session_id": frozen_t.session_id}]}),
        encoding="utf-8",
    )
    (season / "extract" / f"{frozen_t.session_id}.json").write_text(
        _empty_extraction().model_dump_json(), encoding="utf-8"
    )

    live = live_entries(paths, transcripts)
    assert live is not None
    frozen_path = _cache_path(
        paths.cache_dir, frozen_t, _cache_key(frozen_t, DeepSeekConfig.from_env().for_tier("extract"))
    ).relative_to(paths.cache_dir).as_posix()
    assert frozen_path not in live
    assert cache_entries(paths.cache_dir) - live  # the frozen session's file is stale

    # Without any cache entry for the frozen session, the set is still known.
    (paths.cache_dir / frozen_path).unlink()
    live = live_entries(paths, transcripts)
    assert live is not None
    assert len(live) == 1
