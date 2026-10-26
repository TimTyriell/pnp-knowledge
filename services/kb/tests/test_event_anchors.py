"""T4: only allowlisted Events are concepts; the rest anchor in sessions."""

from __future__ import annotations

from pathlib import Path

import pnp_okf.cli as cli
from pnp_okf.emit import EventAnchor, emit_sessions, event_anchors
from pnp_okf.models import (
    CanonicalEntity,
    EntityMention,
    EntityType,
    MentionRef,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.okf import split_document
from pnp_okf.resolve import load_event_concepts

from tests.test_pipeline_offline import _offline_run_args

SID = "2026-01-20_RF_abc"


def _event(cid: str, name: str, ts: str, note: str) -> CanonicalEntity:
    return CanonicalEntity(
        concept_id=cid, type=EntityType.EVENT, canonical_name=name, subtype="Kampf",
        mentions=[MentionRef(session_id=SID, date="2026-01-20", url="http://x",
                             citation_ts=ts, note=note)],
    )


def test_event_anchors_group_by_session_and_sort_by_time():
    anchors = event_anchors([
        _event("events/b", "Kampf B", "01:00:00", "Später."),
        _event("events/a", "Kampf A", "00:10:00", "Früher."),
    ])
    assert [a.title for a in anchors[SID]] == ["Kampf A", "Kampf B"]


def test_session_note_renders_anchors_and_keeps_them_out_of_entity_list(tmp_path: Path):
    transcript = SessionTranscript(session_id=SID, date="2026-01-20", url="http://x", title="T")
    extraction = SessionExtraction(
        recap="Recap.",
        entities=[EntityMention(name="Kampf A", type=EntityType.EVENT,
                                note="Früher.", citation_ts="00:10:00")],
    )
    emit_sessions(
        tmp_path, {SID: transcript}, {SID: extraction},
        mention_concept_ids={},  # the anchored event has no concept
        anchors={SID: [EventAnchor("Kampf A", "Kampf", "00:10:00", "Früher.")]},
    )
    _fm, body = split_document((tmp_path / "sessions" / "2026-01-20.md").read_text(encoding="utf-8"))
    assert "# Ereignisse" in body
    assert "### Kampf A" in body
    assert "_Kampf · 00:10:00_" in body
    assert "# Auftretende Entitäten" not in body
    assert body.index("# Zusammenfassung") < body.index("# Ereignisse")


def test_run_keeps_only_allowlisted_events_as_concepts(tmp_path: Path, monkeypatch):
    """End to end through _run_pipeline (offline, like test_pipeline_offline):
    the allowlisted Event is a file, the other is an anchor in the session."""

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    args = _offline_run_args(tmp_path)
    (tmp_path / "knowledge" / "entity_rules.yaml").write_text(
        "event_concepts:\n- events/harl_verhandlung\n", encoding="utf-8"
    )
    extraction = SessionExtraction(
        recap="Die Gruppe kämpft am Tor und verhandelt.",
        entities=[
            EntityMention(name="Kampf am Tor", type=EntityType.EVENT,
                          note="Ein Kampf am Tor.", citation_ts="00:02:00", subtype="Kampf"),
            EntityMention(name="Harl Verhandlung", type=EntityType.EVENT,
                          note="Eine Verhandlung.", citation_ts="00:03:00", subtype="Verhandlung"),
        ],
    )
    monkeypatch.setattr(
        cli, "extract_session", lambda transcript, cfg, cache_dir, *, force=False: extraction
    )

    assert cli._run_pipeline(args, "2026-09-07T00:00:00Z") == 0

    bundle = Path(args.bundle)
    events = {p.name for p in (bundle / "events").glob("*.md")}
    assert "harl_verhandlung.md" in events
    assert "kampf_am_tor.md" not in events
    _fm, body = split_document((bundle / "sessions" / "2025-03-26.md").read_text(encoding="utf-8"))
    assert "### Kampf am Tor" in body
    assert "### Harl Verhandlung" not in body


def test_load_event_concepts_reads_the_rules_file(tmp_path: Path):
    (tmp_path / "entity_registry.yaml").write_text("entities: []\n", encoding="utf-8")
    (tmp_path / "entity_rules.yaml").write_text(
        "event_concepts:\n- events/verhandlung_mit_harl\n", encoding="utf-8"
    )
    assert load_event_concepts(tmp_path / "entity_registry.yaml") == {"events/verhandlung_mit_harl"}
