"""Entity embeddings for retrieval (docs/evolution/11, WP11).

Re-embeds only the entities touched by the current ingest — the whole point
of keying on session writes rather than a periodic full re-embed. Text per
entity: type + name + aliases + latest description/summary + (for
Characters) their aggregated Trait names (docs/evolution/10).
"""

import logging

from langchain_ollama import OllamaEmbeddings

from .config import EMBED_DIM, EMBED_MODEL

log = logging.getLogger("pnp_graph.embed")

# Backbone nodes grow with elapsed campaign time, not narrative content —
# never useful as a vector-search hit (docs/evolution/10's backbone-node note).
BACKBONE_TYPES = {"Session"}


def ensure_vector_index(driver) -> None:
    with driver.session() as db:
        db.run(
            "CREATE VECTOR INDEX entity_embedding IF NOT EXISTS "
            "FOR (n:Entity) ON (n.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}",
            dim=EMBED_DIM,
        )


def _entity_text(row: dict, trait_names: list[str]) -> str:
    parts = [row.get("type") or "", row.get("name") or "", *(row.get("aliases") or [])]
    if row.get("description"):
        parts.append(row["description"])
    if row.get("summary"):
        parts.append(row["summary"])
    parts += trait_names
    return " | ".join(p for p in parts if p)


def embed_entities(driver, entity_ids: list[str]) -> int:
    """Embed the given entity ids (Session skipped). Returns count embedded."""
    if not entity_ids:
        return 0
    ensure_vector_index(driver)
    embedder = OllamaEmbeddings(model=EMBED_MODEL)
    with driver.session() as db:
        rows = db.run(
            "MATCH (n:Entity) WHERE n.id IN $ids AND NOT n.type IN $backbone "
            "RETURN n.id AS id, n.type AS type, n.name AS name, "
            "       coalesce(n.aliases, []) AS aliases, n.description AS description, "
            "       n.summary AS summary",
            ids=entity_ids, backbone=list(BACKBONE_TYPES),
        ).data()
        char_ids = [r["id"] for r in rows if r["type"] == "Character"]
        traits_by_char: dict[str, list[str]] = {}
        if char_ids:
            for r in db.run(
                "MATCH (c:Entity)-[:KNOWN_FOR]->(t:Entity) WHERE c.id IN $ids "
                "RETURN c.id AS id, collect(t.name) AS names", ids=char_ids,
            ):
                traits_by_char[r["id"]] = r["names"]
        n = 0
        for row in rows:
            text = _entity_text(row, traits_by_char.get(row["id"], []))
            if not text:
                continue
            vector = embedder.embed_query(text)
            db.run("MATCH (n:Entity{id:$id}) SET n.embedding = $v", id=row["id"], v=vector)
            n += 1
    log.info("embedded %d/%d touched entities", n, len(entity_ids))
    return n
