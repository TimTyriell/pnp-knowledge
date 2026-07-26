"""Brief-tier entries are rendered locally, without an LLM call.

Their whole input is a single short note; a model asked to expand it only
reformats. Linking is done against the concept index instead of being invented.
"""

from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.synthesize import link_targets, render_brief_body


def _mention(note, ts="00:12:00", quality="hoch"):
    return MentionRef(
        session_id="2025-05-06_RF_x", date="2025-05-06",
        url="https://youtu.be/x", citation_ts=ts, note=note, quality=quality,
    )


def _entity(cid, name, notes, type_=EntityType.NPC, aliases=()):
    return CanonicalEntity(
        concept_id=cid, type=type_, canonical_name=name, aliases=list(aliases),
        mentions=[_mention(n) for n in notes],
    )


def test_note_is_kept_and_cited():
    entity = _entity("npcs/auranil", "Auranil", ["Priesterin der Kapelle."])
    body = render_brief_body(entity)
    assert "Priesterin der Kapelle." in body
    assert "# Belege" in body
    assert "1. Session 2025-05-06 @ 00:12:00 (https://youtu.be/x)" in body


def test_known_names_become_links_once():
    entity = _entity(
        "npcs/auranil", "Auranil",
        ["Sie übergibt Lindo Laut das Amulett. Lindo Laut flieht."],
    )
    other = _entity("characters/lindo_laut", "Lindo Laut", ["a", "b"],
                    type_=EntityType.CHARACTER)
    body = render_brief_body(entity, link_targets([entity, other]))
    assert "[Lindo Laut](characters/lindo_laut.md)" in body
    # Only the first occurrence is linked — a page peppered with the same link
    # reads worse and adds no edge.
    assert body.count("characters/lindo_laut.md") == 1


def test_genitive_s_is_linked_too():
    entity = _entity("items/amulett", "Amulett", ["Lindo Lauts Amulett glüht."],
                     type_=EntityType.ITEM)
    other = _entity("characters/lindo_laut", "Lindo Laut", ["a", "b"],
                    type_=EntityType.CHARACTER)
    body = render_brief_body(entity, link_targets([entity, other]))
    assert "[Lindo Lauts](characters/lindo_laut.md)" in body


def test_entity_does_not_link_to_itself():
    entity = _entity("npcs/auranil", "Auranil", ["Auranil ist die Priesterin."])
    body = render_brief_body(entity, link_targets([entity]))
    assert "npcs/auranil.md" not in body


def test_better_attested_entity_wins_a_name_collision():
    big = _entity("npcs/harald_gross", "Harald", ["a", "b", "c"])
    small = _entity("npcs/harald_klein", "Harald", ["d"])
    assert link_targets([small, big])["Harald"] == "npcs/harald_gross"


def test_low_quality_transcript_is_marked():
    entity = CanonicalEntity(
        concept_id="npcs/x", type=EntityType.NPC, canonical_name="X",
        mentions=[_mention("Note.", quality="niedrig")],
    )
    assert "[Transkriptqualität: niedrig]" in render_brief_body(entity)
