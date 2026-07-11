"""LLM extraction: chunk text -> GraphExtraction, and in-memory merge."""

import json
import logging

from langchain_ollama import ChatOllama

from .config import (
    LLM_MODEL, LLM_TIMEOUT_S, NUM_CTX, NUM_PREDICT, REPEAT_PENALTY, SUGGESTED_PREDICATES,
)
from .schema import EntityExtraction, Event, EventConsolidation, EventExtraction, GraphExtraction

log = logging.getLogger("pnp_graph.extract")

# Two-role extraction (docs/evolution/06, WP7): a 14B stays reliable on two
# smaller schemas better than one mega-schema, and it raises recall without
# the model having to hold causal reasoning + entity spotting in one pass.
_ENTITY_PROMPT = (
    "Extract characters, NPCs, locations, items, quests, and factions from this "
    "TTRPG (Daggerheart) session transcript chunk. Use consistent names across mentions. "
    "For characters, set type to \"adversary\" for a hostile monster/enemy the party fights, "
    "\"NPC\" for other non-player characters, \"PC\" for player characters.\n\n"
    "Also extract:\n"
    "- rule_entities: game-rules objects referenced at the table (classes, subclasses, "
    "ancestries, communities, domain cards, class features, adversary stat blocks, system "
    "resources like Hope/Fear/Stress). Game resources are rule entities, NOT items.\n\n"
    "Ignore stream/chat meta entirely: Twitch chat messages, raid announcements, viewer "
    "shout-outs, and VTT/tool operation talk (turn trackers, camera/cinema modes, dice-roller "
    "UI) are not part of the game fiction. Never extract a chat viewer, a raiding community, "
    "or a tool/UI element as a character or NPC.\n\n"
)

_EVENT_PROMPT = (
    "Extract events, dice rolls, decisions, recurring traits, and relationships from this "
    "TTRPG (Daggerheart) session transcript chunk.\n\n"
    "- events: only create a new event for an occurrence if at least one is true: (a) a roll "
    "happened, (b) it changed a tracked state (HP, quest status, item ownership, relationship), "
    "(c) it caused or resulted from another event/decision, or (d) it's referenced again later "
    "in the session. If it's ambient/flavor color with none of these — including a repeat of "
    "something a character does regularly — do NOT create an event; instead extract it as a "
    "trait.\n"
    "- traits: a recurring characterization or habit of one character (e.g. 'plays music often', "
    "'always distrusts strangers'), not a one-off happening. If the same ambient behavior comes "
    "up again for a character already noted for it, extract it again as the same trait name "
    "rather than as a new event. Never extract a player's out-of-character/meta commentary "
    "about the game (asking rules questions, giving feedback about how the session went) as a "
    "trait of their character — that describes the player, not the character.\n"
    "- roll_events: every dice roll — who rolled, what trait/action, the outcome "
    "(success_with_hope, success_with_fear, failure, crit...), and the target if any.\n"
    "- decisions: deliberate, weighty player/GM choices, with a short verbatim quote and "
    "the consequence.\n"
    "- relationships: arbitrary lore/social/causal connections between entities already named "
    "below (e.g. a character is hostile to a faction, a character HAS_CLASS a class, a decision "
    "TRIGGERED an event, an event RESULTED_IN another event, an adversary USES its stat block). "
    "Each relationship's subject and object must be one of the names listed below, never a new "
    "entity. Prefer reusing one of these relation types when it fits: "
    f"{', '.join(SUGGESTED_PREDICATES)}, HAS_CLASS, HAS_SUBCLASS, HAS_ANCESTRY, USES_CARD, "
    "HAS_FEATURE, USES, DECIDED, ROLLED — but use a different short UPPER_SNAKE_CASE predicate "
    "if none of these fit. Rate each relationship's confidence based on how directly the text "
    "supports it. If the relationship carries nuance the predicate alone can't express (e.g. "
    "'trusts him only reluctantly, since the incident in the forest'), add a short description; "
    "leave it empty otherwise.\n\n"
)


def build_extractor():
    # One ChatOllama instance -> one model resident in VRAM even though we
    # issue two structured-output calls per chunk (docs/evolution/06), plus one
    # session-level consolidation call (N3, KG_Qualitaetsanalyse_S01).
    llm = ChatOllama(
        model=LLM_MODEL, temperature=0, num_ctx=NUM_CTX, reasoning=False,
        repeat_penalty=REPEAT_PENALTY, num_predict=NUM_PREDICT,
        client_kwargs={"timeout": LLM_TIMEOUT_S},
    )
    return (
        llm.with_structured_output(EntityExtraction, method="json_schema"),
        llm.with_structured_output(EventExtraction, method="json_schema"),
        llm.with_structured_output(EventConsolidation, method="json_schema"),
    )


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


def _known_entities_line(names: list[str]) -> str:
    return (
        "Entities already extracted from this chunk (use only these as subject/object, "
        f"plus 'GM'): {', '.join(names)}.\n\n" if names else ""
    )


def _invoke_with_retry(extractor, prompt: str, chunk: str, chunk_index: int, label: str):
    try:
        result = extractor.invoke(prompt + chunk)
        if result is None:
            raise ValueError("structured output returned None")
    except Exception as exc:  # one retry with a JSON reminder (PLAN.md phase 5)
        log.warning("chunk %d %s-pass extraction failed (%s) — retrying once",
                    chunk_index, label, exc)
        result = extractor.invoke(
            prompt + chunk + "\n\nReturn ONLY valid JSON matching the schema. No prose.")
        if result is None:
            raise ValueError("structured output returned None on retry")
    return result


def extract_chunk(extractors, chunk: str, chunk_index: int,
                  cast_names: list[str] | None = None,
                  rule_names: list[str] | None = None) -> GraphExtraction:
    """Two structured-output calls per chunk (docs/evolution/06, WP7): entity+rules
    pass, then an event pass restricted to the names the entity pass just found."""
    entity_extractor, event_extractor, _ = extractors
    entity_prompt = _ENTITY_PROMPT + _cast_line(cast_names) + _gazetteer_line(rule_names)
    entities: EntityExtraction = _invoke_with_retry(
        entity_extractor, entity_prompt, chunk, chunk_index, "entity")

    known_names = sorted({
        *(cast_names or []),
        *(c.name for c in entities.characters),
        *(l.name for l in entities.locations),
        *(i.name for i in entities.items),
        *(q.name for q in entities.quests),
        *(f.name for f in entities.factions),
        *(r.name for r in entities.rule_entities),
    })
    event_prompt = _EVENT_PROMPT + _known_entities_line(known_names)
    events: EventExtraction = _invoke_with_retry(
        event_extractor, event_prompt, chunk, chunk_index, "event")
    for r in events.relationships:
        r.evidence = chunk_index  # set programmatically; the model can't know its chunk

    return GraphExtraction(
        characters=entities.characters, locations=entities.locations,
        items=entities.items, quests=entities.quests, factions=entities.factions,
        rule_entities=entities.rule_entities,
        events=events.events, roll_events=events.roll_events,
        decisions=events.decisions, traits=events.traits,
        relationships=events.relationships,
    )


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
        ("traits", "name"),
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
        ("traits", "name"),
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
            "[%d/%d] +%d chars, +%d locs, +%d items, +%d quests, +%d events, +%d factions, "
            "+%d traits, +%d rels",
            i, len(chunks),
            len(result.characters), len(result.locations), len(result.items),
            len(result.quests), len(result.events), len(result.factions),
            len(result.traits), len(result.relationships),
        )
    return merged, evidence


# --- N3: session-level event consolidation (docs/evolution/KG_Qualitaetsanalyse_S01) ---
# merge_graphs already dedups events by exact title; a small chunk still mints
# near-duplicate titles for the same moment ('Monster's Last Breath' / 'Monster's
# Final Breath' / 'Monster's Death and Environment Normalization') because no
# single chunk sees the whole session. One extra call after all chunks are
# merged groups those into moments; apply_event_consolidation() then rewrites
# the graph deterministically — the LLM only proposes groupings, never touches data.

_CONSOLIDATION_PROMPT = (
    "Below is every event extracted from one TTRPG (Daggerheart) session, each as "
    "'N. <title> — <summary>'. Group entries that describe the SAME narrative moment or "
    "state change into one group, even if phrased differently (e.g. \"Monster's Last "
    "Breath\", \"Monster's Final Breath\", and \"Monster's Death and Environment "
    "Normalization\" are one moment: the monster dying). Keep genuinely distinct events in "
    "separate, single-member groups — do not over-merge. Every listed title must appear in "
    "exactly one group's member_titles, spelled EXACTLY as given. For each group, pick the "
    "clearest canonical_title and write one merged summary.\n\n"
)


def propose_event_groups(consolidation_extractor, graph: GraphExtraction) -> EventConsolidation:
    if len(graph.events) < 2:
        return EventConsolidation(groups=[])
    listing = "\n".join(f"{i}. {e.title} — {e.summary}" for i, e in enumerate(graph.events, start=1))
    try:
        result = consolidation_extractor.invoke(_CONSOLIDATION_PROMPT + listing)
    except Exception as exc:
        log.warning("event consolidation call failed (%s) — keeping events as-is", exc)
        return EventConsolidation(groups=[])
    return result or EventConsolidation(groups=[])


def _remap_evidence(evidence: dict, title_map: dict[str, str]) -> dict:
    remapped: dict = {}
    for (field, key), chunks in evidence.items():
        if field == "events" and key in title_map:
            new_key = ("events", title_map[key])
        elif field == "relationships":
            subj, pred, obj = key
            new_key = ("relationships", (title_map.get(subj, subj), pred, title_map.get(obj, obj)))
        else:
            new_key = (field, key)
        remapped[new_key] = sorted(set(remapped.get(new_key, [])) | set(chunks))
    return remapped


def apply_event_consolidation(graph: GraphExtraction, evidence: dict,
                              consolidation: EventConsolidation) -> None:
    """Deterministically apply a proposed grouping: rewrite graph.events to one
    entry per group, rewrite every relationship subject/object referencing an
    old title, and remap the evidence sidecar — all in place. A title the model
    didn't cover (schema drift) stays its own singleton (safety net, PLAN.md
    phase-5 pattern) rather than being silently dropped.
    """
    if not consolidation.groups:
        return
    known_titles = {e.title for e in graph.events}
    events_by_title = {e.title: e for e in graph.events}
    title_map: dict[str, str] = {}
    new_events: dict[str, Event] = {}

    for group in consolidation.groups:
        members = [m for m in group.member_titles if m in known_titles]
        if not members:
            continue
        canonical = group.canonical_title.strip() or members[0]
        member_events = [events_by_title[m] for m in members]
        participants = sorted({p for e in member_events for p in e.participants})
        location = next((e.location for e in member_events if e.location), None)
        summary = group.summary.strip() or "; ".join(
            e.summary for e in member_events if e.summary)
        for m in members:
            title_map[m] = canonical
        if canonical in new_events:
            prev = new_events[canonical]
            prev.participants = sorted(set(prev.participants) | set(participants))
            prev.location = prev.location or location
            if summary and summary not in prev.summary:
                prev.summary = (prev.summary + "; " + summary).strip("; ")
        else:
            new_events[canonical] = Event(
                title=canonical, summary=summary, participants=participants, location=location)

    for title, event in events_by_title.items():  # safety net for model-dropped titles
        if title not in title_map:
            title_map[title] = title
            new_events.setdefault(title, event)

    graph.events = list(new_events.values())

    for r in graph.relationships:
        r.subject = title_map.get(r.subject, r.subject)
        r.object = title_map.get(r.object, r.object)
    seen_rels: set = set()
    deduped_rels = []
    for r in graph.relationships:
        key = (r.subject, r.predicate, r.object)
        if key in seen_rels:
            continue
        seen_rels.add(key)
        deduped_rels.append(r)
    graph.relationships = deduped_rels

    if evidence:
        remapped = _remap_evidence(evidence, title_map)
        evidence.clear()
        evidence.update(remapped)
