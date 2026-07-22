# docs/ — map

State of the pipeline as of 2026-07-12. For file-by-file architecture see the
repo-root `CLAUDE.md` (kept current); this folder holds design docs, learnings,
and archived history.

## Layout

| Folder | What | Read when |
|---|---|---|
| [evolution/](evolution/) | The active design spec (WP0–WP14). **Largely implemented** — see the status note in its README. Still the reference for *why* the code is shaped the way it is, and the spec for the open work packages (WP9 bitemporal write-side). Latest: WP14 (Item/Roll parsimony + `:Chunk` split). | Changing schema, resolution, vocab, retrieval, chunking. |
| [learnings/](learnings/) | Verified results and analysis — what was measured, what worked, what was reverted and why. | Before re-attempting anything that looks "missing" (e.g. Scene nodes — tried, reverted). |
| [archive/](archive/) | Superseded docs and old data exports. Historical context only — nothing in here describes the current system. | Almost never. |

## Current state (as-is, short)

- Pipeline (flagship): `transcripts/*.json → semantic scene segmentation →
  megachunk → extract (DeepSeek, one `SceneExtraction` call/scene) → resolve
  (canonical :Entity{id} + :Chunk passages) → store (Neo4j :7687) → embed (two
  vector indexes)`. CLI: `ingest`, `reconcile-report`, `ask`, `summarize-entities`.
- Canonical IDs, player/character split, closed predicate vocab, provenance on
  every fact, SRD grounding, `Decision`, golden-file regression tests, retrieval
  layer — all landed (WP0–WP8, WP10, WP11).
- **Landed since (WP12–WP14):** `Trait` node removed (quirks → `Character.
  description`/`character_summary`); DeepSeek flagship profile + megachunks;
  single-pass `SceneExtraction` with schema-forced significance ("pay to mint");
  chunk-level vector index. **WP14 (2026-07-12):** `Item` minted only for named
  artifacts, `RollEvent` removed entirely, and the vector "book" split onto its
  own `:Chunk` label + index so `MATCH (n:Entity)` is a clean skeleton. Spec:
  [evolution/14_item_roll_parsimony_and_chunk_split.md](evolution/14_item_roll_parsimony_and_chunk_split.md).
  Schema-breaking — wipe `:7687` + re-ingest.
- **Open: WP9** — multi-session ingest proof + bitemporal edge lifecycle on the
  write side (`valid_from`/`valid_to` stamping in `store.py`). Spec:
  [evolution/11_bitemporal_and_retrieval.md](evolution/11_bitemporal_and_retrieval.md).
- Also still open from the archived PLAN.md: file-hash resume-skip in
  `ingest.py` (every run reprocesses every session) and per-session `:Summary`
  nodes.

## Learnings index

- [learnings/MIGRATION_NOTES.md](learnings/MIGRATION_NOTES.md) — WP0 baseline,
  M1/M2 measured results, the **M2 Scene-node revert** (structural noise,
  ~50% of edges for zero signal), breaking changes.
- [learnings/KG_Bloat_2Session_20250401-09.md](learnings/KG_Bloat_2Session_20250401-09.md)
  — **2-session bloat analysis** (German): the measured numbers behind WP12
  (374 single-use traits, 33 % orphan events, 0 % consequence edges) and the
  code-level root cause. Read before touching extraction.
- [learnings/KG_Qualitaetsanalyse_S01_20250326.md](learnings/KG_Qualitaetsanalyse_S01_20250326.md)
  — quality analysis of the S01 graph (German).

## Archive index

- [archive/PLAN.md](archive/PLAN.md) — original architecture plan. Phase 1
  (module split) done; its identity/versioning ideas were superseded by the
  evolution spec (canonical IDs instead of name-keys, bitemporal edges instead
  of `:Fact` nodes). Phases 2 (resume) and 4 (summaries) remain open ideas.
- [archive/01_current_state.md](archive/01_current_state.md) — the pre-WP1
  defect analysis the evolution spec was written against. All four structural
  defects it lists are fixed.
- [archive/graph-exports/](archive/graph-exports/) — Neo4j JSON exports of the
  three-graph comparison era (aikg1/cp1/report1 snapshots).
