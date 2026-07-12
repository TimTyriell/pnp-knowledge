# Evolution Spec — pnp-graph-service → canonical, rules-grounded, high-recall KB

**Read this file first, then open only the doc for the work package you're on.** This set is deliberately split so you don't load 2,000 lines of context to do one focused change.

> **Status (2026-07-12): largely implemented.** WP0–WP8, WP10 and WP11 have
> landed in `src/pnp_graph/` (WP4 Scenes shipped then reverted — see `04`).
> Results and learnings per milestone: `../learnings/MIGRATION_NOTES.md`.
> **WP13** — Agentic Hybrid-RAG ingestion (`13`): semantic scene chunking +
> one-event-per-scene "capsule" schema + GraphRAG entity summaries + chunk-level
> vector index, on the DeepSeek flagship profile — **landed**. Successor to
> **WP12** (`12`, extraction-quality overhaul) — WP12's trait removal and the
> two-profile DeepSeek shift also landed; WP13 replaced WP12's bigger-fixed-chunk
> + `List[Event]` design with semantic scenes and capsule events. Both supersede
> the recall-first stance of `06`/`10`.
> **WP14 (`14`, 2026-07-12) — landed**: `Item` = named artifacts only,
> `RollEvent` removed from the graph, and the vector "book" split onto its own
> `:Chunk` label + index (skeleton is now cleanly `:Entity`). Measured
> 2-session bloat behind WP12–14: `../learnings/KG_Bloat_2Session_20250401-09.md`.
> **Open: WP9** — second-session multi-session proof + the bitemporal
> write-side (`store.py` does not stamp `valid_from`/`valid_to` yet;
> `STATE_PREDICATES` in `config.py` and the as-of read path in `retrieve.py`
> are already in place). References to `PLAN.md` throughout these docs point
> to the superseded original plan, archived at `../archive/PLAN.md`.

## Goal (one line)

Keep the local, private, high-recall `qwen3:14b` pipeline in `src/pnp_graph/`, but make its **output schema and guarantees match the Claude-authored report graph (Graph 3)** — canonical IDs, real entity resolution, scenes, rules/SRD grounding, and TTRPG-native `Decision`/`RollEvent` semantics — **without** the report loader's `attributes_json` opacity. "More knowledge" = Graph 3's structure at Graph 2's (or higher) recall.

## The three graphs in this repo (context you need)

| | Source | Sink | Schema | Recall |
|---|---|---|---|---|
| **Graph 1 `aikg1`** | vendored `../ai-knowledge-graph` free-form triples via `compare/run_both.py` | `:7688` | `:Entity` + arbitrary predicates | very high, unstructured |
| **Graph 2 `cp1`** | **THIS pipeline** (`src/pnp_graph/`) | `:7687` | typed labels keyed on **`name`** | medium |
| **Graph 3 `report1`** | **Not this pipeline** — Claude-authored JSON in `Session_Report_*.md`, loaded by `reports/load_report_graph.py` | `:7689` | `:Entity{id,type}` canonical + `attributes_json` | low (hand-curated) |

**Key architectural fact:** Graph 3's quality comes from an expensive Claude authoring pass, not this service. We do **not** make `qwen` imitate that at runtime. We lift Graph 3's *schema* onto the local pipeline and reuse the occasional report as a **gold cross-check** (see `07_neo4j_and_qa.md`).

## Design invariants (apply to every work package)

1. Canonical `id` is the merge key — **never `name`**. Resolution happens before the write.
2. Closed vocabularies for node `type` and relationship type — validate, don't free-form.
3. Native, queryable properties only — **no `attributes_json`**.
4. Every node and edge carries `confidence ∈ {high,medium,low}`, `session_id`, `evidence_chunks[]`; **state** edges additionally carry `valid_from`/`valid_to` and are closed-and-appended, never overwritten (`11`).
5. Extract generously, resolve deterministically — recall is a prompt dial, correctness is a downstream layer.
6. Idempotent + versionable — aligns with `PLAN.md` append/version policy.
7. Local-first, one 14B in VRAM at a time (RTX 4070 Ti, 12 GB).

## Document map

- `../archive/01_current_state.md` — the pre-WP1 as-is + defects this spec was written against (historical; the defects are fixed).
- `02_target_architecture.md` — the canonical `:Entity{id}` model, module layout, `schema.py`/`store.py` sketches.
- `03_entity_resolution.md` — **the #1 fix.** `resolve.py`, ID scheme, alias registry. Do this before anything else.
- `09_player_character_mapping.md` — player↔character separation, **session-bound** `PLAYS` control parsed from the transcript's `Player (Character)` speaker labels, and action attribution. Read right after `03` (it corrects `03`'s player/character handling).
- `04_scenes_provenance_vocab.md` — provenance on all facts (`evidence_chunks[]`, no Scene nodes — reverted, see file), closed relationship vocab.
- `05_srd_and_semantics.md` — SRD/`RuleEntity` grounding + `Decision`/`RollEvent` extraction.
- `06_llm_recall_strategy.md` — how to get "more knowledge" out of a local 14B.
- `07_neo4j_and_qa.md` — constraints, QA queries, and the `reconcile-report` gold cross-check.
- `08_roadmap.md` — WP0–WP10 in order, each with an acceptance criterion; `PLAN.md` alignment; assumptions; anti-patterns.
- `10_significance_and_recurrence.md` — **guardrail on recall.** Prevents recurring routine behavior (e.g. "plays music often") from inflating into hundreds of near-duplicate nodes, and separates narrative significance from raw frequency. Read before finishing WP6/WP7 — without it, the recall lift causes exactly the problem it describes.
- `11_bitemporal_and_retrieval.md` — the **bitemporal edge contract** (state/event/identity classes, `valid_from`/`valid_to`, death workflow, append-only contradictions) and the **retrieval layer** (`nomic-embed-text` + Neo4j vector index, GraphRAG-style local search *without* adopting the GraphRAG framework — verdict inside). Supersedes `04`'s edge-property list where they differ.
- `12_extraction_quality_overhaul.md` — **landed.** Native parsimony in the extraction layer: scene-level chunking, schema-forced significance, `Trait`-node removal, few-shot anti-patterns. Downstream pruning is an anti-pattern here. Superseded in part by `13`'s capsule schema and `14`'s Item/Roll gates. Supersedes the recall-first tone of `06` and the WP6b aggregation of `10`.
- `13_agentic_hybrid_rag.md` — **landed.** Semantic scene chunking, one combined `SceneExtraction` call/scene, capsule macro-event, GraphRAG entity summaries, chunk-level vector index.
- `14_item_roll_parsimony_and_chunk_split.md` — **landed (2026-07-12).** `Item` = named artifacts only (`is_named_artifact`), `RollEvent` removed from the graph, and the vector "book" split onto its own `:Chunk` label + `chunk_embedding` index (skeleton is cleanly `:Entity`). Schema-breaking — wipe + re-ingest.

## Execution order

Follow `08_roadmap.md`. Short version: **WP1 (entity resolution) is the gate** — most other gains depend on canonical IDs existing first. **WP6b (`10`) must land before WP7** — raising recall without the recurrence guardrail amplifies node/edge inflation rather than adding real information.

**Now (2026-07-12): WP12–WP14 have landed** — the parsimony overhaul (trait removal, capsule events, Item/Roll gates) and the `:Chunk` split are in. The graph is now a clean `:Entity` skeleton + a `:Chunk` vector book. **Next: WP9** (bitemporal write-side) — now worth doing on a low-noise graph instead of versioning the noise.
