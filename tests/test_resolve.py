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
from pnp_graph.resolve import (Resolver, is_out_of_world, map_predicate, normalize,
                               normalize_confidence, predicate_class, resolve_graph, slug)
from pnp_graph.schema import (Character, Decision, Event, Faction, GraphExtraction, Item,
                              Location, Relationship, RuleEntity)
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
    # GM-is-world: the GM gets NO character node and no PLAYS entry
    assert set(info["characters"]) == {"CHAR_LindoLaut", "CHAR_Dodo", "CHAR_Cookie"}
    assert info["plays"]["PLAYER_Tim"] == "CHAR_LindoLaut"
    assert "PLAYER_Deniz" not in info["plays"]
    assert info["players"]["PLAYER_Deniz"]["role"] == "GM"


def test_resolve_variants_collapse_to_one_id():
    r = _tmp_resolver()
    a = r.resolve("der Schleichfurz", "Character")
    assert a == r.resolve("Schleichfurz ", "Character")   # normalized hit
    assert a == r.resolve("Schleichfurtz", "Character")   # fuzzy hit (typo)
    assert a == r.resolve("Schleichfurz", "Character")


def test_pc_keeps_char_prefix_npc_mints_npc_prefix():
    # PC vs NPC is deterministic from the cast: a seeded player-character keeps
    # CHAR_; any other character mints NPC_ (both stay type Character downstream).
    r = _tmp_resolver()
    assert r.resolve("Lindo Laut", "Character") == "CHAR_LindoLaut"   # cast PC
    assert r.resolve("Ganz Neuer Wicht", "Character").startswith("NPC_")  # fresh NPC


def test_resolve_never_crosses_type():
    r = _tmp_resolver()
    loc = r.resolve("Daggerheart", "Location")
    fac = r.resolve("Daggerheart", "Faction")
    assert loc != fac and loc.startswith("LOC_") and fac.startswith("FACTION_")


def test_alias_hit_beats_minting():
    r = _tmp_resolver()
    assert r.resolve("Lindo", "Character") == "CHAR_LindoLaut"  # seeded alias
    # 'GM' is a player alias now (gm-is-world) — resolves to the player, never a char
    assert r.resolve("GM", "Character") == "PLAYER_Deniz"


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
            Character(name="Lindo Laut", role="PC", is_named_character=True),
            Character(name="Tim (Lindo Laut)", role="PC", is_named_character=True),   # composite must not fork
            Character(name="Marco", role="PC", is_named_character=True),               # player name must not fork
        ],
        items=[Item(name="Zauberstab", owner="Lindo", is_named_artifact=True)],
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
    # in-fiction edges never land on a Player (only PLAYS/DIRECTS may touch PLAYER_*)
    for (s, t, o) in edges:
        if t not in ("PLAYS", "DIRECTS"):
            assert not s.startswith("PLAYER_") and not o.startswith("PLAYER_")
    # every node and edge carries provenance
    for e in resolved["entities"]:
        assert e["props"]["session_id"] and e["props"]["confidence"]
    for e in resolved["edges"]:
        assert e["props"]["session_id"] and e["props"]["confidence"]


def test_evidence_chunks():
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        characters=[Character(name="Lindo Laut", role="PC", is_named_character=True)],
        relationships=[
            Relationship(subject="Lindo Laut", predicate="KNOWS", object="Cookie",
                         confidence="high", evidence=2),
        ],
    )
    evidence = {
        ("characters", "Lindo Laut"): [1, 2],
        ("relationships", ("Lindo Laut", "KNOWS", "Cookie")): [2],
    }
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1, evidence=evidence)
    by_id = {e["id"]: e for e in resolved["entities"]}
    # extracted fact stamped with the chunks it was seen in
    assert by_id["CHAR_LindoLaut"]["props"]["evidence_chunks"] == [1, 2]
    edges = {(e["start_id"], e["type"], e["end_id"]): e for e in resolved["edges"]}
    # relationship carries evidence_chunks (from the sidecar)
    rel = edges[("CHAR_LindoLaut", "KNOWS", "CHAR_Cookie")]
    assert rel["props"]["evidence_chunks"] == [2]


def test_record_evidence_sidecar():
    from pnp_graph.extract import _record_evidence
    ev: dict = {}
    g = GraphExtraction(
        characters=[Character(name="Dodo", role="PC", is_named_character=True)],
        relationships=[Relationship(subject="Dodo", predicate="KNOWS", object="Cookie",
                                    confidence="high")],
    )
    _record_evidence(ev, g, 1)
    _record_evidence(ev, g, 3)
    assert ev[("characters", "Dodo")] == [1, 3]
    assert ev[("relationships", ("Dodo", "KNOWS", "Cookie"))] == [1, 3]


def test_srd_rules_decisions():
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    srd = SrdIndex()
    extraction = GraphExtraction(
        rule_entities=[
            RuleEntity(name="Barde", subtype="Class"),          # German alias -> SRD id
            RuleEntity(name="Hausregel Xyz", subtype="System"), # not in SRD -> minted
        ],
        decisions=[
            Decision(name="Ritual bewusst falsch", decided_by="Lindo Laut",
                     quote="wir machen es falsch", consequence="Monster erscheint",
                     confidence="high"),
        ],
        characters=[Character(name="Monster", role="NPC", is_named_character=True)],
        relationships=[
            Relationship(subject="Lindo Laut", predicate="HAS_CLASS", object="Barde",
                         confidence="high"),
            Relationship(subject="Ritual bewusst falsch", predicate="TRIGGERED",
                         object="Monster", confidence="high"),
        ],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1,
                             evidence={}, srd_index=srd)
    ids = {e["id"] for e in resolved["entities"]}
    # SRD hit links to the shared id — no per-session copy entity emitted
    assert "RULE_CLASS_Bard" not in ids
    # non-SRD rule minted with subtype prefix
    assert any(i.startswith("RULE_SYSTEM_") for i in ids)
    # session-scoped decision id
    assert "DEC_2025-03-26_RitualBewusstFalsch" in ids
    edges = {(e["start_id"], e["type"], e["end_id"]) for e in resolved["edges"]}
    assert ("CHAR_LindoLaut", "DECIDED", "DEC_2025-03-26_RitualBewusstFalsch") in edges
    # causal chain: decision TRIGGERED monster; PC HAS_CLASS shared SRD node
    assert ("DEC_2025-03-26_RitualBewusstFalsch", "TRIGGERED", "NPC_Monster") in edges
    assert ("CHAR_LindoLaut", "HAS_CLASS", "RULE_CLASS_Bard") in edges


def test_chunk_passages_minted_and_linked_via_mentions():
    # WP13.5: passing raw chunk texts mints searchable Chunk passages and
    # links every entity seen in that scene to its passage(s) via MENTIONS.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        characters=[Character(name="Monster", role="NPC", is_named_character=True)],
    )
    evidence = {("characters", "Monster"): [1]}
    chunk_texts = ["[00:00] GM:\n  Ein Monster taucht auf.\n\n"]
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1,
                             evidence=evidence, chunk_texts=chunk_texts)
    chunk_entities = [e for e in resolved["entities"] if e["type"] == "Chunk"]
    assert len(chunk_entities) == 1
    assert chunk_entities[0]["id"] == "CHUNK_2025-03-26_001_01"
    assert "Monster taucht auf" in chunk_entities[0]["props"]["text"]
    edges = {(e["start_id"], e["type"], e["end_id"]) for e in resolved["edges"]}
    assert ("CHUNK_2025-03-26_001_01", "IN_SESSION", "SESS_2025-03-26") in edges
    assert ("CHUNK_2025-03-26_001_01", "MENTIONS", "NPC_Monster") in edges


def test_no_chunk_passages_without_chunk_texts_arg():
    # backward compatible: omitting `chunk_texts` (existing callers/tests) mints nothing.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    resolved = resolve_graph(r, GraphExtraction(), "2025-03-26", info, seq=1)
    assert not any(e["type"] == "Chunk" for e in resolved["entities"])


def test_character_description_becomes_pending_notes_not_description():
    # WP13.4: raw per-scene notes never land straight on `description` — they
    # accumulate in `pending_notes` until cli summarize-entities folds them.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        characters=[Character(name="Lindo Laut", role="PC", is_named_character=True, description="spielt oft Musik")],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    char = next(e for e in resolved["entities"] if e["id"] == "CHAR_LindoLaut")
    assert char["props"]["pending_notes"] == ["spielt oft Musik"]
    assert "description" not in char["props"]


def test_pending_notes_accumulate_within_session_for_aliased_mentions():
    # 'Lindo Laut' and 'Lindo' (a seeded alias) resolve to the same character —
    # a note attached to either surface form must not shadow the other's.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        characters=[
            Character(name="Lindo Laut", role="PC", is_named_character=True, description="spielt oft Musik"),
            Character(name="Lindo", role="PC", is_named_character=True, description="misstraut Fremden"),
        ],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    char = next(e for e in resolved["entities"] if e["id"] == "CHAR_LindoLaut")
    assert char["props"]["pending_notes"] == ["spielt oft Musik", "misstraut Fremden"]


def test_no_pending_notes_when_no_description():
    # matches the aliases/evidence_chunks precedent: an empty list is never
    # written as a key at all, not stored as `[]`.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(characters=[Character(name="Lindo Laut", role="PC", is_named_character=True)])
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    char = next(e for e in resolved["entities"] if e["id"] == "CHAR_LindoLaut")
    assert char["props"].get("pending_notes", []) == []


def test_gm_is_world():
    # GM-is-world: no GM Character node exists; the GM player's ONLY edge is
    # DIRECTS -> Session; every extracted edge aimed at a GM surface is dropped.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        characters=[Character(name="GM", role="NPC", is_named_character=True)],  # model minting the GM
        events=[Event(label="Kampfbeginn", participants=["Deniz", "Dodo"],
                      narrative_significance_reasoning="Kampf beginnt")],
        decisions=[Decision(name="Monster flieht", decided_by="Deniz", confidence="high")],
        relationships=[Relationship(subject="Deniz", predicate="KNOWS", object="Dodo",
                                    confidence="high")],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    ids = {e["id"] for e in resolved["entities"]}
    assert "CHAR_Deniz_GM" not in ids and not any("GM" in i for i in ids if i.startswith("CHAR_"))
    edges = {(e["start_id"], e["type"], e["end_id"]) for e in resolved["edges"]}
    assert ("PLAYER_Deniz", "DIRECTS", "SESS_2025-03-26") in edges
    # DIRECTS is the GM player's only edge
    gm_edges = [(s, t, o) for s, t, o in edges if s == "PLAYER_Deniz" or o == "PLAYER_Deniz"]
    assert gm_edges == [("PLAYER_Deniz", "DIRECTS", "SESS_2025-03-26")]
    # the PC keeps its PARTICIPATED_IN; GM roll/decision edges are gone
    assert any(t == "PARTICIPATED_IN" and s == "CHAR_Dodo" for s, t, _ in edges)
    assert not any(t in ("ROLLED", "DECIDED", "KNOWS") and "Deniz" in s for s, t, _ in edges)
    assert any(d["reason"] == "gm-is-world" for d in resolved["dropped"])


def test_ooc_denylist():
    assert is_out_of_world("Twitch-Raid")
    assert is_out_of_world("Würfelwächter (Twitch chat)")
    assert not is_out_of_world("Lindo Laut")


def test_ooc_character_dropped_not_minted():
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(characters=[Character(name="Twitch Raid Bot", role="NPC", is_named_character=True)])
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    assert not any(e["type"] == "Character" and "Twitch" in e["props"]["name"]
                   for e in resolved["entities"])
    assert any("out-of-world" in d["reason"] for d in resolved["dropped"])


def test_generic_mob_never_minted():
    # macro-graph gate (like is_named_artifact): generic combat fodder is
    # identity-unstable and earns no node — dropped whether the model flags it
    # (is_named_character=False) or the deterministic backstop catches it.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(characters=[
        Character(name="Goblin-Wache", role="NPC", is_named_character=True),   # backstop (term)
        Character(name="ein Bauer", role="NPC", is_named_character=False),      # schema gate
        Character(name="Berthold", role="NPC", is_named_character=True),        # named NPC survives
    ])
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    names = {e["props"]["name"] for e in resolved["entities"] if e["type"] == "Character"}
    assert "Berthold" in names
    assert not any("Goblin" in n or "Bauer" in n for n in names)
    assert sum(d["reason"].startswith("generic mob") for d in resolved["dropped"]) == 2


def test_generic_place_never_minted():
    # named-place gate (like is_named_character): generic stage-dressing earns no
    # node — dropped by the model flag (is_named_location=False) or the backstop.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(locations=[
        Location(name="der Wald", is_named_location=True),    # backstop (generic term)
        Location(name="ein Raum", is_named_location=False),   # schema gate
        Location(name="Breschka", is_named_location=True),    # real place survives
    ])
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    names = {e["props"]["name"] for e in resolved["entities"] if e["type"] == "Location"}
    assert "Breschka" in names
    assert not any("Wald" in n or "Raum" in n for n in names)
    assert sum(d["reason"].startswith("generic place") for d in resolved["dropped"]) == 2


def test_events_never_persisted_to_registry():
    # An event is a one-off happening: it resolves in-memory but is never written
    # to the registry (kills bloat + cross-session false-merges of same-title scenes).
    tmp = Path(tempfile.mkdtemp()) / "reg.json"
    tmp.write_text("{}", encoding="utf-8")
    r = Resolver(tmp)
    r.resolve("Monster is defeated", "Event")
    assert r.registry["events"]           # minted in-memory
    r._dirty = True
    r.save()
    assert json.loads(tmp.read_text(encoding="utf-8")).get("events", {}) == {}  # not on disk


def test_gm_fuzzy_match_catches_asr_noise():
    # 'Dennis' for 'Deniz' — the same ASR mangling pattern that produced
    # CHAR_Kieler in the diagnostic run; is_gm_surface must fuzzy-match it.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(characters=[Character(name="Dennis", role="NPC", is_named_character=True)])
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    ids = {e["id"] for e in resolved["entities"]}
    assert not any("Dennis" in i for i in ids)
    assert any(d["reason"] == "gm-is-world" for d in resolved["dropped"])


def test_domain_range_violation_dropped():
    # 'X MEMBER_OF Y' (Character->Character) — MEMBER_OF's range is Faction,
    # not Character, so this must never become an edge.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        relationships=[Relationship(subject="Cookie", predicate="MEMBER_OF", object="Dodo",
                                    confidence="high")],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    assert not any(e["type"] == "MEMBER_OF" for e in resolved["edges"])
    assert any("domain/range" in d["reason"] for d in resolved["dropped"])


def test_domain_range_valid_edge_passes():
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        factions=[Faction(name="Wuerfelwaechter-Gilde")],
        relationships=[Relationship(subject="Cookie", predicate="MEMBER_OF",
                                    object="Wuerfelwaechter-Gilde", confidence="high")],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    assert any(e["type"] == "MEMBER_OF" and e["start_id"] == "CHAR_Cookie"
               for e in resolved["edges"])


def test_mentioned_in_off_vocab():
    assert map_predicate("MENTIONED_IN") == ("RELATES_TO", False)


def test_event_gate_drops_meta_and_roll_events():
    from pnp_graph.resolve import event_gate
    players = ["Tim", "Marco", "Celin", "Deniz"]
    # meta/rules talk
    assert event_gate("Clarification of Hope Point Rule", set(), players)
    assert event_gate("Explanation of Support Mechanics", set(), players)
    assert event_gate("Mention of Bardic Inspiration", set(), players)
    assert event_gate("Lindo Laut considers healing or using armor", set(), players)
    assert event_gate("Hope-Punkt-Regel erläutert", set(), players)
    # roll-shaped (RollEvent covers these)
    assert event_gate("Cookie rolls on Presence", set(), players)
    assert event_gate("Presence roll initiated by Celin", set(), players)
    # player name as actor
    assert event_gate("Marco takes the hit instead of Dodo", set(), players)
    # duplicates a quest
    from pnp_graph.resolve import normalize
    assert event_gate("Defeating the Monster", {normalize("Defeating the Monster")}, players)
    # real state-change events pass — and 'Schriftrolle' is NOT roll-shaped
    assert event_gate("Monster Tentacle Severed", set(), players) is None
    assert event_gate("Schriftrolle gefunden", set(), players) is None
    assert event_gate("Dodo moves the Pott", set(), players) is None


def test_rule_subtype_clamp():
    # off-enum subtypes ('diceroll', 'weapon trait', ...) never mint; enum +
    # 'game'-prefixed variants do; SRD hits bypass the clamp entirely.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    srd = SrdIndex()
    extraction = GraphExtraction(rule_entities=[
        RuleEntity(name="2w12", subtype="diceroll"),          # off-enum -> dropped
        RuleEntity(name="reliable", subtype="weapon trait"),  # off-enum -> dropped
        RuleEntity(name="Hausregel Xyz", subtype="game-mechanic"),  # game+enum -> minted
        RuleEntity(name="Tend to All Wounds", subtype="game-rule"),  # SRD alias -> shared node
    ])
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1, srd_index=srd)
    ids = {e["id"] for e in resolved["entities"]}
    assert not any("2w12" in i.lower() or "reliable" in i.lower() for i in ids)
    assert any(i.startswith("RULE_GAMEMECHANIC_") for i in ids)
    assert sum(1 for d in resolved["dropped"] if d["reason"] == "off-enum rule subtype") == 2
    # SRD alias resolved to the shared Long Rest node, no per-session mint
    assert not any("tendtoallwounds" in i.lower() for i in ids)


def test_cross_type_collision_first_seen_wins():
    # run-2/3 QA blocker: 'Auftraggeber' extracted as Location in one chunk and
    # Faction in another must become ONE node (first-seen type, unioned
    # evidence), with no second registry mint. Registry-level same-name across
    # types (test_resolve_never_crosses_type) stays legal — this guard is
    # session-scoped only.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        locations=[Location(name="Auftraggeber", is_named_location=True)],   # processed before factions
        factions=[Faction(name="Auftraggeber")],
    )
    evidence = {("locations", "Auftraggeber"): [2], ("factions", "Auftraggeber"): [7]}
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1, evidence=evidence)
    hits = [e for e in resolved["entities"]
            if normalize(e["props"].get("name", "")) == "auftraggeber"]
    assert len(hits) == 1
    assert hits[0]["type"] == "Location"  # first-seen wins
    assert hits[0]["props"]["evidence_chunks"] == [2, 7]  # evidence unioned
    assert "FACTION_Auftraggeber" not in r.registry["factions"]  # no second mint


def test_pc_never_duplicated_as_location():
    # baseline run 1 had CHAR_Esterossa AND LOC_Esterossa — same guard covers it:
    # a Location whose surface matches a cast character reuses the character id.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(locations=[Location(name="Cookie", is_named_location=True)])
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    assert not any(e["id"].startswith("LOC_Cookie") for e in resolved["entities"])


def test_registry_write_back():
    r = _tmp_resolver()
    r.resolve("Knurrender Bär", "Character")
    r.save()
    saved = json.loads(r.path.read_text(encoding="utf-8"))
    assert any(e["canonical"] == "Knurrender Bär" for e in saved["characters"].values())


def test_owns_swapped_to_owned_by():
    # WP9: OWNS (Character->Item) folds into the one ownership direction the
    # pipeline keeps, OWNED_BY (Item->Character) — one edge per fact to supersede.
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(
        items=[Item(name="Bogen", is_named_artifact=True)],
        relationships=[Relationship(subject="Cookie", predicate="OWNS", object="Bogen",
                                     confidence="high")],
    )
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=3)
    assert not any(e["type"] == "OWNS" for e in resolved["edges"])
    owned = [e for e in resolved["edges"] if e["type"] == "OWNED_BY"]
    assert len(owned) == 1
    assert owned[0]["start_id"] == "ITEM_Bogen"
    assert owned[0]["end_id"] == "CHAR_Cookie"
    assert owned[0]["props"]["valid_from"] == 3  # state predicate stamped with seq


def test_generic_item_not_minted():
    # Option A: only named/unique artifacts become nodes; generic loot is dropped
    # entirely (it lives in the vector store), a named artifact still mints.
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    r = _tmp_resolver()
    info = _cast_info(r)
    extraction = GraphExtraction(items=[
        Item(name="Fackel", is_named_artifact=False),
        Item(name="Schwert des Veritas", is_named_artifact=True),
    ])
    resolved = resolve_graph(r, extraction, "2025-03-26", info, seq=1)
    ids = {e["id"] for e in resolved["entities"]}
    assert not any(i.startswith("ITEM_Fackel") for i in ids)
    assert any(i.startswith("ITEM_SchwertDesVeritas") for i in ids)


def test_predicate_class():
    assert predicate_class("LOCATED_IN") == "state"
    assert predicate_class("OWNED_BY") == "state"
    assert predicate_class("MEMBER_OF") == "state"
    assert predicate_class("KILLED") == "event"
    assert predicate_class("FAMILY_OF") == "identity"
    assert predicate_class("RELATES_TO") is None
    assert predicate_class("PLAYS") is None  # exempt: own per-session history already


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all resolve invariants pass")
