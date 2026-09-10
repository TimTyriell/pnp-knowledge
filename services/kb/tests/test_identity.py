"""Tests for the P1 identity layer: typed IDs, near-duplicate merging,
transcript-quality derivation, and conflict emission."""

from __future__ import annotations

from pathlib import Path

import yaml
from pnp_okf.emit import emit_conflict, emit_entity, split_conflicts
from pnp_okf.models import (
    CanonicalEntity,
    EntityMention,
    EntityType,
    MentionRef,
    Segment,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.resolve import merge_near_duplicates, resolve_entities
from pnp_okf.validate import ValidationReport, validate_bundle


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


def test_fuzzy_merge_is_insensitive_to_token_order():
    """Whisper drift reorders words too, not just letters: "Harald der Alte"
    and "Der Alte Harald" name the same NPC, but a plain character-level
    SequenceMatcher ratio on the slug scores this pair badly despite the
    tokens being identical."""

    a = _entity("npcs/harald_der_alte", "Harald der Alte", EntityType.NPC, 2)
    b = _entity("npcs/der_alte_harald", "Der Alte Harald", EntityType.NPC, 1)
    merged = merge_near_duplicates([a, b])
    assert len(merged) == 1
    assert merged[0].concept_id == "npcs/harald_der_alte"


def test_incumbent_concept_id_wins_a_fuzzy_fold_even_with_fewer_mentions():
    """Without a registry-incumbency tiebreak, the entity with more mentions
    THIS run wins a fuzzy fold regardless of which id is already stable, so a
    fresh reword with a few loud mentions can silently rename a long-
    established concept the registry (and every rule keyed on it) already
    knows by its old id."""

    incumbent = _entity("characters/esterossa", "Esterossa", mention_count=1)
    newcomer = _entity("characters/esterosa", "Esterosa", mention_count=3)
    merged = merge_near_duplicates(
        [incumbent, newcomer], known_ids={"characters/esterossa"}
    )
    assert len(merged) == 1
    assert merged[0].concept_id == "characters/esterossa"


def test_locations_do_not_merge_with_persons():
    person = _entity("npcs/hartwacht", "Hartwacht", EntityType.NPC)
    place = _entity("locations/hartwacht", "Hartwacht", EntityType.LOCATION)
    merged = merge_near_duplicates([person, place])
    assert len(merged) == 2


# --- live reanchoring --------------------------------------------------------


def test_reword_of_a_live_concept_reanchors_to_its_existing_id(tmp_path: Path):
    """A reword of a concept that is still *live* must reanchor to its
    existing id, not mint a new one -- the dominant churn mode: the LLM
    rewords an already-known entity's name and its derived concept_id moves.

    Written against a near-miss of the registered alias ("Meister Harold",
    one letter off "Meister Harald") rather than an exact copy: an exact copy
    of a known alias already resolves correctly today via the registry's
    per-concept alias lookup (_load_alias_overrides), so it would not fail
    first -- this is the case that still mints npcs/meister_harold today.
    """
    registry_path = tmp_path / "entity_registry.yaml"
    registry_path.write_text(
        yaml.safe_dump(
            {
                "entities": [
                    {
                        "concept_id": "npcs/harald",
                        "type": "NPC",
                        "canonical_name": "Harald",
                        "aliases": ["Meister Harald"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    transcript = SessionTranscript(
        session_id="s1", date="2026-01-01", url="https://x", segments=[]
    )
    extraction = SessionExtraction(
        recap="",
        entities=[
            EntityMention(
                name="Meister Harold",
                type=EntityType.NPC,
                note="n",
                citation_ts="00:00:00",
            )
        ],
    )
    entities = resolve_entities({"s1": extraction}, {"s1": transcript}, registry_path)
    assert [e.concept_id for e in entities] == ["npcs/harald"]


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


def test_split_conflicts_ignores_an_all_clear_section():
    # The model keeps the heading and declares there is nothing to resolve;
    # queueing that wastes a reviewer's attention on an empty case.
    body = "Text.\n\n# Offene Konflikte\n\n_Keine widersprüchlichen Belege vorhanden._"
    assert split_conflicts(body)[1] is None


def test_split_conflicts_ignores_an_all_clear_written_as_prose():
    body = (
        "Text.\n\n# Offene Konflikte\n\n- Session 5 beschreibt Voras' Tod. Es "
        "gibt keine widersprüchlichen Belege über sein Überleben."
    )
    assert split_conflicts(body)[1] is None


def test_split_conflicts_keeps_a_real_point_next_to_an_all_clear():
    # One settled point must not silence a second, unsettled one.
    body = (
        "Text.\n\n# Offene Konflikte\n\n"
        "- Zum Tod gibt es keine widersprüchlichen Belege.\n"
        "- Sein Titel wird einmal als Graf, einmal als Herzog angegeben."
    )
    section = split_conflicts(body)[1]
    assert section is not None and "Herzog" in section


def test_emit_entity_flags_disputed_and_queues_conflict(tmp_path: Path):
    bundle = tmp_path / "bundle" / "campaign"
    entity = _entity("characters/lindo_laut", "Lindo Laut")
    _, conflicts = emit_entity(bundle, entity, _CONFLICT_BODY)
    assert conflicts is not None

    doc = (bundle / "characters" / "lindo_laut.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(doc.split("---\n")[1])
    assert fm["id"] == "CHAR_LINDO_LAUT"
    # SPEC.md §5.4 reserves "status" for draft|stable|deprecated.
    assert fm["review_status"] == "disputed"
    assert "status" not in fm

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


def test_validate_flags_a_link_whose_target_file_does_not_exist(tmp_path: Path):
    """A dangling href must be reported even when the fuzzy resolver rescues it.

    ConceptIndex.resolve() matches a short href against a longer concept slug
    (_by_prefix), so a link to /npcs/harald.md silently "resolves" to
    npcs/harald_der_alte and broken_links stays empty -- while the href on disk
    still names a file nobody wrote. That is the class that silently repoints a
    link at a different entity with its label unchanged. Existence on disk is
    the only check that survives deleting the fuzzy resolver.
    """

    bundle = tmp_path / "campaign"
    _write_concept(bundle, "npcs/harald_der_alte", {"type": "NPC"})
    _write_concept(
        bundle,
        "sessions/2026-01-01",
        {"type": "Session"},
        "Siehe [Harald](/npcs/harald.md).",
    )

    report = validate_bundle(bundle)

    # The fuzzy resolver rescues it, so the existing check stays silent...
    assert report.broken_links == []
    # ...but nothing on disk answers to that href.
    assert report.dangling_links == [("sessions/2026-01-01", "/npcs/harald.md")]
    assert not report.ok


def test_a_relative_href_to_a_real_file_is_not_dangling(tmp_path: Path):
    """The dangling check must resolve an href the way a reader would.

    _LINK_RE deliberately matches document-relative (`../npcs/x.md`, `./x.md`)
    and bare (`x.md`) hrefs, but the check joined every one of them onto the
    bundle root: `../npcs/x.md` escaped the bundle and a bare `x.md` looked in
    the wrong directory, so a link pointing at a file that exists was reported
    as dangling. dangling_links feeds integrity_ok, which makes `pnp run`
    return 3 after the bundle is already written -- and there is no
    --allow-dangling to get past it. One hand-edited relative link would have
    failed every future run.
    """

    bundle = tmp_path / "campaign"
    _write_concept(bundle, "npcs/harald_der_alte", {"type": "NPC"})
    _write_concept(bundle, "npcs/greta", {"type": "NPC"})
    _write_concept(
        bundle,
        "sessions/2026-01-01",
        {"type": "Session"},
        "Siehe [Harald](../npcs/harald_der_alte.md) und [Greta](./../npcs/greta.md).",
    )
    _write_concept(
        bundle,
        "npcs/bertram",
        {"type": "NPC"},
        "Neben [Greta](greta.md) und [Harald](./harald_der_alte.md).",
    )

    report = validate_bundle(bundle)

    assert report.dangling_links == [], (
        "every href above names a file that exists, from its own directory"
    )


def test_a_relative_href_that_escapes_the_bundle_is_dangling(tmp_path: Path):
    """Leaving the bundle is breakage, not a rescue -- it cannot ship."""

    bundle = tmp_path / "campaign"
    (tmp_path / "outside.md").write_text("nicht im Bundle", encoding="utf-8")
    _write_concept(
        bundle,
        "sessions/2026-01-01",
        {"type": "Session"},
        "Siehe [draussen](../../outside.md).",
    )

    report = validate_bundle(bundle)

    assert report.dangling_links == [("sessions/2026-01-01", "../../outside.md")]


def test_integrity_ok_separates_hard_breakage_from_advisory_findings():
    """The run gate must fire on breakage, not on heuristics.

    A healthy bundle already reports suspected person duplicates and cross-type
    slugs -- fuzzy findings a human triages. Gating `pnp run` on report.ok would
    fail every run, and a gate that always fails gets switched off. Only classes
    that mean the corpus is structurally wrong may block.
    """

    advisory = ValidationReport()
    advisory.suspected_person_dups = [("npcs/a", "npcs/b")]
    advisory.cross_type_slugs = {"sanddorn": ["factions/sanddorn", "locations/sanddorn"]}
    assert not advisory.ok
    assert advisory.integrity_ok

    broken = ValidationReport()
    broken.dangling_links = [("sessions/2026-01-01", "/npcs/nobody.md")]
    assert not broken.integrity_ok


def test_live_alias_reanchor_picks_the_best_match_not_the_first():
    """Similarity decides, not registry file order.

    _reanchor_to_live_alias returned on the first alias clearing FUZZY_RATIO
    while walking preserved_aliases in insertion order -- i.e. the order the
    registry happens to list concepts in. With two live concepts both above
    the bar, the closer one lost purely on position, and the mention was then
    bound to the wrong concept for good: that id feeds merge_near_duplicates'
    survivor preference on the next pass.
    """

    from pnp_okf.resolve import _reanchor_to_live_alias

    # "Harald Wirt" is a near-perfect match for the second concept and a
    # weaker (but still >= 0.9) match for the first.
    aliases = {
        "npcs/harald_wirtz": ["Harald Wirtz"],
        "npcs/harald_wirt": ["Harald Wirt"],
    }

    got = _reanchor_to_live_alias("Harald Wirt", EntityType.NPC, aliases)
    assert got == "npcs/harald_wirt", (
        "an exact alias match lost to a weaker one listed first"
    )

    # ...and the answer must not depend on how the registry orders them.
    reversed_order = dict(reversed(list(aliases.items())))
    assert _reanchor_to_live_alias("Harald Wirt", EntityType.NPC, reversed_order) == got
