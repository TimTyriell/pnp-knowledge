# 08 — Roadmap, PLAN.md Alignment, Assumptions & Anti-patterns

> **Status (2026-07-11):** WP0–WP8, WP10, WP11 done (WP4 reverted — see `04`).
> **WP9 is the open work package.** Results per milestone:
> `../learnings/MIGRATION_NOTES.md`. `PLAN.md` is archived at
> `../archive/PLAN.md`; doc `01` at `../archive/01_current_state.md`.

## Work packages (do in order)

Each is independently shippable and verified by re-ingesting `2025-03-26`.

| WP | Scope | Doc | Acceptance |
|---|---|---|---|
| **WP0** | Recon; reproduce baseline; write `MIGRATION_NOTES.md` | `01` | baseline graph reproduced on `2025-03-26` |
| **WP1** | Canonical IDs + `resolve.py` + `store.py` rewrite **(the gate)** | `03` | one node per real character (was 15→~6); dup & cross-type QA empty; `entity_id` constraint live |
| **WP1b** | Player/Character split + per-session `PLAYS` parsed from `Player (Character)` labels + attribution (`format_turn` emits the character) | `09` | `Player` and `Character` are distinct nodes joined by a `PLAYS {session_id}` edge; the composite `Tim (Lindo Laut)` string never becomes a node; every in-fiction edge on `2025-03-26` points to a `Character`, none to a `Player` |
| **WP2** | Provenance on all nodes + confidence normalization | `04` | 0 facts missing `confidence`/`session_id`; no German confidence tokens |
| **WP3** | Closed relationship vocab enforcement | `04` | every rel type ∈ `ALLOWED_PREDICATES` (or logged `RELATES_TO`) |
| **WP4** | ~~Scenes as nodes~~ — shipped then reverted; evidence is a plain `evidence_chunks[]` property, no Scene node/edge | `04` | timeline QA (facts have `evidence_chunks`) empty |
| **WP5** | SRD / `RuleEntity` grounding | `05` | PCs link to shared SRD ids; rules-consistency query runs |
| **WP6** | `Decision` + `RollEvent` extraction | `05` | traceable `Decision → … → Quest` causal chain |
| **WP6b** | `Trait` aggregation + Event-minting filter (do **before** WP7) | `10` | recurring behavior (e.g. music) → one `Trait` with incrementing `count`, not N `Event` nodes; recurrence-vs-significance QA query empty |
| **WP7** | Recall lift (two-pass prompts / optional aikg feed) | `06` | fact count > Graph 3's 27, all QA green, **and** WP6b's recurrence guardrail holds under the higher recall |
| **WP8** | `reconcile-report` gold cross-check | `07` | diffs local vs report; proposes alias additions |
| **WP9** | Multi-session proof + **bitemporal edge lifecycle** (state/event/identity classes, `valid_from`/`valid_to`, death workflow) | `11` | 2nd session: recurring entities MERGE to one id; a contradicting fact closes the old state edge and opens a new one; "as of session N" returns the historical truth; a death closes exactly the state edges, nothing else |
| **WP10** | Regression harness | below | golden-file test; CI fails on dup/off-vocab/missing-provenance |
| **WP11** | Retrieval layer (`retrieve.py` + `cli ask`): entity embeddings via `nomic-embed-text`, Neo4j vector index, as-of graph-neighborhood context for the local LLM | `11` | ownership/history/relationship questions answer correctly with session citations on the two-session corpus; **no** GraphRAG framework adoption (verdict in `11`) |

- **WP9 detail:** ingest a second session and confirm recurring entities `MERGE` to a single id spanning both sessions, cross-session timeline ordering works, and no duplicates appear. Then implement the `11` edge contract: predicate classification (state/event/identity) in `config.py`, close-and-append change workflow, death workflow. This *is* PLAN.md phase 3 for edges; node-property history (`:Fact`) can still follow later.
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
2. ~~**Scene granularity.**~~ Moot — Scene nodes were reverted (`04`); evidence is chunk-index properties only.
3. **SRD source & licensing.** No SRD data ships today. WP5 introduces `data/daggerheart_srd.json`; confirm the source/licensing for full content (a seed subset is fine to start).
4. **Language policy.** Content stays German; vocab/confidence tokens English (per PLAN.md).
5. **Predicate tightening.** Keep the validate-and-map layer (recommended) vs hard-`Literal` on `schema.py:Relationship.predicate` — decide once the vocab is stable.
6. **Neo4j version.** WP11's vector index needs **Neo4j ≥ 5.13** — check/pin the image in `docker-compose.yml`.
7. **LLM size.** Default stays `qwen3:14b` (fits 12 GB alongside `nomic-embed-text`; extraction and embedding run serially anyway). Downshift to Qwen 7–9B only if latency actually hurts, and only after the retry/repair net (`06`) exists — structured-output reliability drops at that size. See `11`.

## Anti-patterns to actively prevent (each seen in one of the three graphs)

- Actor baked into relationship type (`TELLS_VIA_DENIZ`) / predicate sprawl → **Graph 1**. Prevent via closed vocab (`04`).
- Category words as nodes (`character`, `creature`) → **Graph 1**. Prevent via closed types + resolution.
- Name-keyed duplicate entities → **Graph 2** (`store.py` MERGE on name). Fixed by `03`.
- Same name across two types (`Daggerheart` Location+Faction) → **Graph 2**. Caught by QA query 2 (`07`).
- Game resources as Items (`Hope`) → **Graph 2**. Fixed by type rules (`02`/`05`).
- Queryable data hidden in `attributes_json` / relationships hidden as `*_ref` strings → **Graph 3 report loader**. **Do not port to the main pipeline** (invariant 3 in `README.md`).
- Over-pruning away the session's texture → **Graph 3**. Countered by the recall strategy (`06`).

## Expected edges per session (sizing reference)

Measured against the real transcript (`transcripts/2025-03-26_RF_ROCKGeeRUFw.json`, **33.1 real minutes**, 157 segments): running the actual `chunking.load_session` produces **32 raw chunks** at `CHUNK_SIZE=2000`. Projected edge count once WP1–WP8 land, by category:

| Category | Basis | Est. edges/session |
|---|---|---|
| Core content (`MEMBER_OF`,`OWNED_BY`,`LOCATED_IN`,`PARTICIPATED_IN`,…) | Graph 2 today = 232, minus dedup collapse from entity resolution | 180–220 |
| `RollEvent` + edges (`ROLLED`,`TARGETS`,`RESULTED_IN`) | Graph 3 captured 1 roll for the session — under-recall; a real session has more like 10–20 | 30–50 |
| `Decision` + edges (`DECIDED`,`TRIGGERED`) | Graph 3 had 1; realistic recall is a handful per session | 10–15 |
| SRD linking (`HAS_CLASS`,`HAS_ANCESTRY`,`USES_CARD`,`RUNS`,…) | One-time-ish character-sheet facts; heavier in intro sessions, lighter in pure-combat ones | 5–20 (variable) |
| `PLAYS` (player→character, WP1b) | Deterministic: one per player + GM | 4–5 |
| `IN_SESSION` (Event/RollEvent/Decision → Session, no Scene backbone — see `04`) | One per node-fact, direct to Session | 30–40 |

**Total: ~230–300 edges per ~33-min session** — well above Graph 3's 27, below Graph 2's current 232-with-duplicates, and nowhere near Graph 1's 199-predicate sprawl (vocabulary stays closed throughout). Scaled to a 100-hour campaign (~182 sessions this length): **~42,000–55,000 edges** total — clean and well within comfortable Neo4j range. Treat this as a sizing sanity check, not a hard target: WP7's actual acceptance criterion is "exceeds Graph 3's 27 while all QA in `07` stays green," not a specific number.

**Node-side sizing (the backbone question):** most node types (Character, Item, Quest, Trait, …) grow with *narrative activity*; `Session` nodes grow with *elapsed campaign time* regardless of activity, but there's only one per session so this never matters at scale. `Scene` nodes (1 per chunk) were tried and reverted (`04`) precisely because they *did* scale with elapsed time independent of content — projected to ~5,800 nodes over a 100h campaign, a dominant fraction of all nodes for zero unique signal over the `evidence_chunks[]` property. See `10`'s "backbone nodes are a third source of false signal" for why `Session` must still be excluded from any degree-based significance query.

## Target end-state

The local `qwen3` pipeline emits `:Entity{id}` canonical, rules-grounded, fully-provenanced graphs at **higher recall than the hand-authored report** — with the report retained as a gold cross-check, and everything idempotent and versionable per PLAN.md.
