"""A run must not rewrite files it has no new knowledge for.

The 2026-08 incident this guards against: a forced re-extraction resampled
the LLM for 61 already-ingested sessions, which reworded most extracted
entity names. Since concept_id is derived from the extracted name, that
silently renamed ~800 concepts, and the next ordinary ingest (4 new sessions,
no --force) flushed both the drift and the real ingest to disk as one
1000+-file diff — even though the 4 new sessions on their own touched only
32 of 833 pre-existing entities and renamed nothing.

These tests hold two properties that would have caught it:
- idempotency: re-emitting identical input writes zero bytes.
- incrementality: adding a session only touches the concepts it mentions.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from pnp_okf.emit import emit_entity, emit_indexes, emit_log, emit_sessions
from pnp_okf.links import ConceptIndex
from pnp_okf.models import EntityMention, EntityType, SessionExtraction, SessionTranscript
from pnp_okf.okf import write_if_changed
from pnp_okf.resolve import resolve_entities, write_registry

BODY = "# Überblick\n\nBeschreibung.\n\n# Belege\n\n[1] x"


def _transcript(stem: str, date: str) -> SessionTranscript:
    return SessionTranscript(
        session_id=stem, date=date, url=f"https://youtu.be/{stem}", title="Session"
    )


def _mention(name: str, etype: EntityType, ts: str) -> EntityMention:
    return EntityMention(name=name, type=etype, note="Etwas geschah.", citation_ts=ts)


def _emit_all(bundle: Path, tmap: dict, extractions: dict, entities: list) -> None:
    session_entries = emit_sessions(bundle, tmap, extractions)
    for entity in entities:
        emit_entity(bundle, entity, BODY)
    emit_indexes(bundle, entities, session_entries)
    emit_log(bundle, tmap)


def _mtimes(bundle: Path) -> dict[Path, int]:
    return {p: p.stat().st_mtime_ns for p in bundle.rglob("*.md")}


# --- write_if_changed (the mechanism) ---------------------------------------


def test_write_if_changed_skips_identical_content(tmp_path: Path):
    path = tmp_path / "x.md"
    assert write_if_changed(path, "hello") is True
    before = path.stat().st_mtime_ns
    time.sleep(0.02)
    assert write_if_changed(path, "hello") is False
    assert path.stat().st_mtime_ns == before
    assert write_if_changed(path, "changed") is True
    assert path.stat().st_mtime_ns != before


# --- idempotency -------------------------------------------------------------


def test_second_run_over_identical_inputs_writes_nothing(tmp_path: Path):
    t1 = _transcript("2025-03-26_RF_a", "2025-03-26")
    t2 = _transcript("2025-04-01_RF_b", "2025-04-01")
    tmap = {t1.session_id: t1, t2.session_id: t2}
    extractions = {
        t1.session_id: SessionExtraction(
            recap="Recap 1.",
            entities=[_mention("Lindo Laut", EntityType.CHARACTER, "00:08:25")],
        ),
        t2.session_id: SessionExtraction(
            recap="Recap 2.",
            entities=[_mention("Lindo Laut", EntityType.CHARACTER, "00:20:00")],
        ),
    }
    bundle = tmp_path / "bundle"
    registry = tmp_path / "entity_registry.yaml"
    entities = resolve_entities(extractions, tmap, registry)
    write_registry(entities, registry)

    _emit_all(bundle, tmap, extractions, entities)
    before = _mtimes(bundle)
    assert before  # sanity: something was written

    time.sleep(0.02)
    _emit_all(bundle, tmap, extractions, entities)
    after = _mtimes(bundle)

    assert before == after, "identical re-emit rewrote at least one file"


# --- incrementality ------------------------------------------------------


def test_adding_a_session_only_touches_entities_it_mentions(tmp_path: Path):
    t1 = _transcript("2025-03-26_RF_a", "2025-03-26")
    t2 = _transcript("2025-04-01_RF_b", "2025-04-01")
    extractions = {
        t1.session_id: SessionExtraction(
            recap="Recap 1.",
            entities=[
                _mention("Lindo Laut", EntityType.CHARACTER, "00:08:25"),
                _mention("Taverne zum Zwerg", EntityType.LOCATION, "00:10:00"),
            ],
        ),
        t2.session_id: SessionExtraction(
            recap="Recap 2.",
            entities=[_mention("Lindo Laut", EntityType.CHARACTER, "00:20:00")],
        ),
    }
    tmap_before = {t1.session_id: t1, t2.session_id: t2}
    bundle = tmp_path / "bundle"
    registry = tmp_path / "entity_registry.yaml"
    entities_before = resolve_entities(extractions, tmap_before, registry)
    write_registry(entities_before, registry)
    _emit_all(bundle, tmap_before, extractions, entities_before)
    before = _mtimes(bundle)

    # A third session mentions Lindo Laut again (more knowledge about an
    # existing entity) and one brand-new entity. Taverne zum Zwerg is not
    # mentioned again.
    t3 = _transcript("2025-04-09_RF_c", "2025-04-09")
    extractions[t3.session_id] = SessionExtraction(
        recap="Recap 3.",
        entities=[
            _mention("Lindo Laut", EntityType.CHARACTER, "00:05:00"),
            _mention("Neuer NPC", EntityType.NPC, "00:12:00"),
        ],
    )
    tmap_after = {**tmap_before, t3.session_id: t3}
    entities_after = resolve_entities(extractions, tmap_after, registry)
    write_registry(entities_after, registry)

    time.sleep(0.02)
    _emit_all(bundle, tmap_after, extractions, entities_after)
    after = _mtimes(bundle)

    changed = {p for p in before if before[p] != after.get(p)}
    new = set(after) - set(before)
    missing = set(before) - set(after)

    assert missing == set(), f"a run that only adds a session deleted files: {missing}"
    assert (bundle / "characters" / "lindo_laut.md") in changed
    assert (bundle / "sessions" / "2025-04-09.md") in new
    assert (bundle / "npcs" / "neuer_npc.md") in new
    # Untouched by the new session: same content, same mtime.
    assert (bundle / "locations" / "taverne_zum_zwerg.md") not in changed
    assert (bundle / "sessions" / "2025-03-26.md") not in changed
    assert (bundle / "sessions" / "2025-04-01.md") not in changed


# --- identity stability under re-extraction ---------------------------------
#
# Phase 3 (registry-anchored identity, see test_registry_ledger.py) closes
# two of the three ways a resample can rename a concept: a wording that was
# already recorded as an alias reanchors exactly, and one within the fuzzy
# bar of a retired slug reanchors by drift. Both are exercised end to end
# here (through resolve_entities + write_registry, not the ledger's own
# unit tests). The third way — a first-ever reword to wording that matches
# neither, exactly the 08-17 incident's shape — has no code fix: recovering
# it would require loosening the fuzzy match far enough to fold unrelated
# entities together (measured against the real incident data: ratio >= 0.9
# recovers 2% of the renamed concepts, and already mispairs some). That
# case stays xfail; check_rename_safety (test_rename_guard.py) is the actual
# defence against it — refuse the run rather than guess.


def test_reanchors_a_previously_seen_alias_end_to_end(tmp_path: Path):
    t1 = _transcript("2025-03-26_RF_a", "2025-03-26")
    t2 = _transcript("2025-04-01_RF_b", "2025-04-01")
    tmap = {t1.session_id: t1, t2.session_id: t2}
    registry = tmp_path / "entity_registry.yaml"

    # Two sessions, two spellings for the same person, close enough that the
    # ordinary fuzzy merge pass folds them into one concept with an alias.
    # "Cookie" gets the extra mention so it — not "Cookiie" — survives as
    # the winner (merge_near_duplicates breaks ties toward more mentions).
    first = {
        t1.session_id: SessionExtraction(
            recap="Recap.",
            entities=[
                _mention("Cookie", EntityType.CHARACTER, "00:08:25"),
                _mention("Cookie", EntityType.CHARACTER, "00:09:00"),
            ],
        ),
        t2.session_id: SessionExtraction(
            recap="Recap.",
            entities=[_mention("Cookiie", EntityType.CHARACTER, "00:05:00")],
        ),
    }
    entities = resolve_entities(first, tmap, registry)
    write_registry(entities, registry)
    assert {e.concept_id for e in entities} == {"characters/cookie"}
    assert "Cookiie" in entities[0].aliases

    # The concept goes quiet (its sessions drop out of this run's scope,
    # standing in for a reword that stops mentioning it under any known
    # name), retiring it into the ledger with that alias intact.
    write_registry([], registry)

    # A later session uses the exact alias the ledger remembers.
    t3 = _transcript("2025-04-09_RF_c", "2025-04-09")
    later = {t3.session_id: SessionExtraction(
        recap="Recap.",
        entities=[_mention("Cookiie", EntityType.CHARACTER, "00:02:00")],
    )}
    entities = resolve_entities(later, {t3.session_id: t3}, registry)
    assert {e.concept_id for e in entities} == {"characters/cookie"}


@pytest.mark.xfail(
    reason="A first-ever reword to wording that matches neither a known "
    "alias nor the fuzzy bar against the retired ledger cannot be "
    "recovered without risking folding unrelated entities together (see "
    "the module-level note above). check_rename_safety in "
    "test_rename_guard.py is the actual defence — refuse the run.",
    strict=True,
)
def test_reworded_extraction_keeps_the_registry_concept_id(tmp_path: Path):
    t1 = _transcript("2025-03-26_RF_a", "2025-03-26")
    tmap = {t1.session_id: t1}
    registry = tmp_path / "entity_registry.yaml"

    first = {t1.session_id: SessionExtraction(
        recap="Recap.",
        entities=[_mention("Cookie", EntityType.CHARACTER, "00:08:25")],
    )}
    entities = resolve_entities(first, tmap, registry)
    write_registry(entities, registry)
    assert {e.concept_id for e in entities} == {"characters/cookie"}

    # Same session, same person, re-extracted with a different LLM sample.
    reworded = {t1.session_id: SessionExtraction(
        recap="Recap.",
        entities=[_mention("Celin (Cookie)", EntityType.CHARACTER, "00:08:25")],
    )}
    entities = resolve_entities(reworded, tmap, registry)

    assert {e.concept_id for e in entities} == {"characters/cookie"}
    cookie = entities[0]
    assert "Celin (Cookie)" in cookie.aliases


# --- session index blurbs must see the spelling map too --------------------
#
# emit_indexes only applies apply_spellings inside its own per-type _entry
# helper; the session blurb is built earlier in emit_sessions and went
# straight to _short_desc, bypassing the spelling map entirely. Both the
# with-transcript path and the no-transcript (_refresh_orphan_sessions) path
# had the same gap.


def test_session_blurb_gets_spelling_fixes(tmp_path: Path):
    bundle = tmp_path / "bundle"
    t1 = _transcript("2026-01-13_RF_a", "2026-01-13")
    tmap = {t1.session_id: t1}
    extractions = {t1.session_id: SessionExtraction(recap="Das Turnier von Willau begann.")}
    index = ConceptIndex([], spellings={"Willau": "Willauch"})

    entries = emit_sessions(bundle, tmap, extractions, index)

    assert len(entries) == 1
    _title, _url, blurb = entries[0]
    assert "Willauch" in blurb
    assert "Willau " not in blurb + " "
