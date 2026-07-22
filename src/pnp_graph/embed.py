"""Entity embeddings for retrieval (docs/evolution/11, WP11).

Re-embeds only the entities touched by the current ingest — the whole point
of keying on session writes rather than a periodic full re-embed. Text per
entity: type + name + aliases + latest description/summary. Two exceptions:
a Character's recurring personality/quirks live in `character_summary`
(WP13.4, docs/evolution/13 — an LLM-rewritten bio, not raw per-session text;
`cli summarize-entities` maintains it, never ingest directly) rather than
`description` (macro-graph philosophy: no separate Trait nodes). `Chunk`
nodes (WP13.5) embed their raw passage `text` verbatim — the "vector = das
Buch" half of the macro-graph split.
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
        # Two indexes, one per label: the :Entity skeleton and the :Chunk vector
        # "book" (WP13.5) are separate node classes (2026 GraphRAG-standard split).
        for name, label in (("entity_embedding", "Entity"), ("chunk_embedding", "Chunk")):
            db.run(
                f"CREATE VECTOR INDEX {name} IF NOT EXISTS "
                f"FOR (n:{label}) ON (n.embedding) "
                "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
                "`vector.similarity_function`: 'cosine'}}",
                dim=EMBED_DIM,
            )


def _entity_text(row: dict) -> str:
    if row.get("type") == "Chunk":  # WP13.5: embed the raw passage verbatim, no composing
        return row.get("text") or ""
    parts = [row.get("type") or "", row.get("name") or "", *(row.get("aliases") or [])]
    if row.get("type") == "Character":
        if row.get("character_summary"):  # WP13.4: LLM-maintained bio, not raw description
            parts.append(row["character_summary"])
    elif row.get("description"):
        parts.append(row["description"])
    if row.get("summary"):
        parts.append(row["summary"])
    return " | ".join(p for p in parts if p)


def embed_entities(driver, entity_ids: list[str]) -> int:
    """Embed the given entity ids (Session skipped). Returns count embedded."""
    if not entity_ids:
        return 0
    ensure_vector_index(driver)
    embedder = OllamaEmbeddings(model=EMBED_MODEL)
    with driver.session() as db:
        rows = db.run(
            "MATCH (n) WHERE (n:Entity OR n:Chunk) AND n.id IN $ids AND NOT n.type IN $backbone "
            "RETURN n.id AS id, n.type AS type, n.name AS name, "
            "       coalesce(n.aliases, []) AS aliases, n.description AS description, "
            "       n.summary AS summary, n.text AS text, n.character_summary AS character_summary",
            ids=entity_ids, backbone=list(BACKBONE_TYPES),
        ).data()
        n = 0
        for row in rows:
            text = _entity_text(row)
            if not text:
                continue
            vector = embedder.embed_query(text)
            db.run("MATCH (n{id:$id}) SET n.embedding = $v", id=row["id"], v=vector)
            n += 1
    log.info("embedded %d/%d touched entities", n, len(entity_ids))
    return n
