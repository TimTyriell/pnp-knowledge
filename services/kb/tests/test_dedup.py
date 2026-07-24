"""Checks for merge-candidate detection (proposal only — never writes)."""

from __future__ import annotations

from pnp_okf.dedup import (
    MergeGroup,
    propose,
    string_candidates,
    to_registry_merges,
)
from pnp_okf.models import CanonicalEntity, EntityType, MentionRef


def _e(concept_id, etype, name, n=1, aliases=None):
    return CanonicalEntity(
        concept_id=concept_id,
        type=etype,
        canonical_name=name,
        aliases=aliases or [],
        mentions=[
            MentionRef(
                session_id=f"s{i}", date=f"2025-01-{i + 1:02d}", url="u",
                citation_ts="00:01:00", note="note",
            )
            for i in range(n)
        ],
    )


def test_string_candidates_catch_the_real_misses():
    ents = [
        # Sub-threshold spelling drift (~0.86, below resolve.py's 0.9 bar).
        _e("locations/willau", EntityType.LOCATION, "Willau", 2),
        _e("locations/willauch", EntityType.LOCATION, "Willauch", 2),
        # Ambiguous supersets: resolve.py refuses these on purpose.
        _e("npcs/voras", EntityType.NPC, "Voras"),
        _e("npcs/graf_voras_der_heilige", EntityType.NPC, "Graf Voras der Heilige"),
        _e("npcs/voras_der_heilige_der_schrecken", EntityType.NPC, "Voras der Heilige"),
    ]
    pairs = {frozenset(g.concept_ids) for g in string_candidates(ents)}
    assert frozenset({"locations/willau", "locations/willauch"}) in pairs
    assert frozenset({"npcs/voras", "npcs/graf_voras_der_heilige"}) in pairs


def test_person_space_crosses_character_and_npc():
    ents = [
        _e("characters/esterossa", EntityType.CHARACTER, "Esterossa", 3),
        _e("npcs/esterossa_torbhalm", EntityType.NPC, "Esterossa Torbhalm"),
    ]
    pairs = {frozenset(g.concept_ids) for g in string_candidates(ents)}
    assert frozenset({"characters/esterossa", "npcs/esterossa_torbhalm"}) in pairs


def test_unrelated_types_never_pair():
    ents = [
        _e("locations/breska", EntityType.LOCATION, "Breska"),
        _e("items/breska_wappen", EntityType.ITEM, "Breska"),
    ]
    assert string_candidates(ents) == []


class _FakeClient:
    """Stands in for DeepSeek: returns one semantic group plus a bogus id."""

    class chat:  # noqa: N801
        class completions:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                payload = (
                    '{"groups": [{"concept_ids": ["npcs/lenra", "npcs/die_hack",'
                    ' "npcs/does_not_exist"], "canonical": "npcs/lenra",'
                    ' "reason": "Lenra ist die Hack", "confidence": "hoch"}]}'
                )

                class M:
                    content = payload

                class C:
                    message = M()

                return type("R", (), {"choices": [C()]})()


def test_llm_group_survives_but_hallucinated_ids_are_dropped():
    ents = [
        _e("npcs/lenra", EntityType.NPC, "Lenra", 2),
        _e("npcs/die_hack", EntityType.NPC, "Die Hack", 2),
    ]
    cfg = type("Cfg", (), {"model": "m"})()
    groups = propose(ents, cfg, client=_FakeClient())
    semantic = [g for g in groups if "npcs/die_hack" in g.concept_ids]
    assert semantic, "semantic identity must be proposed"
    # The id the model invented must not leak into a registry write.
    assert "npcs/does_not_exist" not in semantic[0].concept_ids


class _FlakyClient:
    """First chunk hangs/errors, later ones succeed."""

    calls = 0

    class chat:  # noqa: N801
        class completions:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                _FlakyClient.calls += 1
                if _FlakyClient.calls == 1:
                    raise TimeoutError("simulated stall")

                class M:
                    content = '{"groups": []}'

                class C:
                    message = M()

                return type("R", (), {"choices": [C()]})()


def test_one_stalled_chunk_does_not_sink_the_sweep():
    from pnp_okf.dedup import llm_candidates

    _FlakyClient.calls = 0
    # Two identity spaces: the first call raises, the second must still run.
    ents = [
        _e("npcs/a", EntityType.NPC, "A"),
        _e("npcs/b", EntityType.NPC, "B"),
        _e("items/c", EntityType.ITEM, "C"),
        _e("items/d", EntityType.ITEM, "D"),
    ]
    cfg = type("Cfg", (), {"model": "m"})()
    groups = llm_candidates(ents, cfg, client=_FlakyClient())
    assert groups == []
    assert _FlakyClient.calls == 2, "second space must still be attempted"


def test_to_registry_merges_points_losers_at_the_survivor():
    ents = [
        _e("npcs/belorus", EntityType.NPC, "Belorus", 3),
        _e("npcs/lord_belorus", EntityType.NPC, "Lord Belorus", 1, ["Belorus der Stille"]),
    ]
    group = MergeGroup(
        concept_ids=["npcs/belorus", "npcs/lord_belorus"],
        canonical="npcs/belorus",
        reason="same",
        confidence="hoch",
    )
    merges = to_registry_merges([group], ents)
    assert merges["lord belorus"] == "npcs/belorus"
    assert merges["belorus der stille"] == "npcs/belorus"
    # The survivor's own name must not be mapped onto itself.
    assert "belorus" not in merges


if __name__ == "__main__":
    test_string_candidates_catch_the_real_misses()
    test_person_space_crosses_character_and_npc()
    test_unrelated_types_never_pair()
    test_llm_group_survives_but_hallucinated_ids_are_dropped()
    test_to_registry_merges_points_losers_at_the_survivor()
    print("all checks passed")
