# docs/ — map

State of the pipeline as of 2026-07-11. For file-by-file architecture see the
repo-root `CLAUDE.md` (kept current); this folder holds design docs, learnings,
and archived history.

## Layout

| Folder | What | Read when |
|---|---|---|
| [evolution/](evolution/) | The active design spec (WP0–WP11). **Largely implemented** — see the status note in its README. Still the reference for *why* the code is shaped the way it is, and the spec for the one open work package (WP9 bitemporal write-side). | Changing schema, resolution, vocab, retrieval. |
| [learnings/](learnings/) | Verified results and analysis — what was measured, what worked, what was reverted and why. | Before re-attempting anything that looks "missing" (e.g. Scene nodes — tried, reverted). |
| [archive/](archive/) | Superseded docs and old data exports. Historical context only — nothing in here describes the current system. | Almost never. |

## Current state (as-is, short)

- Pipeline: `transcripts/*.json → chunking → extract (qwen3:14b, two-pass) →
  resolve (canonical :Entity{id}) → store (Neo4j :7687) → embed (vector index)`.
  CLI: `ingest`, `reconcile-report`, `ask`.
- Canonical IDs, player/character split, closed predicate vocab, provenance on
  every fact, SRD grounding, Decision/RollEvent, Trait aggregation, golden-file
  regression tests, retrieval layer — all landed (WP0–WP8, WP10, WP11).
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
