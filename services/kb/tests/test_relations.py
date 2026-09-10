"""Untyped, reciprocal `relationships[]` edges derived from a concept body's
"## Beziehungen und Verbindungen" section (links.py::relationship_edges).

Deliberately no `kind` field -- see links.py's module-level comment. This
covers the extraction heuristic (bullet head -> resolved target), the four
filters (self-edge, non-live target, mirroring, sort-for-determinism), note
sanitization, and the two new advisory validate.py checks.
"""

from __future__ import annotations

import pytest
from pnp_okf.emit import emit_entity
from pnp_okf.links import ConceptIndex, relationship_edges
from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.okf import write_concept
from pnp_okf.validate import validate_bundle

IDS = [
    "npcs/hans",
    "npcs/greta",
    "factions/gilde",
    "characters/lindo_laut",
    "sessions/2025-04-09",
]
NAMES = {"Hans": "npcs/hans", "Greta": "npcs/greta", "Gilde": "factions/gilde"}

# Sessions are seeded into the index (a real link to one must still resolve)
# but excluded from `live` -- emit_sessions takes no `relationships` kwarg, so
# a reciprocal edge onto a session page would be silently dropped.
LIVE = {"npcs/hans", "npcs/greta", "factions/gilde", "characters/lindo_laut"}


def _index() -> ConceptIndex:
    return ConceptIndex(IDS, NAMES)


def test_markdown_link_head_resolves():
    body = "## Beziehungen und Verbindungen\n\n- [Hans](/npcs/hans.md): Kennt ihn gut.\n"
    edges = relationship_edges({"npcs/greta": body}, _index(), LIVE)
    assert edges["npcs/greta"] == [
        {"target": "npcs/hans", "note": "[Hans](/npcs/hans.md): Kennt ihn gut."}
    ]


def test_plain_bold_name_head_resolves():
    body = "## Beziehungen und Verbindungen\n\n- **Hans:** Kennt ihn gut.\n"
    edges = relationship_edges({"npcs/greta": body}, _index(), LIVE)
    assert edges["npcs/greta"][0]["target"] == "npcs/hans"


@pytest.mark.parametrize(
    "heading",
    [
        "## Beziehungen und Verbindungen",
        "# Beziehungen und Verbindungen",
        "## Beziehung zur Heldengruppe",
        "## Beziehungen",
    ],
)
def test_all_four_heading_variants_are_matched(heading: str):
    body = f"{heading}\n\n- [Hans](/npcs/hans.md): Text.\n"
    edges = relationship_edges({"npcs/greta": body}, _index(), LIVE)
    assert edges["npcs/greta"][0]["target"] == "npcs/hans"


def test_zu_prefix_is_stripped_before_resolving():
    body = "## Beziehungen und Verbindungen\n\n- **Zur Gilde:** Handelt mit ihr.\n"
    edges = relationship_edges({"npcs/greta": body}, _index(), LIVE)
    assert edges["npcs/greta"][0]["target"] == "factions/gilde"


def test_self_edge_is_dropped():
    body = "## Beziehungen und Verbindungen\n\n- [Hans](/npcs/hans.md): Er selbst.\n"
    edges = relationship_edges({"npcs/hans": body}, _index(), LIVE)
    assert edges == {}


def test_session_target_is_dropped():
    body = "## Beziehungen und Verbindungen\n\n- [Session](/sessions/2025-04-09.md): Erwähnt.\n"
    edges = relationship_edges({"npcs/hans": body}, _index(), LIVE)
    assert edges == {}


def test_mirror_edge_is_produced_on_target():
    body = "## Beziehungen und Verbindungen\n\n- [Hans](/npcs/hans.md): Text.\n"
    edges = relationship_edges({"npcs/greta": body}, _index(), LIVE)
    assert edges["npcs/hans"] == [
        {"target": "npcs/greta", "note": "[Hans](/npcs/hans.md): Text."}
    ]


def test_mutual_assertion_yields_one_edge_per_side_not_two():
    # Both pages naming each other is the common case, not the exception --
    # 40 of 162 concepts in the real bundle do it, the party members most of
    # all. Mirroring unconditionally gave each side two entries for the same
    # target, differing only in which page's prose the note came from.
    # A concept's own prose wins for its own page; the mirror only fills in a
    # side that stayed silent.
    greta = "## Beziehungen und Verbindungen\n\n- [Hans](/npcs/hans.md): Gretas Sicht.\n"
    hans = "## Beziehungen und Verbindungen\n\n- [Greta](/npcs/greta.md): Hans' Sicht.\n"
    edges = relationship_edges({"npcs/greta": greta, "npcs/hans": hans}, _index(), LIVE)
    assert edges["npcs/greta"] == [
        {"target": "npcs/hans", "note": "[Hans](/npcs/hans.md): Gretas Sicht."}
    ]
    assert edges["npcs/hans"] == [
        {"target": "npcs/greta", "note": "[Greta](/npcs/greta.md): Hans' Sicht."}
    ]


def test_same_target_named_by_two_bullets_yields_one_edge():
    body = (
        "## Beziehungen und Verbindungen\n\n"
        "- **Zur Gilde:** Mitglied seit Jahren.\n"
        "- [Gilde](/factions/gilde.md): Zahlt Beiträge.\n"
    )
    edges = relationship_edges({"npcs/greta": body}, _index(), LIVE)
    assert [e["target"] for e in edges["npcs/greta"]] == ["factions/gilde"]
    assert edges["npcs/greta"][0]["note"] == "**Zur Gilde:** Mitglied seit Jahren."


def test_edges_are_sorted_by_target():
    body = (
        "## Beziehungen und Verbindungen\n\n"
        "- [Hans](/npcs/hans.md): Erst genannt.\n"
        "- **Gilde:** Danach genannt.\n"
    )
    edges = relationship_edges({"characters/lindo_laut": body}, _index(), LIVE)
    targets = [e["target"] for e in edges["characters/lindo_laut"]]
    assert targets == ["factions/gilde", "npcs/hans"]  # not insertion order


def test_note_is_single_line_and_capped():
    body = (
        "## Beziehungen und Verbindungen\n\n"
        "- [Hans](/npcs/hans.md):  " + "x" * 250 + "   mit  doppelten  Leerzeichen.\n"
    )
    edges = relationship_edges({"npcs/greta": body}, _index(), LIVE)
    note = edges["npcs/greta"][0]["note"]
    assert "\n" not in note
    assert "  " not in note
    assert len(note) <= 200


def test_running_twice_is_byte_identical(tmp_path):
    body = "## Beziehungen und Verbindungen\n\n- [Hans](/npcs/hans.md): Text.\n"
    bodies = {"npcs/greta": body}
    edges_first = relationship_edges(bodies, _index(), LIVE)
    edges_second = relationship_edges(bodies, _index(), LIVE)
    assert edges_first == edges_second

    entity = CanonicalEntity(
        concept_id="npcs/greta",
        type=EntityType.NPC,
        canonical_name="Greta",
        mentions=[
            MentionRef(
                session_id="s1", date="2026-01-01", url="http://x",
                citation_ts="00:01:00", note="Erwähnt.",
            )
        ],
    )
    emit_entity(tmp_path, entity, "# Überblick\n\nText.\n", relationships=edges_first["npcs/greta"])
    path = tmp_path / "npcs" / "greta.md"
    first_bytes = path.read_bytes()
    first_mtime = path.stat().st_mtime_ns

    emit_entity(tmp_path, entity, "# Überblick\n\nText.\n", relationships=edges_second["npcs/greta"])
    assert path.read_bytes() == first_bytes
    assert path.stat().st_mtime_ns == first_mtime  # write_if_changed: unchanged, no rewrite


def test_bad_relationship_target_is_flagged(tmp_path):
    write_concept(
        tmp_path, "npcs/hans",
        {"type": "NPC", "title": "Hans", "relationships": [{"target": "npcs/ghost", "note": "x"}]},
        "Body.",
    )
    report = validate_bundle(tmp_path)
    assert report.bad_relationship_targets == [("npcs/hans", "npcs/ghost")]


def test_asymmetric_relationship_is_flagged(tmp_path):
    write_concept(
        tmp_path, "npcs/hans",
        {"type": "NPC", "title": "Hans", "relationships": [{"target": "npcs/greta", "note": "x"}]},
        "Body.",
    )
    write_concept(tmp_path, "npcs/greta", {"type": "NPC", "title": "Greta"}, "Body.")
    report = validate_bundle(tmp_path)
    assert report.asymmetric_relationships == [("npcs/hans", "npcs/greta")]
    assert report.bad_relationship_targets == []
