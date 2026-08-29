"""Brief-tier entries are rendered locally, without an LLM call.

Their whole input is a single short note; a model asked to expand it only
reformats. Linking is done against the concept index instead of being invented.
"""

from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.synthesize import autolink_prose, link_targets, render_brief_body


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


# --- autolink_prose: the standard/deep-tier counterpart of render_brief_body's
# built-in linking (see Fix 1, services/kb/tests — an LLM-synthesized body was
# never autolinked at all before this, which is why 53/60 deep-tier nodes had
# zero outgoing links) -------------------------------------------------------

_TARGETS = {"Belorus": "npcs/belorus", "Lenra": "npcs/lenra"}


def test_prose_head_gets_linked():
    body = "Belorus herrscht über die Burg. Lenra lebt im Sumpf.\n\n# Belege\n\n1. x\n"
    linked = autolink_prose(body, _TARGETS, skip="factions/x")
    assert "[Belorus](npcs/belorus.md)" in linked
    assert "[Lenra](npcs/lenra.md)" in linked


def test_belege_section_is_never_touched():
    body = "Siehe Belorus.\n\n# Belege\n\n1. Session x. Auch Lenra kommt vor.\n"
    linked = autolink_prose(body, _TARGETS, skip="factions/x")
    assert "[Lenra]" not in linked
    assert "Auch Lenra kommt vor." in linked


def test_heading_line_is_not_linked():
    body = "## Belorus\n\nEr herrscht über Zebros. Lenra warnt ihn.\n\n# Belege\n\n1. x\n"
    linked = autolink_prose(body, _TARGETS, skip="factions/x")
    assert linked.startswith("## Belorus\n")  # heading line untouched
    assert "[Lenra](npcs/lenra.md)" in linked  # prose line still linked


def test_existing_link_or_url_is_not_relinked():
    body = (
        "[Belorus](npcs/belorus.md) herrscht. Lenra lebt.\n\n"
        "# Belege\n\n1. Session x (https://youtu.be/Lenra) — nicht verlinkt.\n"
    )
    linked = autolink_prose(body, _TARGETS, skip="factions/x")
    assert linked.count("belorus.md") == 1  # not linked a second time
    assert "[Lenra](npcs/lenra.md)" in linked  # the real, unlinked mention


def test_applying_twice_is_the_same_as_once():
    body = "Belorus greift an. Später greift Belorus erneut an. Lenra beobachtet.\n\n# Belege\n\n1. x\n"
    once = autolink_prose(body, _TARGETS, skip="factions/x")
    twice = autolink_prose(once, _TARGETS, skip="factions/x")
    assert once == twice
