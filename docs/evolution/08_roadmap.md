# 08 — Roadmap, PLAN.md Alignment, Assumptions & Anti-patterns

## Work packages (do in order)

Each is independently shippable and verified by re-ingesting `2025-03-26`.

| WP | Scope | Doc | Acceptance |
|---|---|---|---|
| **WP0** | Recon; reproduce baseline; write `MIGRATION_NOTES.md` | `01` | baseline graph reproduced on `2025-03-26` |
| **WP1** | Canonical IDs + `resolve.py` + `store.py` rewrite **(the gate)** | `03` | one node per real character (was 15→~6); dup & cross-type QA empty; `entity_id` constraint live |
| **WP1b** | Player/Character split + per-session `PLAYS` parsed from `Player (Character)` labels + attribution (`format_turn` emits the character) | `09` | `Player` and `Character` are distinct nodes joined by a `PLAYS {session_id}` edge; the composite `Tim (Lindo Laut)` string never becomes a node; every in-fiction edge on `2025-03-26` points to a `Character`, none to a `Player` |
| **WP2** | Provenance on all nodes + confidence normalization | `04` | 0 facts missing `confidence`/`session_id`; no German confidence tokens |
| **WP3** | Closed relationship vocab enforcement | `04` | every rel type ∈ `ALLOWED_PREDICATES` (or logged `RELATES_TO`) |
| **WP4** | Scenes as nodes; evidence → scenes | `04` | `Scene` nodes with `seq`; timeline QA empty; "replay in order" works |
| **WP5** | SRD / `RuleEntity` grounding | `05` | PCs link to shared SRD ids; rules-consistency query runs |
| **WP6** | `Decision` + `RollEvent` extraction | `05` | traceable `Decision → … → Quest` causal chain |
| **WP6b** | `Trait` aggregation + Event-minting filter (do **before** WP7) | `10` | recurring behavior (e.g. music) → one `Trait` with incrementing `count`, not N `Event` nodes; recurrence-vs-significance QA query empty |
| **WP7** | Recall lift (two-pass prompts / optional aikg feed) | `06` | fact count > Graph 3's 27, all QA green, **and** WP6b's recurrence guardrail holds under the higher recall |
| **WP8** | `reconcile-report` gold cross-check | `07` | diffs local vs report; proposes alias additions |
| **WP9** | Multi-session proof + versioning hook | below | 2nd session; recurring entities MERGE to one id spanning both |
| **WP10** | Regression harness | below | golden-file test; CI fails on dup/off-vocab/missing-provenance |

- **WP9 detail:** ingest a second session and confirm recurring entities `MERGE` to a single id spanning both sessions, cross-session timeline ordering works, and no duplicates appear. Leaves the graph ready for PLAN.md phase-3 `:Fact` stamping.
- **WP10 detail:** fixed transcript → expected node/edge set as a golden file; CI blocks schema drift, duplicate creation, off-vocab types, and missing provenance. Extends the existing `tests/` (currently only `test_chunking.py`).

## How this rides on top of PLAN.md (don't fight it)

PLAN.md already commits to append/version (`:Fact` with `valid_from`/`valid_to`), per-session `:Summary` nodes, resume via file-hash, and safety nets. This spec is the **identity/schema substrate those phases need**:

- **Canonical `id` (WP1) is a hard prerequisite for versioning** — you cannot stamp `valid_from`/`valid_to` on an entity that forks into three name-nodes. **Do WP1 before PLAN phase 3.**
- PLAN safety-nets **#4 (name normalization)** and **#5 (endpoint validation)** are subsumed and upgraded by `resolve.py`.
- `:Fact` versioning (PLAN phase 3) attaches cleanly to `:Entity{id}`; keep the `valid_to IS NULL = current` rule.
- Per-session `:Summary` (PLAN phase 4) is unaffected and improves — summaries hang off deduped canonical entities.
- Resume/state (PLAN phase 2) and retry/repair (phase 5) proceed as written; WP7 references the same `state/failures/` sink.

## Assumptions to confirm before coding (WP0)

1. **Convergence target.** Migrate the main pipeline to `:Entity{id}` on the existing `:7687`; keep the `:7689` report DB and use it via `reconcile-report`. This spec assumes the team wants convergence — confirm.
2. **Scene granularity.** Start `1 scene = 1 chunk`; upgrade to LLM scene-merging only if you want 1:1 alignment with the report's `S01–S07` (ties into PLAN.md's `seq`-from-`S<NN>` open question).
3. **SRD source & licensing.** No SRD data ships today. WP5 introduces `data/daggerheart_srd.json`; confirm the source/licensing for full content (a seed subset is fine to start).
4. **Language policy.** Content stays German; vocab/confidence tokens English (per PLAN.md).
5. **Predicate tightening.** Keep the validate-and-map layer (recommended) vs hard-`Literal` on `schema.py:Relationship.predicate` — decide once the vocab is stable.

## Anti-patterns to actively prevent (each seen in one of the three graphs)

- Actor baked into relationship type (`TELLS_VIA_DENIZ`) / predicate sprawl → **Graph 1**. Prevent via closed vocab (`04`).
- Category words as nodes (`character`, `creature`) → **Graph 1**. Prevent via closed types + resolution.
- Name-keyed duplicate entities → **Graph 2** (`store.py` MERGE on name). Fixed by `03`.
- Same name across two types (`Daggerheart` Location+Faction) → **Graph 2**. Caught by QA query 2 (`07`).
- Game resources as Items (`Hope`) → **Graph 2**. Fixed by type rules (`02`/`05`).
- Queryable data hidden in `attributes_json` / relationships hidden as `*_ref` strings → **Graph 3 report loader**. **Do not port to the main pipeline** (invariant 3 in `README.md`).
- Over-pruning away the session's texture → **Graph 3**. Countered by the recall strategy (`06`).

## Expected edges per session (sizing reference)

Measured against the real transcript (`transcripts/2025-03-26_RF_ROCKGeeRUFw.json`, 45 min): running the actual `chunking.load_session_chunks` produces **32 raw chunks** at `CHUNK_SIZE=2000`; merged to report-matching granularity that's **~7–10 Scenes**. Projected edge count once WP1–WP8 land, by category:

| Category | Basis | Est. edges/session |
|---|---|---|
| Core content (`MEMBER_OF`,`OWNED_BY`,`LOCATED_IN`,`PARTICIPATED_IN`,…) | Graph 2 today = 232, minus dedup collapse from entity resolution | 180–220 |
| `RollEvent` + edges (`ROLLED`,`TARGETS`,`RESULTED_IN`) | Graph 3 captured 1 roll for 45 min — under-recall; a real session has more like 10–20 | 30–50 |
| `Decision` + edges (`DECIDED`,`TRIGGERED`) | Graph 3 had 1; realistic recall is a handful per session | 10–15 |
| SRD linking (`HAS_CLASS`,`HAS_ANCESTRY`,`USES_CARD`,`RUNS`,…) | One-time-ish character-sheet facts; heavier in intro sessions, lighter in pure-combat ones | 5–20 (variable) |
| `PLAYS` (player→character, WP1b) | Deterministic: one per player + GM | 4–5 |
| Scene infra (`IN_SESSION` + `EVIDENCED_IN` on **node-facts only**, see `04`) | ~7–10 Scenes × `IN_SESSION`, plus `EVIDENCED_IN` from Events/Items/Quests/RollEvents/Decisions — **not** from relationship-facts | 50–70 |

**Total: ~280–370 edges per 45-min session** — well above Graph 3's 27, below Graph 2's current 232-with-duplicates, and nowhere near Graph 1's 199-predicate sprawl (vocabulary stays closed throughout). Scaled to the full 100+ hour campaign (~133 sessions this length): **~37,000–49,000 edges** total — clean and well within comfortable Neo4j range. Treat this as a sizing sanity check, not a hard target: WP7's actual acceptance criterion is "exceeds Graph 3's 27 while all QA in `07` stays green," not a specific number.

## Target end-state

The local `qwen3` pipeline emits `:Entity{id}` canonical, rules-grounded, scene-anchored, fully-provenanced graphs at **higher recall than the hand-authored report** — with the report retained as a gold cross-check, and everything idempotent and versionable per PLAN.md.
