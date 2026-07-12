"""Neo4j writes. Idempotent MERGE on canonical :Entity{id} (docs/evolution/02).

Input is the resolved dict from resolve.py — entities {id, type, props} and
edges {start_id, end_id, type, props}. Endpoints are MATCHed by id, never
MERGE-created: unresolvable endpoints were already dropped in resolve.py.
Versioning (valid_from/valid_to on state edges, WP9, docs/evolution/11):
resolve.py stamps valid_from = seq on state-predicate edges; _write_graph
here closes out the prior value (valid_to) on supersede, keyed per
config.STATE_PREDICATE_KEY.
"""

import logging
import re

from neo4j import GraphDatabase

from .config import NEO4J_URL, STATE_PREDICATE_KEY

log = logging.getLogger("pnp_graph.store")


def connect():
    driver = GraphDatabase.driver(NEO4J_URL, auth=None)  # container runs NEO4J_AUTH=none
    driver.verify_connectivity()  # fail fast if the container isn't up
    return driver


def sanitize_predicate(predicate: str) -> str:
    """Normalize a model-supplied predicate into a safe Cypher relationship type."""
    cleaned = re.sub(r"[^A-Z0-9_]", "_", predicate.strip().upper())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "RELATES_TO"


def ensure_constraints(db) -> None:
    # Retire the name-keyed constraints — they enforce the wrong key (docs/evolution/07).
    for old in ("character_name", "location_name", "faction_name"):
        db.run(f"DROP CONSTRAINT {old} IF EXISTS")
    db.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")
    db.run("CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.type)")
    db.run("CREATE INDEX entity_session IF NOT EXISTS FOR (n:Entity) ON (n.session_id)")


def _write_graph(db, resolved: dict) -> None:
    for e in resolved["entities"]:
        db.run(
            "MERGE (n:Entity {id: $id}) "
            "ON CREATE SET n += $props, n.type = $type, n.created_at = timestamp() "
            "ON MATCH  SET n += $props, n.type = $type, n.updated_at = timestamp()",
            id=e["id"], type=e["type"],
            props={k: v for k, v in e["props"].items() if v is not None},
        )
    for r in resolved["edges"]:
        rtype = sanitize_predicate(r["type"])
        # rtype passed sanitize + the ALLOWED_PREDICATES gate in resolve.py;
        # safe to interpolate (relationship types can't be parameterized).
        key_side = STATE_PREDICATE_KEY.get(rtype)
        if key_side and "valid_from" in r["props"]:
            # Supersede: close the prior open value on the cardinality-one
            # side before writing the new one, so a plain (non as-of) read
            # sees only the current fact (retrieve.py's default edge filter).
            key_id = r["start_id"] if key_side == "start" else r["end_id"]
            other_id = r["end_id"] if key_side == "start" else r["start_id"]
            pattern = (f"(k:Entity {{id: $key_id}})-[old:{rtype}]->(o:Entity)" if key_side == "start"
                       else f"(o:Entity)-[old:{rtype}]->(k:Entity {{id: $key_id}})")
            db.run(
                f"MATCH {pattern} "
                "WHERE o.id <> $other_id AND old.valid_to IS NULL "
                "SET old.valid_to = $valid_from",
                key_id=key_id, other_id=other_id, valid_from=r["props"]["valid_from"],
            )
        # session_id in the MERGE pattern -> one edge per session (PLAYS history etc.).
        db.run(
            f"MATCH (a:Entity {{id: $start}}), (b:Entity {{id: $end}}) "
            f"MERGE (a)-[rel:{rtype} {{session_id: $sid}}]->(b) "
            f"SET rel += $props",
            start=r["start_id"], end=r["end_id"],
            sid=r["props"]["session_id"], props=r["props"],
        )


def write_session(driver, resolved: dict) -> None:
    """Write one session's resolved graph in a single atomic transaction."""
    with driver.session() as db:
        db.execute_write(ensure_constraints)
        db.execute_write(_write_graph, resolved)


# QA queries from docs/evolution/07 — run after every write_session, results
# recorded in ingest_log.jsonl. Non-zero "must_be_zero" entries are blockers.
_QA_QUERIES = {
    "dup_names": (  # 1. duplicates after resolution
        "MATCH (a:Entity),(b:Entity) WHERE a.id < b.id "
        "AND toLower(a.name) = toLower(b.name) RETURN count(*) AS c"),
    "cross_type_names": (  # 2. same name across two types
        "MATCH (a:Entity),(b:Entity) WHERE a.id < b.id AND a.name = b.name "
        "AND a.type <> b.type RETURN count(*) AS c"),
    "missing_provenance": (  # 3. facts without provenance
        "MATCH ()-[r]->() WHERE r.confidence IS NULL OR r.session_id IS NULL "
        "RETURN count(r) AS c"),
    "rules_inconsistent": (  # 4. used domain card outside the PC's class domains
        "MATCH (pc:Entity{type:'Character'})-[:USES_CARD]->(c:Entity{subtype:'DomainCard'}) "
        "MATCH (pc)-[:HAS_CLASS]->(cl:Entity{subtype:'Class'}) "
        "WHERE c.domain IS NOT NULL AND cl.domains IS NOT NULL "
        "AND NOT c.domain IN cl.domains RETURN count(*) AS c"),
    "timeline_unlinked": (  # 5. Event/Roll/Decision without chunk provenance
        "MATCH (n:Entity) WHERE n.type IN ['Event','RollEvent','Decision'] "
        "AND n.evidence_chunks IS NULL RETURN count(n) AS c"),
    "orphans": (  # 6. nodes with no relationships (SRD library excluded)
        "MATCH (n:Entity) WHERE NOT (n)--() AND n.session_id <> 'SRD' "
        "RETURN count(n) AS c"),
    "possible_mis_modeled_recurrence": (  # 7. flag-only (docs/evolution/10) — review, don't auto-fix
        "MATCH (c:Entity{type:'Character'})-[:PARTICIPATED_IN]->(e:Entity{type:'Event'}) "
        "WHERE NOT (e)-[:TRIGGERED|RESULTED_IN]-() "
        "WITH c, e.name AS ename, count(DISTINCT e) AS occurrences "
        "WHERE occurrences >= 3 RETURN count(*) AS c"),
    "orphan_events": (  # 8. WP13.2 capsule contract: every Event must connect to the fiction
        "MATCH (e:Entity{type:'Event'}) "
        "WHERE NOT (e)-[:PARTICIPATED_IN|TARGETS|RESULTED_IN|TRIGGERED|AT_LOCATION]-() "
        "RETURN count(e) AS c"),
}
_QA_BLOCKERS = ("dup_names", "cross_type_names", "missing_provenance", "timeline_unlinked",
                "orphan_events")


def run_qa(driver) -> dict:
    """{check: count} for every QA query; log blockers loudly."""
    results = {}
    with driver.session() as db:
        for name, query in _QA_QUERIES.items():
            results[name] = db.run(query).single()["c"]
    for name in _QA_BLOCKERS:
        if results[name]:
            log.error("QA BLOCKER: %s = %d (must be 0)", name, results[name])
    return results
