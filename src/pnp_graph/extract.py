"""LLM extraction: chunk text -> GraphExtraction, and in-memory merge."""

import logging

from langchain_ollama import ChatOllama

from .config import LLM_MODEL, NUM_CTX, SUGGESTED_PREDICATES
from .schema import GraphExtraction

log = logging.getLogger("pnp_graph.extract")

_PROMPT = (
    "Extract characters, NPCs, locations, items, quests, events, and factions from this "
    "TTRPG session transcript chunk. Use consistent names across mentions.\n\n"
    "Also extract relationships: arbitrary lore/social/causal connections between entities "
    "already extracted above (e.g. a character is hostile to a faction, a character knows "
    "an NPC, an event resulted in another event). Each relationship's subject and object must "
    "be a name from the characters/locations/items/quests/events/factions lists, not a new "
    "entity. Prefer reusing one of these relation types when it fits: "
    f"{', '.join(SUGGESTED_PREDICATES)} — but use a different short UPPER_SNAKE_CASE predicate "
    "if none of these fit. Rate each relationship's confidence based on how directly the text "
    "supports it.\n\n"
)


def build_extractor():
    llm = ChatOllama(model=LLM_MODEL, temperature=0, num_ctx=NUM_CTX, reasoning=False)
    return llm.with_structured_output(GraphExtraction, method="json_schema")


def extract_chunk(extractor, chunk: str, chunk_index: int) -> GraphExtraction:
    result: GraphExtraction = extractor.invoke(_PROMPT + chunk)
    for r in result.relationships:
        r.evidence = chunk_index  # set programmatically; the model can't know its chunk
    return result


def merge_graphs(target: GraphExtraction, extra: GraphExtraction) -> None:
    """Merge `extra` into `target` in place, deduplicating by name/title (or subject+predicate+object)."""
    for field, key in (
        ("characters", "name"),
        ("locations", "name"),
        ("items", "name"),
        ("quests", "name"),
        ("events", "title"),
        ("factions", "name"),
    ):
        existing = {getattr(item, key) for item in getattr(target, field)}
        for item in getattr(extra, field):
            if getattr(item, key) not in existing:
                getattr(target, field).append(item)
                existing.add(getattr(item, key))

    existing_rels = {(r.subject, r.predicate, r.object) for r in target.relationships}
    for r in extra.relationships:
        rel_key = (r.subject, r.predicate, r.object)
        if rel_key not in existing_rels:
            target.relationships.append(r)
            existing_rels.add(rel_key)


def extract_session(extractor, chunks: list[str]) -> GraphExtraction:
    """Run every chunk of one session and merge into a single GraphExtraction."""
    merged = GraphExtraction()
    for i, chunk in enumerate(chunks, start=1):
        result = extract_chunk(extractor, chunk, i)
        merge_graphs(merged, result)
        log.info(
            "[%d/%d] +%d chars, +%d locs, +%d items, +%d quests, +%d events, +%d factions, +%d rels",
            i, len(chunks),
            len(result.characters), len(result.locations), len(result.items),
            len(result.quests), len(result.events), len(result.factions),
            len(result.relationships),
        )
    return merged
