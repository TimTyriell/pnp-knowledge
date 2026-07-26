"""Renaming an entity must not change which entities merge.

canonical_name is a display label a human pins at will; using it to drive the
token-subset rule meant a cosmetic rename reshuffled merges and could surface
unrelated conflicts. Identity lives in the concept id.
"""

from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.resolve import merge_near_duplicates


def _e(cid, name, n=1):
    return CanonicalEntity(
        concept_id=cid, type=EntityType.NPC, canonical_name=name,
        mentions=[MentionRef(session_id=f"s{i}", date=f"2025-01-{i+1:02d}",
                             url="u", citation_ts="00:01:00", note="n") for i in range(n)],
    )


def test_pinned_display_name_does_not_change_merges():
    def outcome(name_a):
        ents = [_e("npcs/nairuk", name_a, 3), _e("npcs/nairuk_baer", "Nairuk Bär", 1)]
        return {e.concept_id for e in merge_near_duplicates(ents)}

    # Same ids, different display names -> identical merge result.
    assert outcome("Nairuk") == outcome("Nyruk")


def test_token_subset_still_folds_on_ids():
    ents = [_e("npcs/esterossa", "Esterossa", 1),
            _e("npcs/esterossa_torbhalm", "Esterossa Torbhalm", 5)]
    survivors = merge_near_duplicates(ents)
    assert [e.concept_id for e in survivors] == ["npcs/esterossa_torbhalm"]


def test_two_supersets_stay_unmerged():
    ents = [_e("npcs/voras", "Voras", 1),
            _e("npcs/voras_der_heilige", "Voras der Heilige", 2),
            _e("npcs/voras_der_schrecken", "Voras der Schrecken", 2)]
    assert len(merge_near_duplicates(ents)) == 3   # ambiguous -> human decides
