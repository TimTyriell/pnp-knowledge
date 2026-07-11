"""Load a Session_Report_*.md's embedded JSON graph (the trailing ```json
appendix```) straight into its own Neo4j (:7689 by default) — no LLM, no
chunking, the report is already a curated graph. Generic :Entity nodes
(matches the report's mixed node types: Character/Location/RuleEntity/...)
rather than src/pnp_graph/schema.py's typed schema, which this doesn't fit.
"""

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))

from neo4j import GraphDatabase  # noqa: E402

from pnp_graph.chunking import session_id_from_path  # noqa: E402
from pnp_graph.store import sanitize_predicate  # noqa: E402

REPORT_NEO4J_URL = os.environ.get("REPORT_NEO4J_URL", "bolt://localhost:7689")
DEFAULT_REPORT = Path(__file__).resolve().parent / "Session_Report_S01_2025-03-26.md"

_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_embedded_graph(md_text: str) -> dict:
    """Pull the last fenced ```json block out of a session report."""
    matches = _JSON_FENCE_RE.findall(md_text)
    if not matches:
        raise ValueError("no ```json appendix found in report")
    return json.loads(matches[-1])


def _ensure_constraint(tx) -> None:
    tx.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")


def _write_graph(tx, graph: dict, session_id: str) -> None:
    for n in graph.get("nodes", []):
        tx.run(
            "MERGE (e:Entity {id: $id}) "
            "SET e.type = $type, e.name = $name, e.aliases = $aliases, "
            "e.evidence_scenes = $evidence_scenes, e.attributes_json = $attributes_json, "
            "e.session_id = $sid",
            id=n["id"], type=n.get("type", ""), name=n.get("name", ""),
            aliases=n.get("aliases", []), evidence_scenes=n.get("evidence_scenes", []),
            attributes_json=json.dumps(n.get("attributes", {})), sid=session_id,
        )
    for e in graph.get("edges", []):
        rel = sanitize_predicate(str(e.get("relation", "")))
        # rel is [A-Z0-9_] only (sanitize_predicate), safe to interpolate as rel type.
        tx.run(
            f"MATCH (a:Entity {{id: $s}}), (b:Entity {{id: $o}}) "
            f"MERGE (a)-[r:`{rel}`]->(b) "
            f"SET r.confidence = $confidence, r.evidence_scenes = $evidence_scenes, r.session_id = $sid",
            s=e["source"], o=e["target"],
            confidence=e.get("confidence", ""), evidence_scenes=e.get("evidence_scenes", []),
            sid=session_id,
        )


def load_report(md_path: Path) -> tuple[int, int]:
    """Load one report's embedded graph into REPORT_NEO4J_URL. Returns (node_count, edge_count)."""
    graph = _extract_embedded_graph(md_path.read_text(encoding="utf-8"))
    session_id = session_id_from_path(md_path)
    driver = GraphDatabase.driver(REPORT_NEO4J_URL, auth=None)  # container runs NEO4J_AUTH=none
    try:
        driver.verify_connectivity()  # fail fast if the container isn't up
        with driver.session() as db:
            db.execute_write(_ensure_constraint)
            db.execute_write(_write_graph, graph, session_id)
    finally:
        driver.close()
    return len(graph.get("nodes", [])), len(graph.get("edges", []))


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REPORT
    n_nodes, n_edges = load_report(path)
    print(f"Loaded {path.name} -> {REPORT_NEO4J_URL}: {n_nodes} nodes, {n_edges} edges")
