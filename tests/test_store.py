"""Supersede-query invariants for WP9 state-edge lifecycle (no Neo4j; fake db)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pnp_graph.store import _write_graph


class _FakeDB:
    """Captures every Cypher call instead of running it."""

    def __init__(self):
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))
        class _Result:
            def single(self):
                return {"c": 0}
        return _Result()


def _resolved(edges=(), entities=()):
    return {"entities": list(entities), "edges": list(edges)}


def test_supersede_fires_for_keyed_state_predicate():
    # LOCATED_IN keys on 'start': a new location for the same character must
    # close the prior open edge.
    db = _FakeDB()
    edge = {"start_id": "CHAR_Cookie", "end_id": "LOC_Wald", "type": "LOCATED_IN",
            "props": {"session_id": "2025-04-01", "confidence": "high", "valid_from": 2}}
    _write_graph(db, _resolved([edge]))
    supersede_calls = [c for c in db.calls if "old.valid_to" in c[0]]
    assert len(supersede_calls) == 1
    query, params = supersede_calls[0]
    assert "(k:Entity {id: $key_id})-[old:LOCATED_IN]->(o:Entity)" in query
    # LOCATED_IN is exclusive only for Character/Item positions (audit_v7pro §7):
    # a source-type guard keeps Location->Location geography open.
    assert "k.type IN $src_types" in query
    assert params["key_id"] == "CHAR_Cookie"
    assert params["other_id"] == "LOC_Wald"
    assert params["valid_from"] == 2
    assert sorted(params["src_types"]) == ["Character", "Item"]


def test_supersede_skipped_for_stable_predicate():
    # AT_LOCATION / HAS_CLASS are STABLE (audit_v7pro §7) — no longer keyed,
    # so they must not emit a supersede query even though they carry valid_from.
    db = _FakeDB()
    edge = {"start_id": "EVT_Kampf", "end_id": "LOC_Wald", "type": "AT_LOCATION",
            "props": {"session_id": "2025-04-01", "confidence": "high", "valid_from": 2}}
    _write_graph(db, _resolved([edge]))
    assert not any("old.valid_to" in c[0] for c in db.calls)


def test_supersede_skipped_for_non_exclusive_predicate():
    # MEMBER_OF has no cardinality-one key (not exclusive) -> no supersede query.
    db = _FakeDB()
    edge = {"start_id": "CHAR_Cookie", "end_id": "FACTION_Krähen", "type": "MEMBER_OF",
            "props": {"session_id": "2025-04-01", "confidence": "high", "valid_from": 2}}
    _write_graph(db, _resolved([edge]))
    assert not any("old.valid_to" in c[0] for c in db.calls)


def test_supersede_skipped_without_valid_from():
    # Event-classified/off-vocab edges never carry valid_from -> no supersede query.
    db = _FakeDB()
    edge = {"start_id": "CHAR_Cookie", "end_id": "CHAR_Dodo", "type": "KILLED",
            "props": {"session_id": "2025-04-01", "confidence": "high"}}
    _write_graph(db, _resolved([edge]))
    assert not any("old.valid_to" in c[0] for c in db.calls)


def test_entity_write_splits_create_and_match_props():
    # A re-mention with no new description/aliases must not blank out what a
    # prior session already wrote — ON MATCH drops empty-string/empty-list
    # values entirely; ON CREATE still writes them (nothing yet to preserve).
    db = _FakeDB()
    entity = {"id": "CHAR_Monster", "type": "Character",
              "props": {"session_id": "2025-04-01", "confidence": "medium",
                        "description": "", "aliases": [], "is_pc": False}}
    _write_graph(db, _resolved(entities=[entity]))
    (query, params), = [c for c in db.calls if "MERGE (n:Entity" in c[0]]
    assert "description" in params["create_props"] and params["create_props"]["description"] == ""
    assert "aliases" in params["create_props"] and params["create_props"]["aliases"] == []
    assert "description" not in params["match_props"]
    assert "aliases" not in params["match_props"]
    assert params["match_props"]["is_pc"] is False  # non-empty/falsy-but-meaningful values pass through


def test_entity_write_keeps_non_empty_values_in_match_props():
    db = _FakeDB()
    entity = {"id": "CHAR_Monster", "type": "Character",
              "props": {"session_id": "2025-04-01", "confidence": "medium",
                        "description": "Spielt oft Musik", "aliases": ["Monsterchen"]}}
    _write_graph(db, _resolved(entities=[entity]))
    (query, params), = [c for c in db.calls if "MERGE (n:Entity" in c[0]]
    assert params["match_props"]["description"] == "Spielt oft Musik"
    assert params["match_props"]["aliases"] == ["Monsterchen"]


def test_pending_notes_appended_via_coalesce_not_overwritten():
    # WP13.4: pending_notes must accumulate across sessions (coalesce + concat),
    # never go through the blind n += props path like other properties.
    db = _FakeDB()
    entity = {"id": "CHAR_Monster", "type": "Character",
              "props": {"session_id": "2025-04-01", "confidence": "medium",
                        "pending_notes": ["misstraut Fremden"]}}
    _write_graph(db, _resolved(entities=[entity]))
    (merge_query, merge_params), = [c for c in db.calls if "MERGE (n:Entity" in c[0]]
    assert "pending_notes" not in merge_params["create_props"]
    assert "pending_notes" not in merge_params["match_props"]
    (notes_query, notes_params), = [c for c in db.calls if "pending_notes" in c[0]]
    assert "coalesce(n.pending_notes, [])" in notes_query
    assert notes_params == {"id": "CHAR_Monster", "notes": ["misstraut Fremden"]}


def test_no_pending_notes_query_when_notes_empty():
    db = _FakeDB()
    entity = {"id": "CHAR_Monster", "type": "Character",
              "props": {"session_id": "2025-04-01", "confidence": "medium", "pending_notes": []}}
    _write_graph(db, _resolved(entities=[entity]))
    assert not any("pending_notes" in c[0] for c in db.calls)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all store invariants pass")
