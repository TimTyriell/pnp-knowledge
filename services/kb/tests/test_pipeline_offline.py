from __future__ import annotations

from pathlib import Path

import yaml
from pnp_okf.emit import emit_entity, emit_indexes, emit_log, emit_sessions
from pnp_okf.models import (
    EntityMention,
    EntityType,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.resolve import resolve_entities, write_registry


def _fixture():
    t1 = SessionTranscript(
        session_id="2025-03-26_RF_a",
        date="2025-03-26",
        url="https://youtu.be/a",
        title="Session 1",
    )
    t2 = SessionTranscript(
        session_id="2025-04-01_RF_b",
        date="2025-04-01",
        url="https://youtu.be/b",
        title="Session 2",
    )
    e1 = SessionExtraction(
        recap="Die Gruppe trifft sich in der Taverne.",
        entities=[
            EntityMention(
                name="Lindo Laut",
                type=EntityType.CHARACTER,
                note="Barde, motiviert die Gruppe.",
                citation_ts="00:08:25",
            ),
            EntityMention(
                name="Taverne zum Zwerg",
                type=EntityType.LOCATION,
                note="Startort der Kampagne.",
                citation_ts="00:10:00",
            ),
        ],
    )
    e2 = SessionExtraction(
        recap="Lindo kämpft gegen Goblins.",
        entities=[
            EntityMention(
                name="Lindo Laut",
                type=EntityType.CHARACTER,
                note="Besiegt einen Goblin.",
                citation_ts="00:20:00",
            ),
        ],
    )
    tmap = {t1.session_id: t1, t2.session_id: t2}
    extractions = {t1.session_id: e1, t2.session_id: e2}
    return tmap, extractions


def test_resolve_and_emit(tmp_path: Path):
    tmap, extractions = _fixture()
    bundle = tmp_path / "bundle" / "campaign"
    registry = bundle.parent / "entity_registry.yaml"

    entities = resolve_entities(extractions, tmap, registry)
    write_registry(entities, registry)

    # Lindo appears twice -> one canonical entity with two mentions.
    lindo = next(e for e in entities if e.concept_id == "characters/lindo_laut")
    assert len(lindo.mentions) == 2

    session_entries = emit_sessions(bundle, tmap, extractions)
    for entity in entities:
        emit_entity(bundle, entity, "# Überblick\n\nBeschreibung.\n\n# Belege\n\n[1] x")
    emit_indexes(bundle, entities, session_entries)
    emit_log(bundle, tmap)

    # Files exist.
    assert (bundle / "sessions" / "2025-03-26.md").exists()
    assert (bundle / "characters" / "lindo_laut.md").exists()
    assert (bundle / "locations" / "taverne_zum_zwerg.md").exists()
    assert (bundle / "index.md").exists()
    assert (bundle / "log.md").exists()
    assert registry.exists()

    # Session concept has frontmatter with required type + resource.
    session_doc = (bundle / "sessions" / "2025-03-26.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(session_doc.split("---\n")[1])
    assert fm["type"] == "Session"
    assert fm["resource"] == "https://youtu.be/a"

    # index.md files carry no frontmatter.
    assert not (bundle / "index.md").read_text(encoding="utf-8").startswith("---")


def test_registry_merge_override(tmp_path: Path):
    tmap, extractions = _fixture()
    bundle = tmp_path / "bundle" / "campaign"
    registry = bundle.parent / "entity_registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    # Fold the location into the character via a manual merge override.
    registry.write_text(
        yaml.safe_dump({"merge": {"taverne zum zwerg": "characters/lindo_laut"}}),
        encoding="utf-8",
    )

    entities = resolve_entities(extractions, tmap, registry)
    ids = {e.concept_id for e in entities}
    assert "locations/taverne_zum_zwerg" not in ids
    assert "characters/lindo_laut" in ids
