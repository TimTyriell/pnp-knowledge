"""Pure self-check for load_report_graph's parsing (no Neo4j needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from load_report_graph import _extract_embedded_graph, DEFAULT_REPORT  # noqa: E402
from pnp_graph.store import sanitize_predicate  # noqa: E402

graph = _extract_embedded_graph(DEFAULT_REPORT.read_text(encoding="utf-8"))
assert graph["nodes"], "expected non-empty nodes"
assert graph["edges"], "expected non-empty edges"
assert all("id" in n for n in graph["nodes"]), "every node needs an id"
assert all("source" in e and "target" in e for e in graph["edges"]), "every edge needs source/target"

assert sanitize_predicate("hostile to!") == "HOSTILE_TO"

print(f"OK: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges parsed from {DEFAULT_REPORT.name}")
