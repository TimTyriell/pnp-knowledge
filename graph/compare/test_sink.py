"""Self-check for run_both._write_triples: malformed triples dropped, predicates
sanitized into safe Cypher rel types. No Neo4j needed (stub tx). Run:

    python compare/test_sink.py
"""

from run_both import _write_triples


class FakeTx:
    def __init__(self):
        self.queries = []

    def run(self, cypher, **params):
        self.queries.append((cypher, params))


def test_filters_and_sanitizes():
    triples = [
        {"subject": "james watt", "predicate": "developed", "object": "steam engine"},
        {"subject": "a", "object": "b", "predicate": "is a / kind-of!"},  # messy predicate
        {"subject": "only subject"},          # malformed: no object -> dropped
        "not a dict",                          # malformed -> dropped
        {"subject": "x", "object": "y", "predicate": "", "inferred": True},  # empty pred
    ]
    tx = FakeTx()
    _write_triples(tx, triples, "2025-03-26")

    merges = [q for q, _ in tx.queries if "MERGE (a:Entity" in q]
    assert len(merges) == 3, f"expected 3 valid triples merged, got {len(merges)}"

    # every interpolated rel type is [A-Z0-9_] only, and empty predicate -> fallback
    import re
    for q in merges:
        m = re.search(r"\[r:`([^`]*)`\]", q)
        assert m, f"no rel type in: {q}"
        assert re.fullmatch(r"[A-Z0-9_]+", m.group(1)), f"unsafe rel type: {m.group(1)}"
    assert any("RELATES_TO" in q for q in merges), "empty predicate should fall back to RELATES_TO"
    print("ok: 3 valid triples, all rel types safe, empty-predicate fallback works")


if __name__ == "__main__":
    test_filters_and_sanitizes()
