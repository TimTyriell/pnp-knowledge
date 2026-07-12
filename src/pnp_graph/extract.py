"""LLM extraction: chunk text -> GraphExtraction, and in-memory merge."""

import json
import logging

from langchain_ollama import ChatOllama

from .config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, FLAGSHIP_MAX_TOKENS, LLM_MODEL, LLM_TIMEOUT_S,
    NUM_CTX, NUM_PREDICT, PROVIDER, REPEAT_PENALTY, SUGGESTED_PREDICATES,
)
from .schema import GraphExtraction, SceneExtraction, SceneSegmentation

log = logging.getLogger("pnp_graph.extract")

# Single-call scene extraction (docs/evolution/13, WP13.6): supersedes the WP7
# two-pass entity/event split (kept a 14B reliable on a smaller schema per
# call). On the flagship profile, with scenes already pre-segmented so each
# call is scoped to one coherent unit, one combined call halves the API calls
# per session at no measured quality cost.
_SCENE_PROMPT = (
    "This transcript chunk is ONE scene. Extract everything from it in one pass.\n\n"
    "- items: create an Item ONLY for a unique, named, plot-significant artifact and set "
    "is_named_artifact=true. WRONG (is_named_artifact=false, generic — do NOT treat as "
    "significant): 'Fackel', '3 Goldstücke', 'Heiltrank', 'Kurzschwert'. CORRECT "
    "(is_named_artifact=true): 'Schwert des Veritas', 'die verlorene Schriftrolle der Blume'.\n"
    "- characters, locations, quests, factions: use consistent names across mentions. "
    "For characters, set role to \"adversary\" for a hostile monster/enemy the party fights, "
    "\"NPC\" for other non-player characters, \"PC\" for player characters. If a character "
    "shows a recurring personality trait, habit, or quirk (e.g. 'plays music often', 'always "
    "distrusts strangers'), fold it into that character's description as prose — never as a "
    "separate happening. Never put a player's out-of-character/meta commentary (rules "
    "questions, feedback about the session) into a character's description — that describes "
    "the player, not the character.\n"
    "- rule_entities: game-rules objects referenced at the table (classes, subclasses, "
    "ancestries, communities, domain cards, class features, adversary stat blocks, system "
    "resources like Hope/Fear/Stress). Game resources are rule entities, NOT items. "
    "Extract ONLY rules that match the known-rules list further below — anything rule-like "
    "that is not on that list (in-character banter about made-up abilities, descriptions of "
    "miniatures/tokens) is NOT a rule entity; skip it.\n"
    "- macro_scene_event: the SINGLE most consequential thing this whole scene accomplishes — "
    "its summary as one macro unit, or the one permanent, world-altering state change (a death, "
    "a quest completed, an alliance formed, ownership changing hands). A whole 20-minute combat "
    "is ONE event (e.g. 'Kampf gegen die Goblins'), never one per attack or roll. Fill "
    "narrative_significance_reasoning with why this scene alters world state — if the scene is "
    "pure filler, still name its most consequential moment; do not invent multiple events. "
    "Session-opening recaps and character introductions are NOT macro-events.\n"
    "- relationships: arbitrary lore/social/causal connections between entities you extracted "
    "above (e.g. a character is hostile to a faction, a character HAS_CLASS a class, an event "
    "RESULTED_IN another event, an adversary USES its stat block). "
    "Each relationship's subject and object — and the macro_scene_event's participants — must be "
    "one of the names you extracted above or from the cast list below, never an entity you "
    "haven't listed anywhere else. Prefer reusing one of these relation types when it fits: "
    f"{', '.join(SUGGESTED_PREDICATES)}, HAS_CLASS, HAS_SUBCLASS, HAS_ANCESTRY, USES_CARD, "
    "HAS_FEATURE, USES — but use a different short UPPER_SNAKE_CASE predicate "
    "if none of these fit. Rate each relationship's confidence based on how directly the text "
    "supports it. If the relationship carries nuance the predicate alone can't express (e.g. "
    "'trusts him only reluctantly, since the incident in the forest'), add a short description; "
    "leave it empty otherwise. Do not extract ALLIED_WITH or KNOWS between player characters — "
    "party membership is implicit and not a relationship.\n\n"
    "Extract ONLY what exists inside the game fiction (diegetic). Ignore stream/chat meta "
    "entirely: Twitch chat messages, raid announcements, viewer shout-outs, and VTT/tool "
    "operation talk (turn trackers, camera/cinema modes, dice-roller UI) are not part of the "
    "game fiction. Never extract a chat viewer, a raiding community, or a tool/UI element as a "
    "character or NPC. The same goes for GM remarks about the real world (scheduling, someone "
    "making the session run late, technical issues), descriptions of the physical "
    "miniatures/tokens on the table ('das ist nur eine Maus als Figur' describes the miniature, "
    "not the character), and in-character jokes about abilities or classes that do not exist — "
    "none of these are entities.\n\n"
    "The transcript is auto-transcribed (Whisper) — names appear in inconsistent spellings. "
    "Never create separate entities for spelling variants of one name (pick one spelling and "
    "keep it), and never merge two people just because their names sound similar when the "
    "context shows they are different figures (e.g. a tomb guardian vs. a fleeing child).\n\n"
)


def _make_chat_llm():
    if PROVIDER == "deepseek":
        from langchain_openai import ChatOpenAI  # lazy: not a dep of the local profile
        return ChatOpenAI(
            model=LLM_MODEL, temperature=0, base_url=DEEPSEEK_BASE_URL,
            api_key=DEEPSEEK_API_KEY, timeout=LLM_TIMEOUT_S, max_tokens=FLAGSHIP_MAX_TOKENS,
            # deepseek-v4-flash defaults to thinking mode, which rejects the forced
            # tool_choice with_structured_output(function_calling) sets — dense chunks
            # that trigger thinking then 400/return None. Disable thinking for
            # structured extraction (the two are mutually exclusive on this endpoint).
            extra_body={"thinking": {"type": "disabled"}},
        )
    # One ChatOllama instance -> one model resident in VRAM even though we
    # issue two structured-output calls per chunk (docs/evolution/06).
    return ChatOllama(
        model=LLM_MODEL, temperature=0, num_ctx=NUM_CTX, reasoning=False,
        repeat_penalty=REPEAT_PENALTY, num_predict=NUM_PREDICT,
        client_kwargs={"timeout": LLM_TIMEOUT_S},
    )


def _structured_method() -> str:
    # DeepSeek's OpenAI-compatible endpoint doesn't support strict json_schema
    # response_format at all (confirmed live: 400 "response_format type is
    # unavailable"). Its strict function-calling mode (strict=True) DOES get
    # accepted, but on a compound schema with several $defs (Event/RollEvent/
    # Decision/Relationship/...) it silently ignores our schema and
    # hallucinates a different one instead (invented keys like "event_type",
    # "source_entity", "relationship_type" — none of them ours). Plain
    # non-strict function-calling reliably returns the exact schema we asked
    # for, so use that despite the occasional missed tool-call _invoke_with_retry
    # already covers. SceneExtraction (WP13.6) is the largest compound schema
    # yet — re-verify this holds if DeepSeek's tool-call adherence regresses.
    return "function_calling" if PROVIDER == "deepseek" else "json_schema"


def build_extractor():
    return _make_chat_llm().with_structured_output(SceneExtraction, method=_structured_method())


def build_segmenter():
    """WP13.1 semantic scene chunking: a structured-output client that partitions
    a whole session into scenes (used on the flagship profile only)."""
    return _make_chat_llm().with_structured_output(SceneSegmentation, method=_structured_method())


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


def _known_world_line(known: dict[str, list[str]] | None) -> str:
    """Audit v6 engine fix: the campaign's known canon, injected per chunk so the
    model resolves mentions to existing entities at extraction time instead of
    minting ASR spelling variants / quest paraphrases the resolver then can't merge."""
    if not known or not any(known.values()):
        return ""
    lines = "\n".join(f"{label}: {'; '.join(names)}" for label, names in known.items() if names)
    return (
        "Known campaign entities from previous sessions and earlier scenes of this one. "
        "When a mention refers to — or is an ASR spelling variant of — one of these, use the "
        "EXACT name as listed, never a new spelling. Only introduce a new entity when it is "
        "clearly distinct from all of these.\n"
        f"{lines}\n"
        "If this scene advances one of the known quests, reuse its exact quest name and set "
        "its current status; only create a new quest for a genuinely new storyline.\n\n"
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


def extract_chunk(extractor, chunk: str, chunk_index: int,
                  cast_names: list[str] | None = None,
                  rule_names: list[str] | None = None,
                  known_world: dict[str, list[str]] | None = None) -> GraphExtraction:
    """One structured-output call per chunk (docs/evolution/13, WP13.6): entities,
    rules, the one capsule macro event (WP13.2), relationships."""
    prompt = (_SCENE_PROMPT + _cast_line(cast_names) + _gazetteer_line(rule_names)
              + _known_world_line(known_world))
    scene: SceneExtraction = _invoke_with_retry(extractor, prompt, chunk, chunk_index, "scene")
    for r in scene.relationships:
        r.evidence = chunk_index  # set programmatically; the model can't know its chunk

    return GraphExtraction(
        characters=scene.characters, locations=scene.locations,
        items=scene.items, quests=scene.quests, factions=scene.factions,
        rule_entities=scene.rule_entities,
        events=[scene.macro_scene_event],
        relationships=scene.relationships,
    )


def merge_graphs(target: GraphExtraction, extra: GraphExtraction) -> None:
    """Merge `extra` into `target` in place, deduplicating by name/title (or subject+predicate+object)."""
    for field, key in (
        ("characters", "name"),
        ("locations", "name"),
        ("items", "name"),
        ("quests", "name"),
        ("events", "label"),
        ("factions", "name"),
        ("rule_entities", "name"),
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
        ("quests", "name"), ("events", "label"), ("factions", "name"),
        ("rule_entities", "name"),
    ):
        for item in getattr(result, field):
            evidence.setdefault((field, getattr(item, key)), []).append(chunk_index)
    for r in result.relationships:
        evidence.setdefault(("relationships", (r.subject, r.predicate, r.object)), []).append(chunk_index)


def _combined_known(known_world: dict[str, list[str]] | None,
                    merged: GraphExtraction) -> dict[str, list[str]]:
    """Campaign gazetteer + names already extracted in earlier scenes of THIS
    session, so scene 7 reuses the exact names scene 2 introduced (catches
    Goblin-Dorf/Goblinlager splits before the registry ever sees them)."""
    combined = {k: list(v) for k, v in (known_world or {}).items()}
    for label, items in (("Characters", merged.characters), ("Locations", merged.locations),
                         ("Factions", merged.factions), ("Quests", merged.quests),
                         ("Items", merged.items)):
        lines = combined.setdefault(label, [])
        for item in items:
            name = item.name
            if not any(line.casefold().startswith(name.casefold()) for line in lines):
                lines.append(name)
    return combined


def extract_session(extractor, chunks: list[str],
                    cast_names: list[str] | None = None,
                    rule_names: list[str] | None = None,
                    known_world: dict[str, list[str]] | None = None,
                    fail_dir=None) -> tuple[GraphExtraction, dict]:
    """Run every chunk of one session; returns (merged graph, evidence sidecar).

    With `fail_dir`, a chunk that still fails after the retry is dumped there
    and skipped — a partial session beats no session (PLAN.md phase 5).
    """
    merged = GraphExtraction()
    evidence: dict = {}
    for i, chunk in enumerate(chunks, start=1):
        try:
            result = extract_chunk(extractor, chunk, i, cast_names, rule_names,
                                   _combined_known(known_world, merged))
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
            "+%d rels",
            i, len(chunks),
            len(result.characters), len(result.locations), len(result.items),
            len(result.quests), len(result.events), len(result.factions),
            len(result.relationships),
        )
    return merged, evidence


# --- WP13.1: semantic scene segmentation (docs/evolution/13) ---
# A fast pre-pass over the whole session's segments returns scene boundaries;
# chunking.scene_chunks then slices ONLY at those boundaries so each chunk is
# one logical scene. Flagship-only (needs a big context window); the local
# profile keeps chunking.pack_segments' char budget.

_SEGMENT_PROMPT = (
    "Below is one TTRPG (Daggerheart) session transcript, one line per segment as "
    "'<index>: <speaker>: <text>'. Partition it into consecutive SCENES — a scene is "
    "one coherent narrative unit (an encounter, a negotiation, a journey leg, a shopping "
    "stop). Return scenes in order as start_segment/end_segment index ranges that together "
    "cover EVERY segment exactly once, with no gaps or overlaps: the first scene starts at "
    "index 0 and each scene's start_segment is the previous end_segment + 1. Prefer fewer, "
    "larger scenes over many tiny ones — never split a single fight or conversation across "
    "two scenes. Give each a short title.\n\n"
)


def _segment_listing(segments: list[dict]) -> str:
    return "\n".join(
        f"{i}: {s.get('speaker', '')}: {s.get('text', '')}" for i, s in enumerate(segments))


def segment_session(segmenter, segments: list[dict]) -> "list":
    """WP13.1: return ordered SceneBoundary list for the whole session. Falls
    back to a single all-covering scene if the pre-pass fails or returns nothing
    (chunking then packs it by budget) — a degraded chunking beats no session."""
    from .schema import SceneBoundary
    if not segments:
        return []
    try:
        result: SceneSegmentation = segmenter.invoke(_SEGMENT_PROMPT + _segment_listing(segments))
    except Exception as exc:
        log.warning("scene segmentation failed (%s) — falling back to one scene", exc)
        result = None
    scenes = (result.scenes if result else None) or [
        SceneBoundary(start_segment=0, end_segment=len(segments) - 1, label="full session")]
    return scenes
