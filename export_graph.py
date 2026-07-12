"""One-off Neo4j graph export to JSON (nodes + relationships), no embeddings.

Same {"nodes": [...], "props": ...} shape as docs/data_export/*/neo4j_export*.json
(Neo4j Browser's own export format) so existing tooling/diffing still works.

Usage: python export_graph.py [output.json] [--uri bolt://localhost:7687]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from neo4j import GraphDatabase

from pnp_graph.config import NEO4J_URL


def export_graph(uri: str, out_path: Path) -> None:
    driver = GraphDatabase.driver(uri, auth=None)
    with driver.session() as db:
        nodes = [
            {"id": r["id"], "labels": r["labels"],
             "props": {k: v for k, v in r["props"].items() if k != "embedding"}}
            for r in db.run(
                "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props")
        ]
        rels = [
            {"id": r["id"], "type": r["type"], "start": r["start"], "end": r["end"], "props": r["props"]}
            for r in db.run(
                "MATCH (a)-[rel]->(b) RETURN elementId(rel) AS id, type(rel) AS type, "
                "elementId(a) AS start, elementId(b) AS end, properties(rel) AS props")
        ]
    driver.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"nodes": nodes, "relationships": rels}, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"exported {len(nodes)} nodes, {len(rels)} relationships -> {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("output", nargs="?", default="docs/data_export/neo4j_export.json")
    ap.add_argument("--uri", default=NEO4J_URL)
    args = ap.parse_args()
    export_graph(args.uri, Path(args.output))
