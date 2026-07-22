"""Tests for the P1 identity layer: typed IDs, near-duplicate merging,
transcript-quality derivation, and conflict emission."""

from __future__ import annotations

from pathlib import Path

import yaml

from pnp_okf.emit import emit_conflict, emit_entity, split_conflicts
from pnp_okf.models import (
    CanonicalEntity,
    EntityType,
    MentionRef,
    Segment,
    SessionTranscript,
)
from pnp_okf.resolve import merge_near_duplicates
from pnp_okf.validate import validate_bundle


def _entity(
    concept_id: str,
    name: str,
    etype: EntityType = EntityType.CHARACTER,
    mention_count: int = 1,
) -> CanonicalEntity:
    mentions = [
        MentionRef(
            session_id=f"s{i}",
            date=f"2025-03-{26 + i:02d}",
            url="https://youtu.be/x",
            citation_ts="00:01:00",
            note="n",
        )
        for i in range(mention_count)
    ]
    return CanonicalEntity(
        concept_id=concept_id, type=etype, canonical_name=name, mentions=mentions
    )


# --- typed IDs ---------------------------------------------------------------


def test_entity_id_uses_pnp_report_vocabulary():
    assert _entity("characters/lindo_laut", "Lindo Laut").entity_id == "CHAR_LINDO_LAUT"
    assert (
        _entity("npcs/hexe", "Hexe", EntityType.NPC).entity_id == "NPC_HEXE"
    )
    assert (
        _entity("locations/hartwacht", "Hartwacht", EntityType.LOCATION).entity_id
        == "LOC_HARTWACHT"
    )


# --- near-duplicate merging --------------------------------------------------


def test_fuzzy_merge_folds_whisper_spelling_drift():
    a = _entity("characters/esterossa", "Esterossa", mention_count=3)
    b = _entity("characters/esterosa", "Esterosa", mention_count=1)
    merged = merge_near_duplicates([a, b])
    assert len(merged) == 1
    assert merged[0].concept_id == "characters/esterossa"
    assert "Esterosa" in merged[0].aliases
    assert len(merged[0].mentions) == 4


def test_token_subset_merges_into_unique_longer_name():
    short = _entity("characters/esterossa", "Esterossa", mention_count=1)
    full = _entity("characters/esterossa_torbhalm", "Esterossa Torbhalm", mention_count=2)
    merged = merge_near_duplicates([short, full])
    assert len(merged) == 1
    assert merged[0].concept_id == "characters/esterossa_torbhalm"
    assert "Esterossa" in merged[0].aliases


def test_ambiguous_token_subset_stays_unmerged():
    lia = _entity("npcs/lia", "Lia", EntityType.NPC)
    stern = _entity("npcs/lia_stern", "Lia Stern", EntityType.NPC)
    mond = _entity("npcs/lia_mond", "Lia Mond", EntityType.NPC)
    merged = merge_near_duplicates([lia, stern, mond])
    assert {e.concept_id for e in merged} == {
        "npcs/lia",
        "npcs/lia_stern",
        "npcs/lia_mond",
    }


def test_person_space_merges_across_character_and_npc_dirs():
    pc = _entity("characters/lindo_laut", "Lindo Laut", EntityType.CHARACTER, 2)
    npc = _entity("npcs/lindo_laut", "Lindo Laut", EntityType.NPC, 1)
    merged = merge_near_duplicates([pc, npc])
    assert len(merged) == 1
    assert len(merged[0].mentions) == 3


def test_locations_do_not_merge_with_persons():
    person = _entity("npcs/hartwacht", "Hartwacht", EntityType.NPC)
    place = _entity("locations/hartwacht", "Hartwacht", EntityType.LOCATION)
    merged = merge_near_duplicates([person, place])
    assert len(merged) == 2


# --- transcript quality ------------------------------------------------------


def _transcript(spoken: list[tuple[str, str]]) -> SessionTranscript:
    return SessionTranscript(
        session_id="2025-03-26_RF_a",
        date="2025-03-26",
        url="https://youtu.be/a",
        segments=[
            Segment(start=0, end=1, speaker=speaker, text=text)
            for speaker, text in spoken
        ],
    )


def test_quality_hoch_when_all_speakers_mapped():
    t = _transcript([("Deniz (GM)", "eins zwei drei"), ("Tim (Lindo)", "vier")])
    assert t.unsicher_ratio == 0.0
    assert t.quality == "hoch"


def test_quality_niedrig_when_many_unmapped_speakers():
    t = _transcript(
        [("SPEAKER_03", "eins zwei drei vier fuenf"), ("Tim (Lindo)", "sechs")]
    )
    assert t.unsicher_ratio > 0.2
    assert t.quality == "niedrig"


# --- conflicts ---------------------------------------------------------------


_CONFLICT_BODY = """# Überblick

Text.

# Belege

[1] Session 2025-03-26 @ 00:01:00

# Offene Konflikte

* Beleg [1] sagt tot, Beleg [2] sagt lebendig.
"""


def test_split_conflicts_returns_section():
    body, section = split_conflicts(_CONFLICT_BODY)
    assert section is not None
    assert "tot" in section
    assert body == _CONFLICT_BODY  # section stays visible in the concept


def test_emit_entity_flags_disputed_and_queues_conflict(tmp_path: Path):
    bundle = tmp_path / "bundle" / "campaign"
    entity = _entity("characters/lindo_laut", "Lindo Laut")
    _, conflicts = emit_entity(bundle, entity, _CONFLICT_BODY)
    assert conflicts is not None

    doc = (bundle / "characters" / "lindo_laut.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(doc.split("---\n")[1])
    assert fm["id"] == "CHAR_LINDO_LAUT"
    assert fm["status"] == "disputed"

    conflict_path = emit_conflict(tmp_path / "conflicts", entity, conflicts)
    text = conflict_path.read_text(encoding="utf-8")
    cfm = yaml.safe_load(text.split("---\n")[1])
    assert cfm["type"] == "Conflict"
    assert cfm["status"] == "open"
    assert cfm["concept"] == "characters/lindo_laut"


def test_emit_entity_without_conflicts(tmp_path: Path):
    bundle = tmp_path / "bundle" / "campaign"
    entity = _entity("npcs/hexe", "Hexe", EntityType.NPC)
    _, conflicts = emit_entity(bundle, entity, "# Überblick\n\nText.\n\n# Belege\n\n[1] x")
    assert conflicts is None
    doc = (bundle / "npcs" / "hexe.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(doc.split("---\n")[1])
    assert "status" not in fm


# --- validate ----------------------------------------------------------------


def _write_concept(bundle: Path, cid: str, fm: dict, body: str = "Text.") -> None:
    path = bundle / f"{cid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n\n" + body,
        encoding="utf-8",
    )


def test_validate_flags_duplicate_ids_and_suspected_persons(tmp_path: Path):
    bundle = tmp_path / "campaign"
    _write_concept(
        bundle, "characters/esterossa", {"type": "Character", "id": "CHAR_ESTEROSSA"}
    )
    _write_concept(
        bundle,
        "characters/esterossa_torbhalm",
        {"type": "Character", "id": "CHAR_ESTEROSSA_TORBHALM"},
    )
    _write_concept(bundle, "npcs/dup_a", {"type": "NPC", "id": "NPC_SAME"})
    _write_concept(bundle, "npcs/dup_b", {"type": "NPC", "id": "NPC_SAME"})

    report = validate_bundle(bundle)
    assert report.duplicate_ids == {"NPC_SAME": ["npcs/dup_a", "npcs/dup_b"]}
    assert (
        "characters/esterossa",
        "characters/esterossa_torbhalm",
    ) in report.suspected_person_dups
    assert not report.ok
