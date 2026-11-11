import json
from argparse import Namespace
from pathlib import Path

import pytest
from pnp_okf.config import DeepSeekConfig, Paths
from pnp_okf.frozen import FrozenStore, write_json
from pnp_okf.models import Segment, SessionExtraction, SessionTranscript


def _transcript(session_id="s1", date="2026-01-01"):
    return SessionTranscript(session_id=session_id, date=date,
        url="https://www.youtube.com/watch?v=vid00001",
        segments=[Segment(start=0, end=1, speaker="A", text="Hallo")])


def _freeze(root, transcripts):
    season = root / "frozen" / "P"
    rows = []
    values = {}
    for t in transcripts:
        value = SessionExtraction(recap=f"Fest {t.session_id}")
        values[t.session_id] = value
        rows.append({"session_id": t.session_id, "dialogue_sha": ""})
        write_json(season / "extract" / f"{t.session_id}.json", value.model_dump(mode="json"))
    write_json(season / "manifest.json", {"schema": 1, "season": "P", "sessions": rows})
    return values


def _state_blob():
    return {"threads": [], "status_changes": [], "attitudes": []}


class _Boom:
    def __getattr__(self, name):
        raise AssertionError("the model was called for a frozen session")


def _cfg():
    return DeepSeekConfig(api_key="x", model="m", base_url="https://example.invalid")


def test_load_cached_extraction_prefers_frozen(tmp_path):
    from pnp_okf.extract import load_cached_extraction
    t = _transcript()
    expected = _freeze(tmp_path, [t])[t.session_id]
    assert load_cached_extraction(tmp_path / "empty-cache", t, _cfg(), frozen=FrozenStore.load(tmp_path)) == expected


def test_frozen_extraction_survives_a_prompt_bump(tmp_path, monkeypatch):
    import pnp_okf.extract as extract
    t = _transcript()
    expected = _freeze(tmp_path, [t])[t.session_id]
    monkeypatch.setattr(extract, "EXTRACT_PROMPT_VERSION", "99")
    assert extract.load_cached_extraction(tmp_path / "cache", t, _cfg(), frozen=FrozenStore.load(tmp_path)) == expected


def test_extract_all_never_calls_the_model_for_frozen(tmp_path, monkeypatch):
    import pnp_okf.cli as cli
    t = _transcript()
    expected = _freeze(tmp_path, [t])[t.session_id]
    def fail(*args, **kwargs):
        raise AssertionError("frozen extraction called the model")
    monkeypatch.setattr(cli, "extract_session", fail)
    paths = Paths(tmp_path, tmp_path, tmp_path / "cache")
    assert cli._extract_all([t], _cfg(), paths, True, frozen=FrozenStore.load(tmp_path))[t.session_id] == expected


def test_thaw_reaches_extract_session(tmp_path, monkeypatch):
    import pnp_okf.cli as cli
    t = _transcript()
    _freeze(tmp_path, [t])
    called = []
    monkeypatch.setattr(cli, "extract_session", lambda *a, **k: called.append(1) or SessionExtraction(recap="new"))
    paths = Paths(tmp_path, tmp_path, tmp_path / "cache")
    cli._extract_all([t], _cfg(), paths, False, frozen=FrozenStore.load(tmp_path, {"P"}))
    assert called == [1]


def test_run_state_applies_frozen_state_without_a_call(tmp_path):
    from pnp_okf.state import run_state
    transcripts = [_transcript("s1", "2026-01-01"), _transcript("s2", "2026-01-02")]
    _freeze(tmp_path, transcripts)
    for t in transcripts:
        write_json(tmp_path / "frozen" / "P" / "state" / f"{t.session_id}.json", _state_blob())
    run = run_state(transcripts, _cfg(), tmp_path / "cache", [], client=_Boom(), frozen=FrozenStore.load(tmp_path))
    assert run.called == 0 and run.cached == 2
    assert set(run.states) == {"s1", "s2"}


def test_frozen_state_cache_miss_does_not_call_model(tmp_path):
    from pnp_okf.frozen import FrozenError
    from pnp_okf.state import run_state
    t = _transcript()
    _freeze(tmp_path, [t])
    with pytest.raises(FrozenError, match="no frozen state or cached state"):
        run_state([t], _cfg(), tmp_path / "empty-cache", [], client=_Boom(),
                  frozen=FrozenStore.load(tmp_path))


def test_estimate_marks_missing_frozen_state_incomplete_without_a_call(tmp_path):
    from pnp_okf.state import run_state
    t = _transcript()
    _freeze(tmp_path, [t])
    run = run_state([t], _cfg(), tmp_path / "empty-cache", [], client=_Boom(),
                    estimate=True, frozen=FrozenStore.load(tmp_path))
    assert run.called == 0
    assert run.uncached_estimate == 0
    assert run.incomplete is True


def test_run_state_frozen_prefix_then_cached_call(tmp_path, monkeypatch):
    import pnp_okf.state as state
    from pnp_okf.state import SessionState, ThreadUpdate, run_state
    transcripts = [_transcript("s1", "2026-01-01"), _transcript("s2", "2026-01-02")]
    _freeze(tmp_path, transcripts[:1])
    first = SessionState(threads=[ThreadUpdate(
        thread_id="threads/ausweg", title="Ausweg", kind="quest",
        status="open", note="n", citation_ts="00:00:00",
    )])
    write_json(tmp_path / "frozen" / "P" / "state" / "s1.json", first.model_dump(mode="json"))
    prompts = []
    def call(client, cfg, transcript, glossary, open_threads):
        prompts.append(open_threads)
        return SessionState()
    monkeypatch.setattr(state, "_call_llm", call)
    run = run_state(transcripts, _cfg(), tmp_path / "cache", [], client=object(), frozen=FrozenStore.load(tmp_path))
    assert run.called == 1
    assert "threads/ausweg" in prompts[0]


def test_thaw_flag_parses():
    from pnp_okf.cli import _build_parser
    assert _build_parser().parse_args(["run", "--thaw", "P,1"]).thaw == "P,1"


def test_paths_default_transcripts_is_the_sibling_checkout(monkeypatch):
    from pathlib import Path
    monkeypatch.delenv("PNP_TRANSCRIPT_DIR", raising=False)
    workspace = next(p for p in Path(__file__).resolve().parents if (p / "pnp-crawl").is_dir())
    assert Paths.resolve().transcript_dir == workspace / "pnp-crawl" / "transcripts_final"


def _prepare_frozen_run(tmp_path, args, extraction):
    from pnp_okf.ingest import load_transcripts

    transcript = load_transcripts(Path(args.transcripts))[0]
    season = tmp_path / "knowledge" / "frozen" / "P"
    write_json(season / "manifest.json", {
        "schema": 1, "season": "P",
        "sessions": [{"session_id": transcript.session_id, "dialogue_sha": ""}],
    })
    write_json(season / "extract" / f"{transcript.session_id}.json", extraction.model_dump(mode="json"))
    return transcript, season


def _offline_args(tmp_path):
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    (transcripts / "2025-03-26_RF_a.json").write_text(json.dumps({
        "video_date": "2025-03-26", "video_url": "https://youtu.be/x",
        "video_title": "Test", "language": "de",
        "segments": [{"start": 1.0, "end": 2.0, "speaker": "GM", "text": "Hallo Welt"}],
    }), encoding="utf-8")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "entity_rules.yaml").write_text("{}\n", encoding="utf-8")
    return Namespace(transcripts=str(transcripts), bundle=str(knowledge / "bundle" / "campaign"),
                     cache=str(tmp_path / "cache"), session=None, limit=None, force=False,
                     reextract=False, workers=1, clean=False, allow_prune=False, allow_rename=False)


def test_estimate_counts_frozen_sessions_as_free(tmp_path, monkeypatch, capsys):
    from pnp_okf.cli import main
    from pnp_okf.models import SessionExtraction

    args = _offline_args(tmp_path)
    _prepare_frozen_run(tmp_path, args, SessionExtraction(recap="Fest"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    assert main(["run", "--estimate", "--transcripts", args.transcripts,
                 "--bundle", args.bundle, "--cache", args.cache]) == 0
    out = capsys.readouterr().out
    assert "frozen:   1 session(s)" in out
    assert "0 to call" in out


def test_estimate_with_thaw_prices_the_season_again(tmp_path, monkeypatch, capsys):
    from pnp_okf.cli import main
    from pnp_okf.models import SessionExtraction

    args = _offline_args(tmp_path)
    _prepare_frozen_run(tmp_path, args, SessionExtraction(recap="Fest"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    assert main(["run", "--estimate", "--thaw", "P", "--transcripts", args.transcripts,
                 "--bundle", args.bundle, "--cache", args.cache]) == 0
    out = capsys.readouterr().out
    assert "1 to call" in out
    assert "frozen:" not in out


def test_frozen_body_skips_synthesis(tmp_path, monkeypatch):
    import pnp_okf.cli as cli
    from pnp_okf.frozen import mention_fingerprint, safe_name
    from pnp_okf.models import EntityMention, EntityType, SessionExtraction
    from pnp_okf.resolve import resolve_entities

    args = _offline_args(tmp_path)
    extraction = SessionExtraction(recap="Fest", entities=[EntityMention(
        name="Orden der Wacht", type=EntityType.FACTION, note="Bewacht das Tor.", citation_ts="00:01:00",
    )])
    transcript, season = _prepare_frozen_run(tmp_path, args, extraction)
    entities = resolve_entities({transcript.session_id: extraction}, {transcript.session_id: transcript},
                                tmp_path / "knowledge" / "entity_registry.yaml")
    entity = next(e for e in entities if e.tier != "brief")
    write_json(season / "synth" / f"{safe_name(entity.concept_id)}.json", {
        "fingerprint": mention_fingerprint(entity), "body": "Der gefrorene Prologtext.",
    })
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    def fail_synthesis(*args, **kwargs):
        raise AssertionError("synthesis called")

    monkeypatch.setattr(cli, "synthesize_entity_body", fail_synthesis)
    assert cli._run_pipeline(args, "2026-09-07T00:00:00Z") == 0
    emitted = tmp_path / "knowledge" / "bundle" / "campaign" / f"{entity.concept_id}.md"
    assert "Der gefrorene Prologtext." in emitted.read_text(encoding="utf-8")
