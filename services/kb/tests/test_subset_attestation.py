"""The token-subset rule must not let a footnote swallow a character.

The rule exists for "Esterossa" -> "Esterossa Torbhalm": a bare first name and
the same person's full name. But it folded the *subset* into the superset
regardless of evidence, so a one-mention derived node ("Die Magier von
Belorus", "Geist von Rotunas", "Vampire/Untote von Voras") absorbed the
well-attested person it was named after and the character's entry disappeared.
"""

from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.resolve import merge_near_duplicates


def _e(cid, name, n, type_=EntityType.NPC):
    return CanonicalEntity(
        concept_id=cid, type=type_, canonical_name=name,
        mentions=[
            MentionRef(session_id=f"s{i}", date=f"2025-01-{i + 1:02d}", url="u",
                       citation_ts="00:01:00", note="n")
            for i in range(n)
        ],
    )


def test_a_derived_node_does_not_swallow_the_person():
    person = _e("npcs/belorus", "Belorus", 6)
    derived = _e("npcs/magier_von_belorus", "Die Magier von Belorus", 1)
    ids = {e.concept_id for e in merge_near_duplicates([person, derived])}
    assert "npcs/belorus" in ids
    assert "npcs/magier_von_belorus" in ids


def test_the_full_name_still_wins_when_better_attested():
    # The case the rule exists for: a bare first name and the same person.
    short = _e("characters/esterossa", "Esterossa", 1, EntityType.CHARACTER)
    full = _e("characters/esterossa_torbhalm", "Esterossa Torbhalm", 39,
              EntityType.CHARACTER)
    ids = {e.concept_id for e in merge_near_duplicates([short, full])}
    assert ids == {"characters/esterossa_torbhalm"}


def test_equal_attestation_still_folds():
    short = _e("npcs/lia", "Lia", 2)
    full = _e("npcs/lia_stormrak", "Lia Stormrak", 2)
    ids = {e.concept_id for e in merge_near_duplicates([short, full])}
    assert ids == {"npcs/lia_stormrak"}
