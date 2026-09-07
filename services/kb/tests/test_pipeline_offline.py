from __future__ import annotations

import argparse
import json
from pathlib import Path

import pnp_okf.cli as cli
import pnp_okf.emit as emit_mod
import yaml
from pnp_okf.emit import (
    emit_entity,
    emit_indexes,
    emit_log,
    emit_sessions,
    mention_concept_index,
)
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


def test_session_bullet_links_to_merge_target_not_raw_slug(tmp_path: Path):
    """A merge:d mention must link to the merge target, not slugify(raw name).

    Regression for emit.py's session bullet builder re-slugifying the raw
    extracted name instead of using the concept_id resolve_entities actually
    assigned -- see PIPELINE.md section 7.
    """

    tmap, extractions = _fixture()
    bundle = tmp_path / "bundle" / "campaign"
    registry = bundle.parent / "entity_registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    # Same merge override as test_registry_merge_override: the location
    # mention folds into the character concept.
    registry.write_text(
        yaml.safe_dump({"merge": {"taverne zum zwerg": "characters/lindo_laut"}}),
        encoding="utf-8",
    )

    entities = resolve_entities(extractions, tmap, registry)
    mention_map = mention_concept_index(entities)

    emit_sessions(bundle, tmap, extractions, mention_concept_ids=mention_map)

    session_doc = (bundle / "sessions" / "2025-03-26.md").read_text(encoding="utf-8")
    assert "/characters/lindo_laut.md" in session_doc
    assert "/locations/taverne_zum_zwerg.md" not in session_doc


def _ambiguous_fixture():
    """Two entities whose mentions collide on (session, citation_ts, note).

    MentionRef carries no name, so the LLM reusing one note for two entities
    in the same beat is enough to land them on the same key. Different
    identity spaces here (NPC vs Location), or the fuzzy pass would fold them
    into one concept and there would be nothing ambiguous left.
    """

    t = SessionTranscript(
        session_id="2025-03-26_RF_a", date="2025-03-26",
        url="https://youtu.be/a", title="Session 1",
    )
    extraction = SessionExtraction(
        recap="Harald taucht am Tor auf.",
        entities=[
            EntityMention(
                name="Harald", type=EntityType.NPC,
                note="Taucht am Tor auf.", citation_ts="00:08:25",
            ),
            EntityMention(
                name="Tor von Belorus", type=EntityType.LOCATION,
                note="Taucht am Tor auf.", citation_ts="00:08:25",
            ),
        ],
    )
    return {t.session_id: t}, {t.session_id: extraction}


def test_an_ambiguous_mention_is_reported_not_silently_dropped(tmp_path: Path, caplog):
    """Dropping both entities from a session must leave a trace.

    mention_concept_index maps an ambiguous key to None and then stripped it,
    so emit_sessions could not tell "ambiguous" from "ignore:d" -- both hit
    `resolved is None` and were skipped. Two real entities vanished from
    "Auftretende Entitäten" with nothing counting it, and if every mention in
    a session collided the heading was simply not emitted. The resolver
    refusing to guess is correct; doing it invisibly is not.
    """

    import logging

    tmap, extractions = _ambiguous_fixture()
    bundle = tmp_path / "bundle" / "campaign"
    registry = bundle.parent / "entity_registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(yaml.safe_dump({"merge": {}}), encoding="utf-8")

    entities = resolve_entities(extractions, tmap, registry)
    mention_map = mention_concept_index(entities)

    with caplog.at_level(logging.WARNING, logger="pnp_okf.emit"):
        emit_sessions(bundle, tmap, extractions, mention_concept_ids=mention_map)

    session_doc = (bundle / "sessions" / "2025-03-26.md").read_text(encoding="utf-8")
    assert "Auftretende Entitäten" not in session_doc, (
        "both entities are genuinely unresolvable; the bullet list stays empty"
    )
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "2025-03-26_RF_a" in m and "ambiguous" in m and "Harald" in m for m in messages
    ), f"the drop was silent; log was {messages}"


def test_an_ignored_mention_does_not_warn(tmp_path: Path, caplog):
    """`ignore:` is a decision already taken -- it is not a dropped mention."""

    import logging

    tmap, extractions = _fixture()
    bundle = tmp_path / "bundle" / "campaign"
    registry = bundle.parent / "entity_registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        yaml.safe_dump({"ignore": ["locations/taverne_zum_zwerg"]}), encoding="utf-8"
    )

    entities = resolve_entities(extractions, tmap, registry)
    mention_map = mention_concept_index(entities)

    with caplog.at_level(logging.WARNING, logger="pnp_okf.emit"):
        emit_sessions(bundle, tmap, extractions, mention_concept_ids=mention_map)

    session_doc = (bundle / "sessions" / "2025-03-26.md").read_text(encoding="utf-8")
    assert "/locations/taverne_zum_zwerg.md" not in session_doc
    assert "/characters/lindo_laut.md" in session_doc
    assert not [r for r in caplog.records if "ambiguous" in r.getMessage()]


# --- crash safety: write ordering in _run_pipeline --------------------------
#
# PIPELINE.md section 7, the 2026-09-05 incident: emit_sessions used to run
# before synthesize/emit_entity, and write_registry before everything. A kill
# during the 25-95 minute synthesis window left new session files (and a
# freshly-written registry) pointing at entity concept files that were never
# written -- 54 dangling links. These drive the pipeline end to end (offline:
# extraction is monkeypatched, and the single test entity is brief-tier so no
# synthesis LLM call happens either) and record the real write order.


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


def _stub_extraction() -> SessionExtraction:
    # A single-mention NPC is brief-tier (models.py CanonicalEntity.tier), so
    # synthesis never makes an LLM call either -- the whole run is offline.
    return SessionExtraction(
        recap="Die Gruppe trifft einen NPC.",
        entities=[
            EntityMention(
                name="Wache Hans",
                type=EntityType.NPC,
                note="Ein Wächter am Tor.",
                citation_ts="00:01:00",
            )
        ],
    )


def test_no_session_file_is_written_before_entity_files(
    tmp_path: Path, monkeypatch: object
) -> None:
    """A session file must never land on disk before the entity concept
    file(s) its own bullet list links to -- else a kill leaves a dangling
    link (PIPELINE.md section 7)."""

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    args = _offline_run_args(tmp_path)
    extraction = _stub_extraction()
    monkeypatch.setattr(
        cli, "extract_session", lambda transcript, cfg, cache_dir, *, force=False: extraction
    )

    order: list[str] = []
    original_write_concept = emit_mod.write_concept

    def spy_write_concept(bundle_dir, concept_id, frontmatter, body):
        order.append(concept_id)
        return original_write_concept(bundle_dir, concept_id, frontmatter, body)

    monkeypatch.setattr(emit_mod, "write_concept", spy_write_concept)

    ret = cli._run_pipeline(args, "2026-09-07T00:00:00Z")
    assert ret == 0

    sessions = [i for i, cid in enumerate(order) if cid.startswith("sessions/")]
    entities = [i for i, cid in enumerate(order) if not cid.startswith("sessions/")]
    assert sessions and entities, f"expected both kinds of writes, got {order}"
    assert min(sessions) > max(entities), (
        f"a session file was written before an entity concept file: {order}"
    )


def test_registry_is_written_after_the_bundle_it_describes(
    tmp_path: Path, monkeypatch: object
) -> None:
    """entity_registry.yaml must not sit ahead of the concept files it
    inventories -- else a kill leaves it naming ids with no file behind them
    yet (PIPELINE.md section 7, Task 2)."""

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    args = _offline_run_args(tmp_path)
    extraction = _stub_extraction()
    monkeypatch.setattr(
        cli, "extract_session", lambda transcript, cfg, cache_dir, *, force=False: extraction
    )

    order: list[str] = []
    original_write_concept = emit_mod.write_concept

    def spy_write_concept(bundle_dir, concept_id, frontmatter, body):
        order.append(concept_id)
        return original_write_concept(bundle_dir, concept_id, frontmatter, body)

    monkeypatch.setattr(emit_mod, "write_concept", spy_write_concept)

    original_write_registry = cli.write_registry

    def spy_write_registry(entities, registry_path):
        order.append("REGISTRY")
        return original_write_registry(entities, registry_path)

    monkeypatch.setattr(cli, "write_registry", spy_write_registry)

    ret = cli._run_pipeline(args, "2026-09-07T00:00:00Z")
    assert ret == 0

    registry_positions = [i for i, cid in enumerate(order) if cid == "REGISTRY"]
    concept_positions = [i for i, cid in enumerate(order) if cid != "REGISTRY"]
    assert registry_positions and concept_positions, f"expected both, got {order}"
    assert min(registry_positions) > max(concept_positions), (
        f"the registry was written before the bundle files it describes: {order}"
    )
