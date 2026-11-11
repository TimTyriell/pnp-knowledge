import json

import pytest
from pnp_okf.cli import main
from pnp_okf.config import DeepSeekConfig
from pnp_okf.extract import _cache_key, _cache_path, _store_cache
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import EntityMention, EntityType, SessionExtraction
from pnp_okf.prompts import EXTRACT_PROMPT_VERSION


@pytest.fixture
def freeze_inputs(tmp_path, monkeypatch):
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    for date, video_id, text in (
        ("2025-03-26", "vid00001", "Prolog"),
        ("2026-09-06", "vid00002", "Staffel eins"),
    ):
        (transcripts / f"{date}_RF_{video_id}.json").write_text(json.dumps({
            "video_date": date,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "video_title": text,
            "language": "de",
            "segments": [{"start": 1.0, "end": 2.0, "speaker": "GM", "text": text}],
        }), encoding="utf-8")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "episodes.yaml").write_text(
        'seasons:\n  "P": {label: Prolog}\n  "1": {label: Staffel 1}\n'
        'episodes:\n  - {video_id: vid00001, id: P-01, season: "P"}\n'
        '  - {video_id: vid00002, id: S1-01, season: "1"}\n', encoding="utf-8")
    (knowledge / "entity_rules.yaml").write_text("{}\n", encoding="utf-8")
    cache = tmp_path / "cache"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    cfg = DeepSeekConfig.from_env().for_tier("extract")
    transcripts_loaded = load_transcripts(transcripts)
    p_session, s1_session = transcripts_loaded
    p_extraction = SessionExtraction(recap="Cache recap", entities=[EntityMention(
        name="Orden der Wacht", type=EntityType.FACTION, note="Bewacht das Tor.", citation_ts="00:00:01",
    )])
    key = _cache_key(p_session, cfg)
    _store_cache(_cache_path(cache, p_session, key), key, p_extraction)
    common = ["--transcripts", str(transcripts), "--bundle", str(knowledge / "bundle" / "camp"),
              "--cache", str(cache)]
    return tmp_path, common, p_session, s1_session, p_extraction


def test_freeze_writes_manifest_and_extractions(freeze_inputs):
    root, args, p_session, s1_session, _ = freeze_inputs
    assert main(["freeze", "P", *args]) == 0
    season = root / "knowledge" / "frozen" / "P"
    manifest = json.loads((season / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["sessions"] == 1
    assert manifest["prompt_versions"]["extract"] == EXTRACT_PROMPT_VERSION
    assert (season / "extract" / f"{p_session.session_id}.json").is_file()
    assert not (season / "extract" / f"{s1_session.session_id}.json").exists()


def test_freeze_refuses_when_a_session_is_uncached(freeze_inputs):
    root, args, *_ = freeze_inputs
    (root / "cache").joinpath("extract").rename(root / "cache" / "extract-hidden")
    assert main(["freeze", "P", *args]) == 2
    assert not (root / "knowledge" / "frozen" / "P" / "manifest.json").exists()


def test_freeze_unknown_season_exits_2(freeze_inputs):
    _, args, *_ = freeze_inputs
    assert main(["freeze", "X", *args]) == 2


def test_refreeze_does_not_overwrite(freeze_inputs):
    root, args, p_session, *_ = freeze_inputs
    assert main(["freeze", "P", *args]) == 0
    season = root / "knowledge" / "frozen" / "P"
    manifest_path = season / "manifest.json"
    frozen_at = json.loads(manifest_path.read_text(encoding="utf-8"))["frozen_at"]
    extraction_path = season / "extract" / f"{p_session.session_id}.json"
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    extraction["recap"] = "Hand edit"
    extraction_path.write_text(json.dumps(extraction), encoding="utf-8")
    assert main(["freeze", "P", *args]) == 0
    assert json.loads(extraction_path.read_text(encoding="utf-8"))["recap"] == "Hand edit"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["frozen_at"] == frozen_at


def test_from_cache_overwrites(freeze_inputs):
    root, args, p_session, *_ = freeze_inputs
    assert main(["freeze", "P", *args]) == 0
    extraction_path = root / "knowledge" / "frozen" / "P" / "extract" / f"{p_session.session_id}.json"
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    extraction["recap"] = "Hand edit"
    extraction_path.write_text(json.dumps(extraction), encoding="utf-8")
    assert main(["freeze", "P", "--from-cache", *args]) == 0
    assert json.loads(extraction_path.read_text(encoding="utf-8"))["recap"] == "Cache recap"


def test_incomplete_state_refreeze_keeps_old_file_but_does_not_read_it(freeze_inputs):
    from pnp_okf.frozen import FrozenStore, write_json
    from pnp_okf.state import write_glossary

    root, args, p_session, *_ = freeze_inputs
    assert main(["freeze", "P", *args]) == 0
    season = root / "knowledge" / "frozen" / "P"
    stale_path = season / "state" / f"{p_session.session_id}.json"
    write_json(stale_path, {"threads": [], "status_changes": [], "attitudes": []})
    manifest_path = season / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["state_sessions"] = 1
    write_json(manifest_path, manifest)
    write_glossary(root / "knowledge", [{"type": "NPC", "name": "Xenia", "aliases": []}])

    assert main(["freeze", "P", "--from-cache", *args]) == 0
    assert stale_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["counts"]["state_sessions"] == 0
    assert FrozenStore.load(root / "knowledge").state_blob(p_session.session_id) is None


def test_frozen_season_survives_cache_loss(freeze_inputs, capsys):
    root, args, *_ = freeze_inputs
    assert main(["freeze", "P", *args]) == 0
    import shutil

    shutil.rmtree(root / "cache")
    assert main(["run", "--estimate", *args]) == 0
    output = capsys.readouterr().out
    assert "frozen:   1 session(s)" in output
    assert "1 to call" in output


def test_freeze_makes_no_llm_call(freeze_inputs, monkeypatch):
    _, args, *_ = freeze_inputs
    def fail(*_args, **_kwargs):
        raise AssertionError("freeze called the model")
    monkeypatch.setattr("pnp_okf.llm_client.build_client", fail)
    assert main(["freeze", "P", *args]) == 0

