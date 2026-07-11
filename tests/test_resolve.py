"""Invariants for speaker parsing + canonical-id resolution (no LLM, no Neo4j).

Run: python -m pytest tests/  (or python tests/test_resolve.py for the asserts).
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pnp_graph.resolve as resolve_mod
from pnp_graph.chunking import parse_speaker, session_cast
from pnp_graph.resolve import Resolver, map_predicate, normalize, normalize_confidence, resolve_graph, slug
from pnp_graph.schema import (Character, Decision, GraphExtraction, Item,
                              Relationship, RollEvent, RuleEntity)
from pnp_graph.srd import SrdIndex

CAST_LABELS = ["Tim (Lindo Laut)", "Marco (Dodo)", "Celin (Cookie)", "Deniz (GM)"]


def _tmp_resolver() -> Resolver:
    """Resolver on a throwaway copy of the seed registry (no write-back into data/)."""
    seed = Path(__file__).resolve().parents[1] / "data" / "alias_registry.json"
    tmp = Path(tempfile.mkdtemp()) / "alias_registry.json"
    tmp.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")
    return Resolver(tmp)


def _cast_info(resolver: Resolver) -> dict:
    segs = [{"speaker": lbl, "text": "hi", "start": 0, "end": 1} for lbl in CAST_LABELS]
    return resolver.bootstrap_cast(session_cast(segs))


def test_parse_speaker():
    assert parse_speaker("Tim (Lindo Laut)") == ("Tim", "Lindo Laut", False)
    assert parse_speaker("Deniz (GM)") == ("Deniz", None, True)
    assert parse_speaker("S0") == ("S0", None, False)  # plain label untouched


def test_slug_and_normalize_fold_german():
    assert slug("der Schleichfurz") == "Schleichfurz"
    assert slug("Marco (Dodo)") == "Marco"
    assert normalize("Schleichfurz ") == normalize("der Schleichfurz")
    assert normalize("Bär") == normalize("Baer")
    assert normalize("Straße") == "strasse"


def test_bootstrap_cast_splits_players_and_characters():
    r = _tmp_resolver()
    info = _cast_info(r)
    assert set(info["players"]) == {"PLAYER_Tim", "PLAYER_Marco", "PLAYER_Celin", "PLAYER_Deniz"}
    assert set(info["characters"]) == {"CHAR_LindoLaut", "CHAR_Dodo", "CHAR_Cookie", "CHAR_Deniz_GM"}
    assert info["plays"]["PLAYER_Tim"] == "CHAR_LindoLaut"
    assert info["plays"]["PLAYER_Deniz"] == "CHAR_Deniz_GM"
    assert info["characters"]["CHAR_Deniz_GM"]["is_pc"] is False


def test_resolve_variants_collapse_to_one_id():
    r = _tmp_resolver()
    a = r.resolve("der Schleichfurz", "Character")
    assert a == r.resolve("Schleichfurz ", "Character")   # normalized hit
    assert a == r.resolve("Schleichfurtz", "Character")   # fuzzy hit (typo)
    assert a == r.resolve("Schleichfurz", "Character")


def test_resolve_never_crosses_type():
    r = _tmp_resolver()
    loc = r.resolve("Daggerheart", "Location")
    fac = r.resolve("Daggerheart", "Faction")
    assert loc != fac and loc.startswith("LOC_") and fac.startswith("FACTION_")


def test_alias_hit_beats_minting():
    r = _tmp_resolver()
    assert r.resolve("Lindo", "Character") == "CHAR_LindoLaut"  # seeded alias
    assert r.resolve("GM", "Character") == "CHAR_Deniz_GM"


def test_player_name_never_becomes_character():
    r = _tmp_resolver()
    assert r.resolve("Tim", "Character") == "PLAYER_Tim"  # resolved as player, rerouted later


def test_map_predicate():
    assert map_predicate("ALLY_OF") == ("ALLIED_WITH", True)     # synonym
    assert map_predicate("MEMBER_OF") == ("MEMBER_OF", True)
    assert map_predicate("TELLS_VIA_DENIZ") == ("RELATES_TO", False)  # off-vocab


def test_normalize_confidence():
    assert normalize_confidence("hoch") == "high"
    assert normalize_confidence("Mittel") == "medium"
    assert normalize_confidence("low") == "low"
    assert normalize_confidence("???") == "medium"


def test_resolve_graph_end_to_end(tmp_state=None):
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())  # keep dropped-edge logs out of state/
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        characters=[
            Character(name="Lindo Laut", type="PC"),
            Character(name="Tim (Lindo Laut)", type="PC"),   # composite must not fork
            Character(name="Marco", type="PC"),               # player name must not fork
        ],
        items=[Item(name="Zauberstab", owner="Lindo")],
        relationships=[
            Relationship(subject="Lindo", predicate="ALLY_OF", object="Dodo", confidence="high"),
            Relationship(subject="Lindo Laut", predicate="FLIRTS_WITH", object="Cookie", confidence="low"),
            Relationship(subject="Niemand", predicate="KNOWS", object="Lindo", confidence="high"),
        ],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    ids = {e["id"] for e in resolved["entities"]}

    # exactly one node per real person; composite + player names collapsed
    assert "CHAR_LindoLaut" in ids
    assert not any(i.startswith("CHAR_Tim") or i.startswith("CHAR_Marco") for i in ids)

    edges = {(e["start_id"], e["type"], e["end_id"]): e for e in resolved["edges"]}
    # PLAYS parsed from labels, one per player, stamped with seq
    assert edges[("PLAYER_Tim", "PLAYS", "CHAR_LindoLaut")]["props"]["seq"] == 1
    # synonym mapped
    ally = edges[("CHAR_LindoLaut", "ALLIED_WITH", "CHAR_Dodo")]
    assert ally["props"]["confidence"] == "high"
    # off-vocab coerced to RELATES_TO, original kept
    rel = edges[("CHAR_LindoLaut", "RELATES_TO", "CHAR_Cookie")]
    assert rel["props"]["original_predicate"] == "FLIRTS_WITH"
    # owner via alias -> OWNED_BY edge
    assert any(k[1] == "OWNED_BY" and k[2] == "CHAR_LindoLaut" for k in edges)
    # unresolved endpoint dropped, not written
    assert len(resolved["dropped"]) == 1
    assert resolved["dropped"][0]["subject"] == "Niemand"
    # in-fiction edges never land on a Player (only PLAYS may touch PLAYER_*)
    for (s, t, o) in edges:
        if t != "PLAYS":
            assert not s.startswith("PLAYER_") and not o.startswith("PLAYER_")
    # every node and edge carries provenance
    for e in resolved["entities"]:
        assert e["props"]["session_id"] and e["props"]["confidence"]
    for e in resolved["edges"]:
        assert e["props"]["session_id"] and e["props"]["confidence"]


def test_scenes_and_evidence():
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        characters=[Character(name="Lindo Laut", type="PC")],
        relationships=[
            Relationship(subject="Lindo Laut", predicate="KNOWS", object="Cookie",
                         confidence="high", evidence=2),
        ],
    )
    evidence = {
        ("characters", "Lindo Laut"): [1, 2],
        ("relationships", ("Lindo Laut", "KNOWS", "Cookie")): [2],
    }
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1,
                             evidence=evidence, n_chunks=3)
    by_id = {e["id"]: e for e in resolved["entities"]}
    # one Scene per chunk, seq set, linked to the session
    scenes = [e for e in resolved["entities"] if e["type"] == "Scene"]
    assert [s["props"]["seq"] for s in sorted(scenes, key=lambda s: s["id"])] == [1, 2, 3]
    edges = {(e["start_id"], e["type"], e["end_id"]): e for e in resolved["edges"]}
    assert ("SCENE_2025-03-26_S01", "IN_SESSION", "SESS_2025-03-26") in edges
    # extracted fact stamped with its scenes + EVIDENCED_IN edges
    assert by_id["CHAR_LindoLaut"]["props"]["evidence_scenes"] == [
        "SCENE_2025-03-26_S01", "SCENE_2025-03-26_S02"]
    assert ("CHAR_LindoLaut", "EVIDENCED_IN", "SCENE_2025-03-26_S01") in edges
    assert ("CHAR_LindoLaut", "EVIDENCED_IN", "SCENE_2025-03-26_S02") in edges
    # relationship carries evidence_scenes (from the sidecar)
    rel = edges[("CHAR_LindoLaut", "KNOWS", "CHAR_Cookie")]
    assert rel["props"]["evidence_scenes"] == ["SCENE_2025-03-26_S02"]


def test_record_evidence_sidecar():
    from pnp_graph.extract import _record_evidence
    ev: dict = {}
    g = GraphExtraction(
        characters=[Character(name="Dodo", type="PC")],
        relationships=[Relationship(subject="Dodo", predicate="KNOWS", object="Cookie",
                                    confidence="high")],
    )
    _record_evidence(ev, g, 1)
    _record_evidence(ev, g, 3)
    assert ev[("characters", "Dodo")] == [1, 3]
    assert ev[("relationships", ("Dodo", "KNOWS", "Cookie"))] == [1, 3]


def test_srd_rules_rolls_decisions():
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    srd = SrdIndex()
    extraction = GraphExtraction(
        rule_entities=[
            RuleEntity(name="Barde", subtype="Class"),          # German alias -> SRD id
            RuleEntity(name="Hausregel Xyz", subtype="System"), # not in SRD -> minted
        ],
        roll_events=[
            RollEvent(name="Dodo attack roll", roller="Dodo", trait_or_action="attack",
                      outcome="success_with_fear", target="Monster", confidence="high"),
        ],
        decisions=[
            Decision(name="Ritual bewusst falsch", decided_by="Lindo Laut",
                     quote="wir machen es falsch", consequence="Monster erscheint",
                     confidence="high"),
        ],
        characters=[Character(name="Monster", type="NPC")],
        relationships=[
            Relationship(subject="Lindo Laut", predicate="HAS_CLASS", object="Barde",
                         confidence="high"),
            Relationship(subject="Ritual bewusst falsch", predicate="TRIGGERED",
                         object="Monster", confidence="high"),
        ],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1,
                             evidence={}, n_chunks=1, srd_index=srd)
    ids = {e["id"] for e in resolved["entities"]}
    # SRD hit links to the shared id — no per-session copy entity emitted
    assert "RULE_CLASS_Bard" not in ids
    # non-SRD rule minted with subtype prefix
    assert any(i.startswith("RULE_SYSTEM_") for i in ids)
    # session-scoped roll/decision ids
    assert "ROLL_2025-03-26_DodoAttackRoll" in ids
    assert "DEC_2025-03-26_RitualBewusstFalsch" in ids
    edges = {(e["start_id"], e["type"], e["end_id"]) for e in resolved["edges"]}
    assert ("CHAR_Dodo", "ROLLED", "ROLL_2025-03-26_DodoAttackRoll") in edges
    assert ("ROLL_2025-03-26_DodoAttackRoll", "TARGETS", "CHAR_Monster") in edges
    assert ("CHAR_LindoLaut", "DECIDED", "DEC_2025-03-26_RitualBewusstFalsch") in edges
    # causal chain: decision TRIGGERED monster; PC HAS_CLASS shared SRD node
    assert ("DEC_2025-03-26_RitualBewusstFalsch", "TRIGGERED", "CHAR_Monster") in edges
    assert ("CHAR_LindoLaut", "HAS_CLASS", "RULE_CLASS_Bard") in edges


def test_registry_write_back():
    r = _tmp_resolver()
    r.resolve("Knurrender Bär", "Character")
    r.save()
    saved = json.loads(r.path.read_text(encoding="utf-8"))
    assert any(e["canonical"] == "Knurrender Bär" for e in saved["characters"].values())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all resolve invariants pass")
