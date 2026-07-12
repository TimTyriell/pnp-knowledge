"""Retrieval layer (docs/evolution/11, WP11) — GraphRAG-style "local search"
WITHOUT adopting the GraphRAG framework (verdict in the doc): embed the
question, pull top-k entities via the Neo4j vector index, expand 1-2 hops
filtered to currently-true facts (or "as of session N"), excluding the
Session backbone, then let the local LLM answer from that compact
context, citing session_ids. No community detection / global search.
"""

import logging

from langchain_ollama import ChatOllama, OllamaEmbeddings

from .config import EMBED_MODEL, LLM_MODEL, NUM_CTX
from .embed import BACKBONE_TYPES

log = logging.getLogger("pnp_graph.retrieve")

_SYSTEM = (
    "You answer questions about a TTRPG campaign using ONLY the graph context below. "
    "Cite the session_id for every claim you make. If the context doesn't contain the "
    "answer, say so plainly instead of guessing.\n\n"
)


def _top_k_entities(driver, question: str, k: int) -> list[dict]:
    """Top-k seeds across BOTH vector indexes — the :Entity skeleton and the
    :Chunk passage "book" (WP13.5) — merged by cosine score. A Chunk seed pulls
    its verbatim passage into context; an Entity seed pulls its neighborhood."""
    embedder = OllamaEmbeddings(model=EMBED_MODEL)
    qvec = embedder.embed_query(question)
    rows: list[dict] = []
    with driver.session() as db:
        for index in ("entity_embedding", "chunk_embedding"):
            rows += db.run(
                "CALL db.index.vector.queryNodes($index, $k, $qvec) "
                "YIELD node, score "
                "RETURN node.id AS id, node.type AS type, node.name AS name, score",
                index=index, k=k, qvec=qvec,
            ).data()
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:k]


def _expand(driver, entity_ids: list[str], as_of_session: int | None) -> dict:
    """1-hop neighborhood of the seed entities: currently-true facts by
    default, or every fact valid as of `as_of_session` (docs/evolution/11).
    Non-lifecycle edges (events, identity) are always included —
    only state edges are time-filtered."""
    if as_of_session is None:
        edge_filter = "(r.valid_from IS NULL OR r.valid_to IS NULL)"
        params: dict = {}
    else:
        edge_filter = (
            "(r.valid_from IS NULL) OR "
            "(r.valid_from <= $asof AND (r.valid_to IS NULL OR r.valid_to > $asof))"
        )
        params = {"asof": as_of_session}
    with driver.session() as db:
        nodes = db.run(
            "MATCH (n) WHERE (n:Entity OR n:Chunk) AND n.id IN $ids "
            "RETURN n.id AS id, n.type AS type, "
            "n.name AS name, n.status AS status, n.text AS text", ids=entity_ids,
        ).data()
        edges = db.run(
            # directed pattern (never -[r]-) so an edge between two seed
            # entities is returned once, not once per traversal direction.
            # Label-agnostic endpoints so Chunk-[:MENTIONS]->Entity edges (the
            # passage<->skeleton join, WP13.5) expand alongside skeleton edges.
            f"MATCH (a)-[r]->(b) WHERE (a:Entity OR a:Chunk) AND (b:Entity OR b:Chunk) "
            f"AND (a.id IN $ids OR b.id IN $ids) "
            f"AND {edge_filter} AND NOT a.type IN $backbone AND NOT b.type IN $backbone "
            f"RETURN a.id AS a, a.name AS a_name, type(r) AS rel, b.id AS b, "
            f"       b.name AS b_name, r.description AS description, "
            f"       r.confidence AS confidence, r.session_id AS session_id, "
            f"       r.count AS count",
            ids=entity_ids, backbone=list(BACKBONE_TYPES), **params,
        ).data()
    return {"nodes": nodes, "edges": edges}


def _format_context(ctx: dict) -> str:
    lines = ["Entities:"]
    for n in ctx["nodes"]:
        if n.get("type") == "Chunk":  # WP13.5: verbatim source text, not the usual name line
            lines.append(f"  - {n['id']} (source passage): {n.get('text', '').strip()}")
            continue
        status = f", status={n['status']}" if n.get("status") else ""
        lines.append(f"  - {n['id']} ({n['type']}): {n['name']}{status}")
    lines.append("Facts:")
    for e in ctx["edges"]:
        bits = []
        if e.get("session_id"):
            bits.append(f"session={e['session_id']}")
        if e.get("confidence"):
            bits.append(f"confidence={e['confidence']}")
        if e.get("count"):
            bits.append(f"count={e['count']}")
        if e.get("description"):
            bits.append(f'"{e["description"]}"')
        suffix = f" [{', '.join(bits)}]" if bits else ""
        lines.append(f"  - {e['a_name']} -{e['rel']}-> {e['b_name']}{suffix}")
    return "\n".join(lines)


def search(driver, question: str, k: int = 8, as_of_session: int | None = None) -> dict:
    """Question -> compact graph context dict (nodes + edges). No LLM call."""
    seeds = _top_k_entities(driver, question, k)
    if not seeds:
        return {"nodes": [], "edges": []}
    return _expand(driver, [s["id"] for s in seeds], as_of_session)


def ask(driver, question: str, k: int = 8, as_of_session: int | None = None) -> str:
    ctx = search(driver, question, k, as_of_session)
    if not ctx["nodes"]:
        return "No relevant entities found in the graph for that question."
    llm = ChatOllama(model=LLM_MODEL, temperature=0, num_ctx=NUM_CTX, reasoning=False)
    prompt = f"{_SYSTEM}Question: {question}\n\nGraph context:\n{_format_context(ctx)}\n\nAnswer:"
    return llm.invoke(prompt).content
