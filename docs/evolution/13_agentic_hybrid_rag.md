# WP13 — Agentic Hybrid-RAG Ingestion (semantic scenes, capsule events, critic, entity summaries)

> **Priority 1. Successor to WP12** (`12_extraction_quality_overhaul.md`).
> WP12's trait removal and the DeepSeek two-profile shift already landed (see
> "Already shipped" below); WP13 replaces WP12's *bigger-fixed-chunk* Component 1
> with true semantic scene segmentation, and its *List[Event]* schema with a
> one-event-per-scene "capsule". Written against the 3-session bloat
> (`../learnings/KG_Bloat_2Session_20250401-09.md`): 530+ Events (33 % orphaned),
> 580+ single-use Traits.

## Paradigm (one line)

**Graph = table of contents (macro state, ownership, locations, scene-level
events); Vector store = the book (raw transcript detail).** The KG stops
modelling micro-beats as topology; retrieval (`cli ask`, WP11) serves detail
from embedded transcript text. Extraction runs on a flagship reasoning API
(DeepSeek) where token cost is negligible but the 4k/8k output cap is the real
constraint — so the pipeline is engineered around *small, bounded* structured
output per call, not one giant graph dump.

## Design invariant added

> **9. One scene, one macro-event.** A transcript chunk is exactly one logical
> scene (semantic boundaries, not token budget). Each chunk yields at most ONE
> `Event`, and only with a filled `narrative_significance_reasoning`. Recurring
> characterization updates a Character property, never mints a node (invariant 8,
> WP12), and the biography text is (re)written by a summarization pass, not
> accumulated raw.

## Already shipped (WP-A / WP-B, 2026-07-12)

- **Trait eradication** — `Trait` node type + `KNOWN_FOR` gone end-to-end;
  quirks fold into `Character.description`. (WP12 Component 3 — done.)
- **Event restriction (prompt)** — `_EVENT_PROMPT` now demands whole-scene /
  permanent-state-change events, a 20-min combat = one event.
- **Two extraction profiles** — `PNP_PROFILE=local|flagship` in `config.py`;
  `flagship` = DeepSeek API (`langchain-openai` `ChatOpenAI`,
  `method="function_calling"`), megachunks (`CHUNK_SIZE=44000` chars). Local
  Ollama kept for dev smoke only. Embeddings + `ask` stay local.

WP13 turns the megachunk (a blunt char budget) into a *scene* (semantic), and
the "one macro event per scene" from a prompt hope into a schema guarantee.

---

## WP13.1 — Semantic Scene Chunking (P1, matched pair with 13.2)

**Problem:** even a 44k-char megachunk cuts on a char budget — it can still
split a battle in half and destroy the causal arc.

**Solution:** an LLM pre-pass segments the session into scenes; `chunking.py`
slices segments *only* at those boundaries. Chunk length becomes whatever the
scene is (bounded by the API context window, not a fixed budget).

**`schema.py`** — new models:
```python
class SceneBoundary(BaseModel):
    start_segment: int   # inclusive index into the session's segment list
    end_segment: int     # inclusive
    title: str           # short scene label, for logging/debug

class SceneSegmentation(BaseModel):
    scenes: list[SceneBoundary] = []
```

**`extract.py`** — `segment_session(segmenter, segments) -> list[SceneBoundary]`:
feed a line-numbered condensed view (`{i}: {speaker}: {text}`) of the whole
session; `segmenter = llm.with_structured_output(SceneSegmentation, method=...)`.
- **Context guard:** a long session can exceed even a 64k window. If the
  condensed transcript exceeds a token budget, window the segmentation over
  overlapping spans of ~400 segments and stitch (a boundary within the overlap
  wins once). `ponytail:` single-pass first; add windowing only when a real
  session overflows.

**`chunking.py`** — `scene_chunks(segments, boundaries) -> list[str]`: join each
boundary's segment span into one chunk text (reuse the existing turn-join /
speaker-label formatting from `pack_segments`). No overlap between scenes
(a scene is self-contained). `load_session` gains a branch:
```python
if PROVIDER == "deepseek":           # flagship: semantic scenes
    boundaries = segment_session(segmenter, segments)
    chunks = scene_chunks(segments, boundaries)
else:                                 # local dev smoke: keep char budget
    chunks = pack_segments(segments)
```
`segment_session` needs the LLM, so either `load_session` takes the segmenter,
or (cleaner) session loading stays pure and `ingest.py` orchestrates:
`segments = raw_segments(path); chunks = scene_chunks(...)`.

**Acceptance:** a session yields ~10-30 scene chunks (not 100s of micro-chunks);
`state/ingest_log.jsonl` records `scenes` per session; spot-check that no scene
boundary lands mid-combat (manual, one session).

## WP13.2 — Capsule Event Schema (P1)

**1 chunk = 1 scene ⇒ enforce 1 event.** Remove the `List[Event]` escape hatch
so the model can't inflate.

**`schema.py`:**
```python
class Event(BaseModel):
    title: str
    summary: str = ""
    participants: list[str] = []
    location: str | None = None
    narrative_significance_reasoning: str = Field(   # REQUIRED, no default
        description="Justify why this scene alters world state (a death, a "
        "quest change, ownership change, alliance...). If you cannot, the "
        "scene has no macro-event — leave it empty is NOT allowed; pick the "
        "single most consequential change of the scene.")

class EventExtraction(BaseModel):
    macro_scene_event: Event                 # was: events: list[Event]
    roll_events: list[RollEvent] = []        # a scene may still have several rolls
    decisions: list[Decision] = []
    relationships: list[Relationship] = []
```
`narrative_significance_reasoning` has no default → `function_calling`/
`json_schema` marks it required → the model must reason before it can emit the
event ("pay to mint", WP12 mechanism, now per-scene).

**`extract.py`** `extract_chunk`: Pass 2 returns one `macro_scene_event`; wrap it
into the aggregate as a 1-element list so downstream (`merge_graphs`,
`resolve_graph`) is unchanged. `GraphExtraction.events` stays a list (one per
scene, appended across chunks).

**Remove N3 event consolidation** (`propose_event_groups` /
`apply_event_consolidation`, `EventConsolidation`/`EventGroup`): it existed to
merge near-duplicate titles minted by *micro*-chunks. One-event-per-scene makes
cross-chunk title dups impossible. Delete from `extract.py`, `schema.py`,
`ingest.py`, `build_extractor` (drop the 3rd structured extractor).

**Carry over WP12's consequence-edge QA** (`store.py::_QA_QUERIES`, a blocker):
```cypher
MATCH (e:Entity {type:'Event'})
WHERE NOT (e)-[:PARTICIPATED_IN|TARGETS|RESULTED_IN|TRIGGERED]-()
RETURN count(e) AS c   // must be 0
```
With one event per scene and required participants, orphan rate collapses.

**Acceptance (vs 3-session baseline 530 events):** **≤ ~90 events** (≈ scenes ×
sessions); 0 orphan events; every event has `narrative_significance_reasoning`.

## WP13.4 — GraphRAG Entity Summarization (P2, independent)

Replaces the value Trait nodes used to carry (character personality) with a
GraphRAG "entity summary" property, written by an LLM, not accumulated raw.

**Where micro-behaviors come from:** each scene's `Character.description`
(shipped in WP-A). Resolve appends them to a `behavior_notes` list property on
the Character (same union pattern as `aliases`/`evidence_chunks` in
`resolve.add_entity`) instead of overwriting `description`.

**New `summarize.py` + `cli summarize-entities`** (run after ingest — "async" =
a separate manually/cron-triggered step, NOT a hot-path daemon; `ponytail:`
upgrade to a real queue only if runtime matters):
- For each Character touched since last summary: read existing
  `character_summary` + the new `behavior_notes`; one LLM call rewrites a single
  cohesive German biography paragraph; write back to `character_summary`; clear
  the consumed `behavior_notes`; re-`embed_entities` that character.
- `character_summary` (not `behavior_notes`) becomes the text `embed._entity_text`
  uses for Characters, so retrieval sees a coherent bio.

**Acceptance:** every major Character carries a `character_summary` reflecting
≥2 sessions; 0 Trait nodes (already true); `cli ask` about a character's
personality answers from the summary.

## WP13.3 — Agentic Critic / self-correction (P3, gate on measured need)

An LLM Critic evaluates the assembled per-scene JSON *before* resolve/write; on
finding orphaned events or edges whose endpoints aren't in the entity set, it
returns the defect and the Extraction Agent retries once with the critique
appended.

**`extract.py`** `critique_and_correct(extractors, graph, chunk, cast, ...)`
after Pass 2, ≤1 correction round (bounded cost).

**Reconcile with the deterministic layer (important):** `resolve.py` already
drops hallucinated-endpoint and domain-violating edges, and the WP13.2 QA query
already catches orphan events. The Critic's *only* added value is
*self-correction* (fix-then-keep) over *silent drop* — at the price of +1-2 API
calls per scene. **Do not build it until 13.1/13.2 land and a real flagship run
shows the deterministic drop rate is high enough to hurt recall.** If drops are
rare, skip the Critic (YAGNI).

---

## Priority & sequencing

| P | WP | Why here | Depends on |
|---|----|----------|------------|
| **1** | 13.2 Capsule schema | biggest bloat lever, extends shipped WP-A | — |
| **1** | 13.1 Semantic chunking | makes "1 event/scene" meaningful on flagship | 13.2 |
| **2** | 13.4 Entity summarization | restores Trait's value, independent | WP-A `description` |
| **3** | 13.3 Critic agent | high API cost, overlaps deterministic layer | 13.1/13.2 + a real run |

13.1 and 13.2 are a matched pair — capsule only makes sense with scene chunks;
ship together, flagship-only. Local profile keeps `pack_segments` + emits one
(imperfect) event per char-chunk — acceptable, it is dev-smoke only.

## Migration / rollout
1. Wipe `neo4j-main` (schema break: `Event` fields, N3 gone).
2. Flagship re-ingest one session (`PNP_PROFILE=flagship ... --only <date>`);
   check scene count, event count, `state/failures/`, the orphan-event QA = 0.
3. Regenerate `tests/golden_resolved.json`; update `test_extract.py`
   (single `macro_scene_event`, no N3), add a segmentation test.
4. `cli summarize-entities`; verify `character_summary` on a PC.
5. Full re-ingest once one session is clean; `reconcile-report` for recall.

## Risks
- **Segmentation context overflow** on long sessions → windowed pre-pass (13.1).
- **Required reasoning field** can push the model to force a weak event on a
  filler scene → prompt must allow "the scene's most consequential change" to be
  minor, and the orphan-QA + `reconcile-report` catch over/under-minting.
- **DeepSeek output cap (8k)** per scene: one event + a scene's rolls fits
  easily; the cap was the reason for capsule, not a threat to it.
- **Critic cost** — see 13.3; gated deliberately.
