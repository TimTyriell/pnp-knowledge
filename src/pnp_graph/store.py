"""Neo4j writes. Idempotent MERGE so repeated/multi-session runs accumulate.

Phase 1: same write behavior as the original script, parameterized by session_id.
Versioning (valid_from/valid_to) and per-session summaries land in later phases.
"""

import logging
import re

from neo4j import GraphDatabase

from .config import NEO4J_URL
from .schema import GraphExtraction

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
    db.run("CREATE CONSTRAINT character_name IF NOT EXISTS FOR (c:Character) REQUIRE c.name IS UNIQUE")
    db.run("CREATE CONSTRAINT location_name IF NOT EXISTS FOR (l:Location) REQUIRE l.name IS UNIQUE")
    db.run("CREATE CONSTRAINT faction_name IF NOT EXISTS FOR (f:Faction) REQUIRE f.name IS UNIQUE")


def _write_graph(db, graph: GraphExtraction, session_id: str, seq: int) -> None:
    db.run("MERGE (s:Session {id: $id}) SET s.seq = $seq", id=session_id, seq=seq)

    for c in graph.characters:
        db.run(
            "MERGE (c:Character {name: $name}) "
            "SET c.player = $player, c.type = $type, c.aliases = $aliases "
            "WITH c MATCH (s:Session {id: $sid}) MERGE (c)-[:APPEARS_IN]->(s)",
            name=c.name, player=c.player, type=c.type, aliases=c.aliases, sid=session_id,
        )
    for l in graph.locations:
        db.run(
            "MERGE (l:Location {name: $name}) SET l.description = $description",
            name=l.name, description=l.description,
        )
    for i in graph.items:
        db.run(
            "MERGE (i:Item {name: $name}) SET i.status = $status "
            "WITH i MATCH (c:Character {name: $owner}) MERGE (i)-[:OWNED_BY]->(c)",
            name=i.name, status=i.status, owner=i.owner,
        )
    for q in graph.quests:
        db.run("MERGE (q:Quest {name: $name}) SET q.status = $status", name=q.name, status=q.status)
    for e in graph.events:
        db.run(
            # `name` mirrors `title` so relationship edges can MATCH any node type by `name` alone.
            "MERGE (ev:Event {title: $title}) SET ev.summary = $summary, ev.name = $title "
            "WITH ev MATCH (s:Session {id: $sid}) MERGE (ev)-[:IN_SESSION]->(s) "
            "WITH ev MATCH (l:Location {name: $location}) MERGE (ev)-[:AT_LOCATION]->(l)",
            title=e.title, summary=e.summary, sid=session_id, location=e.location,
        )
        for participant in e.participants:
            db.run(
                "MATCH (c:Character {name: $name}), (ev:Event {title: $title}) "
                "MERGE (c)-[:PARTICIPATED_IN]->(ev)",
                name=participant, title=e.title,
            )
    for f in graph.factions:
        db.run("MERGE (f:Faction {name: $name}) SET f.description = $description",
               name=f.name, description=f.description)

    for r in graph.relationships:
        rel_type = sanitize_predicate(r.predicate)
        # rel_type is sanitized to [A-Z0-9_] only, safe to interpolate as a Cypher relationship type.
        db.run(
            f"MATCH (a {{name: $subject}}), (b {{name: $object}}) "
            f"MERGE (a)-[rel:{rel_type}]->(b) "
            f"SET rel.confidence = $confidence, rel.evidence_chunk = $evidence, rel.session_id = $sid",
            subject=r.subject, object=r.object,
            confidence=r.confidence, evidence=r.evidence, sid=session_id,
        )


def write_session(driver, graph: GraphExtraction, session_id: str, seq: int) -> None:
    """Write one session's merged graph in a single atomic transaction."""
    with driver.session() as db:
        db.execute_write(ensure_constraints)
        db.execute_write(_write_graph, graph, session_id, seq)
