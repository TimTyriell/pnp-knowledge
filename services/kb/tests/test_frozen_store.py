import json
import logging

import pytest
from pnp_okf.frozen import FrozenError, FrozenStore, mention_fingerprint, write_json
from pnp_okf.models import (
    CanonicalEntity,
    EntityType,
    MentionRef,
    Segment,
    SessionExtraction,
    SessionTranscript,
)


def _transcript(session_id="s1", text="Hallo"):
    return SessionTranscript(
        session_id=session_id,
        date="2026-01-01",
        url="https://example.invalid/video",
        segments=[Segment(start=0, end=1, speaker="A", text=text)],
    )


def _entity(session_ids=("s1",)):
    return CanonicalEntity(
        concept_id="npcs/beispiel",
        type=EntityType.NPC,
        canonical_name="Beispiel",
        mentions=[
            MentionRef(
                session_id=sid,
                date="2026-01-01",
                url="https://example.invalid/video",
                citation_ts="00:00:00",
                note="Eine Erwähnung.",
            )
            for sid in session_ids
        ],
    )


def _freeze(root, *, sessions=("s1",), extraction=True):
    season = root / "frozen" / "P"
    write_json(
        season / "manifest.json",
        {
            "schema": 1,
            "season": "P",
            "sessions": [
                {"session_id": sid, "dialogue_sha": ""} for sid in sessions
            ],
        },
    )
    if extraction:
        value = SessionExtraction(recap="Ein Rückblick.")
        write_json(season / "extract" / "s1.json", value.model_dump(mode="json"))
        return value
    return None


def test_missing_dir_is_an_empty_store(tmp_path):
    store = FrozenStore.load(tmp_path)
    assert store.extraction(_transcript()) is None
    assert store.body(_entity()) is None
    assert store.state_blob("s1") is None
    assert store.season_of("s1") is None


def test_extraction_round_trip(tmp_path):
    expected = _freeze(tmp_path)
    store = FrozenStore.load(tmp_path)
    assert store.extraction(_transcript()) == expected
    assert store.season_of("s1") == "P"


def test_unlisted_session_is_not_frozen(tmp_path):
    _freeze(tmp_path)
    assert FrozenStore.load(tmp_path).extraction(_transcript("s2")) is None


@pytest.mark.parametrize("thaw", [{"P"}, {"all"}])
def test_thaw_hides_the_season(tmp_path, thaw):
    _freeze(tmp_path)
    store = FrozenStore.load(tmp_path, thaw=thaw)
    assert store.extraction(_transcript()) is None
    assert store.season_of("s1") is None


def test_listed_session_without_file_raises(tmp_path):
    _freeze(tmp_path, extraction=False)
    with pytest.raises(FrozenError):
        FrozenStore.load(tmp_path).extraction(_transcript())


def test_corrupt_manifest_raises(tmp_path):
    manifest = tmp_path / "frozen" / "P" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{not json", encoding="utf-8")
    with pytest.raises(FrozenError):
        FrozenStore.load(tmp_path)


def test_changed_transcript_warns_once_and_still_returns(tmp_path, caplog):
    expected = _freeze(tmp_path)
    season = tmp_path / "frozen" / "P"
    manifest = json.loads((season / "manifest.json").read_text(encoding="utf-8"))
    from pnp_okf.frozen import dialogue_sha

    manifest["sessions"][0]["dialogue_sha"] = dialogue_sha(_transcript())
    write_json(season / "manifest.json", manifest)
    changed = _transcript(text="Geändert")

    with caplog.at_level(logging.WARNING):
        store = FrozenStore.load(tmp_path)
        assert store.extraction(changed) == expected
        assert store.extraction(changed) == expected
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "still using the frozen extraction" in warnings[0].message


def test_body_needs_all_mentions_in_one_frozen_season(tmp_path):
    _freeze(tmp_path, sessions=("s1", "s2"))
    entity = _entity(("s1", "outside"))
    assert FrozenStore.load(tmp_path).body(entity) is None


def test_body_fingerprint_mismatch_falls_through(tmp_path):
    _freeze(tmp_path)
    entity = _entity()
    path = tmp_path / "frozen" / "P" / "synth" / "npcs__beispiel.json"
    write_json(path, {"fingerprint": "x", "body": "Fest"})
    store = FrozenStore.load(tmp_path)
    assert store.body(entity) is None

    write_json(path, {"fingerprint": mention_fingerprint(entity), "body": "Fest"})
    assert store.body(entity) == "Fest"
