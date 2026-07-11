"""LLM extraction: chunk text -> GraphExtraction, and in-memory merge."""

import json
import logging

from langchain_ollama import ChatOllama

from .config import LLM_MODEL, NUM_CTX, SUGGESTED_PREDICATES
from .schema import GraphExtraction

log = logging.getLogger("pnp_graph.extract")

_PROMPT = (
    "Extract characters, NPCs, locations, items, quests, events, and factions from this "
    "TTRPG (Daggerheart) session transcript chunk. Use consistent names across mentions.\n\n"
    "Also extract:\n"
    "- rule_entities: game-rules objects referenced at the table (classes, subclasses, "
    "ancestries, communities, domain cards, class features, adversary stat blocks, system "
    "resources like Hope/Fear/Stress). Game resources are rule entities, NOT items.\n"
    "- roll_events: every dice roll — who rolled, what trait/action, the outcome "
    "(success_with_hope, success_with_fear, failure, crit...), and the target if any.\n"
    "- decisions: deliberate, weighty player/GM choices, with a short verbatim quote and "
    "the consequence.\n\n"
    "Also extract relationships: arbitrary lore/social/causal connections between entities "
    "already extracted above (e.g. a character is hostile to a faction, a character HAS_CLASS "
    "a class, a decision TRIGGERED an event, an event RESULTED_IN another event). Each "
    "relationship's subject and object must be a name from the lists above, not a new "
    "entity. Prefer reusing one of these relation types when it fits: "
    f"{', '.join(SUGGESTED_PREDICATES)}, HAS_CLASS, HAS_SUBCLASS, HAS_ANCESTRY, USES_CARD, "
    "HAS_FEATURE, USES, DECIDED, ROLLED — but use a different short UPPER_SNAKE_CASE predicate "
    "if none of these fit. Rate each relationship's confidence based on how directly the text "
    "supports it.\n\n"
)


def build_extractor():
    llm = ChatOllama(model=LLM_MODEL, temperature=0, num_ctx=NUM_CTX, reasoning=False)
    return llm.with_structured_output(GraphExtraction, method="json_schema")


def _cast_line(cast_names: list[str] | None) -> str:
    if not cast_names:
        return ""
    return (
        "The speakers in this transcript are these characters (plus 'GM', the narrator): "
        f"{', '.join(cast_names)}. Attribute their actions to exactly these names — "
        "do not invent name variants for them.\n\n"
    )


def _gazetteer_line(rule_names: list[str] | None) -> str:
    if not rule_names:
        return ""
    return (
        "Known Daggerheart rule entities (use these exact names when the table references "
        f"them, even if the transcript paraphrases or uses German): {', '.join(rule_names)}.\n\n"
    )


def extract_chunk(extractor, chunk: str, chunk_index: int,
                  cast_names: list[str] | None = None,
                  rule_names: list[str] | None = None) -> GraphExtraction:
    prompt = _PROMPT + _cast_line(cast_names) + _gazetteer_line(rule_names)
    try:
        result: GraphExtraction | None = extractor.invoke(prompt + chunk)
        if result is None:
            raise ValueError("structured output returned None")
    except Exception as exc:  # one retry with a JSON reminder (PLAN.md phase 5)
        log.warning("chunk %d extraction failed (%s) — retrying once", chunk_index, exc)
        result = extractor.invoke(
            prompt + chunk + "\n\nReturn ONLY valid JSON matching the schema. No prose.")
        if result is None:
            raise ValueError("structured output returned None on retry")
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
        ("rule_entities", "name"),
        ("roll_events", "name"),
        ("decisions", "name"),
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


def _record_evidence(evidence: dict, result: GraphExtraction, chunk_index: int) -> None:
    """Accumulate which chunks each entity/relationship was seen in (sidecar,
    keyed on the same name/title keys merge_graphs dedups on — kept out of the
    Pydantic models so the LLM's JSON schema stays unchanged)."""
    for field, key in (
        ("characters", "name"), ("locations", "name"), ("items", "name"),
        ("quests", "name"), ("events", "title"), ("factions", "name"),
        ("rule_entities", "name"), ("roll_events", "name"), ("decisions", "name"),
    ):
        for item in getattr(result, field):
            evidence.setdefault((field, getattr(item, key)), []).append(chunk_index)
    for r in result.relationships:
        evidence.setdefault(("relationships", (r.subject, r.predicate, r.object)), []).append(chunk_index)


def extract_session(extractor, chunks: list[str],
                    cast_names: list[str] | None = None,
                    rule_names: list[str] | None = None,
                    fail_dir=None) -> tuple[GraphExtraction, dict]:
    """Run every chunk of one session; returns (merged graph, evidence sidecar).

    With `fail_dir`, a chunk that still fails after the retry is dumped there
    and skipped — a partial session beats no session (PLAN.md phase 5).
    """
    merged = GraphExtraction()
    evidence: dict = {}
    for i, chunk in enumerate(chunks, start=1):
        try:
            result = extract_chunk(extractor, chunk, i, cast_names, rule_names)
        except Exception as exc:
            if fail_dir is None:
                raise
            fail_dir.mkdir(parents=True, exist_ok=True)
            (fail_dir / f"chunk_{i:03d}.json").write_text(
                json.dumps({"chunk_index": i, "error": repr(exc), "chunk": chunk},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            log.error("chunk %d failed twice — dumped to %s, continuing", i, fail_dir)
            continue
        _record_evidence(evidence, result, i)
        merge_graphs(merged, result)
        log.info(
            "[%d/%d] +%d chars, +%d locs, +%d items, +%d quests, +%d events, +%d factions, +%d rels",
            i, len(chunks),
            len(result.characters), len(result.locations), len(result.items),
            len(result.quests), len(result.events), len(result.factions),
            len(result.relationships),
        )
    return merged, evidence
