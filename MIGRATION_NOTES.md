# Migration Notes — evolution spec (docs/evolution/) WP0–WP10

## Baseline (WP0, recorded 2026-07-03)

From `state/ingest_log.jsonl`, run of 2026-07-01 on `2025-03-26_RF_ROCKGeeRUFw.json`
(name-keyed pipeline, pre-WP1):

| chunks | characters | locations | items | quests | events | factions | relationships |
|---|---|---|---|---|---|---|---|
| 32 | **15** | 7 | 12 | 5 | 40 | 4 | 167 |

15 Character nodes for ~5 real people — the duplicate-identity defect
`docs/evolution/01_current_state.md` describes. This is the number WP1 must
collapse to ~6 (Lindo Laut, Dodo, Cookie, Deniz-GM, + genuine NPCs).

Speaker labels confirmed in the transcript:
`Tim (Lindo Laut)`, `Marco (Dodo)`, `Celin (Cookie)`, `Deniz (GM)`.

## Assumption calls (docs/evolution/08_roadmap.md §Assumptions)

Proceeding with the spec's own defaults; flag if any is wrong:

1. **Convergence target:** yes — main pipeline migrates to `:Entity{id}` on `:7687`;
   `:7689` report DB stays as gold cross-check via `reconcile-report`.
2. **Scene granularity:** v1 = 1 scene per chunk. LLM scene-merging deferred.
3. **SRD source:** seed subset only until licensing confirmed. Candidate bulk
   source: sibling `c:\dev\pnp\daggerheart-data` JSON.
4. **Language:** content German; predicates/confidence English tokens.
5. **Predicates:** validate-and-map in `resolve.py` (no hard `Literal` yet).

## Milestones

- **M1 = WP1 + WP1b + WP2 + WP3** (one `store.py` rewrite, not three):
  canonical ids + `resolve.py`, Player/Character split + per-session `PLAYS`,
  provenance on all facts, closed predicate vocab.
- **M2 = WP4** scenes. **M3 = WP5+WP6** SRD + Decision/RollEvent.
  **M4 = WP7+WP8** two-pass recall + reconcile-report. **M5 = WP9+WP10**
  multi-session + golden-file regression.

## M1 result (verified 2026-07-03, re-ingest of `2025-03-26`)

`:7687` wiped, `entity_id` constraint live, re-ingested through
extract→resolve→store. **86 entities, 228 edges (46 dropped as unresolved
endpoints, logged to `state/failures/2025-03-26/dropped_edges.jsonl`)**.

| type | count |
|---|---|
| Event | 41 | Item | 17 | Location | 7 | Quest | 7 | Faction | 5 |
| Player | 4 | Character | 4 | Session | 1 |

- **Character count: 4** (Lindo Laut, Dodo, Cookie, Deniz-GM) — was 15. WP1
  acceptance met (one node per real person).
- **Player/Character split**: 4 `Player` + 4 `Character`, one `PLAYS{seq}` edge
  each, all seq=1. No in-fiction edge lands on a `Player` node. WP1b met.
- QA1 (dup names), QA2 (cross-type name collision), QA3 (missing provenance)
  all **empty/0**.
- Rel-type histogram: `PARTICIPATED_IN`(48) `MENTIONED_IN`(42) `IN_SESSION`(41)
  `KNOWS`(15) `LOCATED_IN`(14) `AT_LOCATION`(12) `OWNED_BY`(11) `RESULTED_IN`(10)
  `OWNS`(9) `TRIGGERED`(9) `APPEARS_IN`(4) `PLAYS`(4) `RELATES_TO`(4) `USES`(3)
  `HOSTILE_TO`(1) `ALLIED_WITH`(1) — every type ∈ `ALLOWED_PREDICATES`.
  `RELATES_TO`'s 4 are genuinely off-vocab model output (`HAS_ABILITY`,
  `HAS_RULE`, `PLANS_TO_USE`, `PROTECTED`, `SPOKEN_TO`, `USED`,
  `USES_ACCENT`, `WARNING` seen — coerced + logged, not silently dropped). WP3 met.
- 46 dropped edges is high (~17% of extracted relationships) — mostly the
  model referencing an `Event` by a paraphrased title that didn't survive to
  `surface_to_id`. Worth revisiting once M2 scenes/M4 two-pass land; not a
  blocker (spec explicitly prefers dropping over phantom nodes).

## M2 result (WP4 scenes, verified 2026-07-03)

Re-ingest: 118 entities, 438 edges. 32 `Scene` nodes (`seq` 1–32, 1 scene =
1 chunk), all `IN_SESSION`. QA5 (Event/RollEvent/Decision without
`EVIDENCED_IN`→Scene) **empty**. `evidence_scenes[]` on nodes and on 135 edges;
"replay session in order" query works (scene-seq → events).

**M2 reverted (2026-07-11):** live-graph inspection showed `Scene`/`EVIDENCED_IN`/
`IN_SESSION`-to-Scene made up ~50% of all edges for zero information not
already on `evidence_scenes[]` — pure structural noise, not a timeline
feature (v2 LLM scene-merging, the thing that would've made Scenes a real
narrative spine, was never built). `Scene` nodes and `EVIDENCED_IN` removed;
provenance is now a plain `evidence_chunks: [int]` property on the fact
itself, no separate node or edge. See `docs/evolution/04_scenes_provenance_vocab.md`.

## Breaking changes at M1

- `:7687` is **wiped** before the first M1 ingest (old graph is name-keyed and
  irreconcilable; fully reproducible from transcripts).
- `ensure_constraints` drops `character_name`/`location_name`/`faction_name`
  and creates `entity_id` uniqueness + `type`/`session_id` indexes.
- All nodes become `:Entity {id, type, name, session_id, confidence, ...}`.
  `Session` keeps its shape (`:Entity {type:'Session'}`).
- Fuzzy matching uses stdlib `difflib` (ratio ≥ 0.9), not `rapidfuzz`; no APOC.
