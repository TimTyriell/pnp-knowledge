"""The registry's ``retired:`` ledger — identity memory that survives a rename.

Before this existed, a concept absent from a run's resolved entity set lost
its whole registry row on the next write_registry(), aliases included. That
is why the 2026-08 incident's ~800 renamed concepts could not be
auto-remapped after the fact: the alias information that could have paired
an old id with its new wording no longer existed anywhere on disk. The
ledger keeps every id write_registry has ever seen, plus the names it was
last known by, so resolve_entities can reanchor a later reword instead of
minting a fresh concept.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pnp_okf.models import EntityMention, EntityType, SessionExtraction, SessionTranscript
from pnp_okf.resolve import resolve_entities, write_registry


def _transcript(stem: str, date: str) -> SessionTranscript:
    return SessionTranscript(
        session_id=stem, date=date, url=f"https://youtu.be/{stem}", title="Session"
    )


def _mention(name: str, etype: EntityType, ts: str = "00:01:00") -> EntityMention:
    return EntityMention(name=name, type=etype, note="Etwas geschah.", citation_ts=ts)


def test_retired_concept_keeps_its_names_in_the_ledger(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    t1 = _transcript("s1", "2025-03-26")

    # Run 1: "Cookie" and "Celin" merge into one concept via the fuzzy pass
    # is not guaranteed, so seed the alias directly via a registry override
    # would require a second name — simplest: two mentions, same session,
    # one canonical + a token-subset-mergeable second name is unnecessary
    # here. We only need the concept to exist with an alias once, which the
    # merge pass already covers elsewhere (test_dedup.py); this test only
    # cares about what happens to that row once it goes quiet.
    extractions = {t1.session_id: SessionExtraction(
        recap="R.", entities=[_mention("Cookie", EntityType.CHARACTER)],
    )}
    tmap = {t1.session_id: t1}
    entities = resolve_entities(extractions, tmap, registry)
    write_registry(entities, registry)
    assert {e.concept_id for e in entities} == {"characters/cookie"}

    # Run 2: the session's cache is untouched, but the run is scoped to a
    # different session set (the realistic full-context trigger is a reword
    # that drops the mention entirely — this simulates that end state
    # directly rather than depending on non-deterministic extraction).
    t2 = _transcript("s2", "2025-04-01")
    extractions2 = {t2.session_id: SessionExtraction(
        recap="R2.", entities=[_mention("Someone Else", EntityType.NPC)],
    )}
    entities2 = resolve_entities(extractions2, {t2.session_id: t2}, registry)
    write_registry(entities2, registry)

    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    live_ids = {e["concept_id"] for e in data.get("entities") or []}
    retired_ids = {e["concept_id"] for e in data.get("retired") or []}
    assert "characters/cookie" not in live_ids
    assert "characters/cookie" in retired_ids
    retired_entry = next(e for e in data["retired"] if e["concept_id"] == "characters/cookie")
    assert retired_entry["canonical_name"] == "Cookie"


def test_ledger_reanchors_an_exact_previously_seen_alias(tmp_path: Path):
    """A wording that was already an alias of a now-retired concept must
    resolve back to that concept's id, not mint a new one."""

    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(
        yaml.safe_dump({
            "entities": [],
            "retired": [{
                "concept_id": "characters/cookie",
                "type": "Character",
                "canonical_name": "Cookie",
                "aliases": ["Celin"],
            }],
        }),
        encoding="utf-8",
    )
    t1 = _transcript("s1", "2025-03-26")
    extractions = {t1.session_id: SessionExtraction(
        recap="R.", entities=[_mention("Celin", EntityType.CHARACTER)],
    )}
    entities = resolve_entities(extractions, {t1.session_id: t1}, registry)
    assert {e.concept_id for e in entities} == {"characters/cookie"}


def test_ledger_reanchors_spelling_drift_by_fuzzy_match(tmp_path: Path):
    """A wording within the fuzzy bar of a retired slug, but never recorded
    verbatim before, still reanchors (Whisper-adjacent drift, not a fresh
    coincidence)."""

    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(
        yaml.safe_dump({
            "entities": [],
            "retired": [{
                "concept_id": "npcs/esterossa",
                "type": "NPC",
                "canonical_name": "Esterossa",
                "aliases": [],
            }],
        }),
        encoding="utf-8",
    )
    t1 = _transcript("s1", "2025-03-26")
    extractions = {t1.session_id: SessionExtraction(
        recap="R.", entities=[_mention("Esterosa", EntityType.NPC)],  # one letter off
    )}
    entities = resolve_entities(extractions, {t1.session_id: t1}, registry)
    assert {e.concept_id for e in entities} == {"npcs/esterossa"}


def test_ledger_reanchor_respects_never_merge(tmp_path: Path):
    """A human ruling that two beings are distinct must survive a fuzzy
    reanchor attempt exactly as it survives merge_near_duplicates."""

    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(
        yaml.safe_dump({
            "entities": [],
            "retired": [{
                "concept_id": "npcs/kip",
                "type": "NPC",
                "canonical_name": "Kip",
                "aliases": [],
            }],
            "never_merge": [["npcs/kip", "npcs/kipp"]],
        }),
        encoding="utf-8",
    )
    t1 = _transcript("s1", "2025-03-26")
    extractions = {t1.session_id: SessionExtraction(
        recap="R.", entities=[_mention("Kipp", EntityType.NPC)],
    )}
    entities = resolve_entities(extractions, {t1.session_id: t1}, registry)
    assert {e.concept_id for e in entities} == {"npcs/kipp"}


def test_ignored_concept_is_not_resurrected_by_the_ledger(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(
        yaml.safe_dump({
            "entities": [],
            "retired": [{
                "concept_id": "npcs/cookie",
                "type": "NPC",
                "canonical_name": "Cookie",
                "aliases": ["Celin"],
            }],
            "ignore": ["npcs/cookie"],
        }),
        encoding="utf-8",
    )
    t1 = _transcript("s1", "2025-03-26")
    extractions = {t1.session_id: SessionExtraction(
        recap="R.", entities=[_mention("Celin", EntityType.NPC)],
    )}
    entities = resolve_entities(extractions, {t1.session_id: t1}, registry)
    assert entities == []


def test_ledger_survives_a_run_that_sees_no_sessions(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    t1 = _transcript("s1", "2025-03-26")
    extractions = {t1.session_id: SessionExtraction(
        recap="R.", entities=[_mention("Cookie", EntityType.CHARACTER)],
    )}
    entities = resolve_entities(extractions, {t1.session_id: t1}, registry)
    write_registry(entities, registry)

    empty_entities = resolve_entities({}, {}, registry)
    write_registry(empty_entities, registry)
    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    assert {e["concept_id"] for e in data.get("retired") or []} == {"characters/cookie"}

    third = resolve_entities(
        {t1.session_id: SessionExtraction(
            recap="R.", entities=[_mention("Cookie", EntityType.CHARACTER)],
        )},
        {t1.session_id: t1},
        registry,
    )
    write_registry(third, registry)
    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    assert data.get("retired") in (None, [])
    assert {e["concept_id"] for e in data["entities"]} == {"characters/cookie"}
