"""reconcile-report (docs/evolution/07, WP8): diff the hand-authored report
graph (gold, the trailing ```json appendix of Session_Report_*.md) against the
local pipeline's graph on :7687 for the same session.

Reports three things:
- recall gaps  — report entities/edges the local run missed entirely
- id mismatches — same entity under a different id ⇒ an alias-registry hole,
  printed as a suggested data/alias_registry.json addition (never auto-applied)
- confidence disagreements on shared edges
"""

import json
import logging
import re
from pathlib import Path

from neo4j import GraphDatabase

from .config import NEO4J_URL, REPO_ROOT
from .resolve import _TYPE_MAP, map_predicate, normalize

log = logging.getLogger("pnp_graph.reconcile")

_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_SKIP_TYPES = {"Session"}  # structural, ids are scheme-specific by design


def _find_report(session_id: str) -> Path:
    for base in (REPO_ROOT, REPO_ROOT / "reports"):
        hits = sorted(base.glob(f"Session_Report_*_{session_id}.md"))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"no Session_Report_*_{session_id}.md in {REPO_ROOT} or reports/")


def _report_graph(session_id: str) -> dict:
    text = _find_report(session_id).read_text(encoding="utf-8")
    matches = _JSON_FENCE_RE.findall(text)
    if not matches:
        raise ValueError("no ```json appendix found in report")
    return json.loads(matches[-1])


def _local_graph(session_id: str) -> tuple[dict, list]:
    """(entities by id, edges) from :7687. All entities (for the name map —
    SRD/cross-session targets are legitimate), edges filtered to the session."""
    driver = GraphDatabase.driver(NEO4J_URL, auth=None)
    try:
        driver.verify_connectivity()
        with driver.session() as db:
            nodes = {r["id"]: r.data() for r in db.run(
                "MATCH (n:Entity) RETURN n.id AS id, n.type AS type, n.name AS name, "
                "coalesce(n.aliases, []) AS aliases")}
            edges = [r.data() for r in db.run(
                "MATCH (a:Entity)-[r]->(b:Entity) WHERE r.session_id = $sid "
                "RETURN a.id AS source, type(r) AS relation, b.id AS target, "
                "r.confidence AS confidence", sid=session_id)]
    finally:
        driver.close()
    return nodes, edges


def reconcile(session_id: str) -> dict:
    report = _report_graph(session_id)
    local_nodes, local_edges = _local_graph(session_id)

    name_to_local: dict[str, str] = {}
    for n in local_nodes.values():
        for surface in (n["name"], *n["aliases"]):
            if surface:
                name_to_local.setdefault(normalize(surface), n["id"])

    node_gaps, id_mismatches, alias_suggestions = [], [], []
    report_to_local: dict[str, str] = {}
    for n in report.get("nodes", []):
        if n.get("type") in _SKIP_TYPES:
            continue
        surfaces = [n.get("name", ""), *n.get("aliases", [])]
        local_id = next((name_to_local[normalize(s)] for s in surfaces
                         if s and normalize(s) in name_to_local), None)
        if local_id is None:
            node_gaps.append(f'{n["id"]} ({n.get("type")}: {n.get("name")})')
        else:
            report_to_local[n["id"]] = local_id
            if n["id"] != local_id:
                id_mismatches.append(f'{n["id"]} -> {local_id}')
                section = _TYPE_MAP.get(n.get("type", ""), (None, None))[1]
                if section:
                    alias_suggestions.append(
                        {"section": section, "id": local_id, "add_alias": n.get("name", "")})

    local_edge_set = {(e["source"], e["relation"], e["target"]): e for e in local_edges}
    edge_gaps, confidence_diffs = [], []
    for e in report.get("edges", []):
        s = report_to_local.get(e["source"])
        t = report_to_local.get(e["target"])
        rel, _ = map_predicate(str(e.get("relation", "")))
        if s is None or t is None:
            continue  # endpoint already counted as a node gap
        hit = local_edge_set.get((s, rel, t))
        if hit is None:
            edge_gaps.append(f'{e["source"]} -{e.get("relation")}-> {e["target"]}')
        elif hit["confidence"] and e.get("confidence") and hit["confidence"] != e["confidence"]:
            confidence_diffs.append(
                f'{s} -{rel}-> {t}: report={e["confidence"]} local={hit["confidence"]}')

    return {"report_nodes": len(report.get("nodes", [])),
            "report_edges": len(report.get("edges", [])),
            "node_gaps": node_gaps, "edge_gaps": edge_gaps,
            "id_mismatches": id_mismatches, "alias_suggestions": alias_suggestions,
            "confidence_diffs": confidence_diffs}


def print_reconciliation(session_id: str) -> None:
    r = reconcile(session_id)
    print(f"reconcile-report {session_id}: report has {r['report_nodes']} nodes / "
          f"{r['report_edges']} edges")
    print(f"\nRECALL GAPS — {len(r['node_gaps'])} report entities missing locally:")
    for g in r["node_gaps"]:
        print(f"  - {g}")
    print(f"\nEDGE GAPS — {len(r['edge_gaps'])} report edges missing locally:")
    for g in r["edge_gaps"]:
        print(f"  - {g}")
    print(f"\nID MISMATCHES — {len(r['id_mismatches'])} (same entity, different id):")
    for m in r["id_mismatches"]:
        print(f"  - {m}")
    if r["alias_suggestions"]:
        print("\nSuggested alias_registry.json additions (apply manually):")
        print(json.dumps(r["alias_suggestions"], ensure_ascii=False, indent=2))
    if r["confidence_diffs"]:
        print(f"\nCONFIDENCE DISAGREEMENTS — {len(r['confidence_diffs'])}:")
        for c in r["confidence_diffs"]:
            print(f"  - {c}")
