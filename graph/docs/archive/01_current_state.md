# 01 — Current State & Defects (as-is)

Read alongside the code in `src/pnp_graph/`. This is the *why* behind the whole evolution.

Pipeline: `ordered_sessions → load_session_chunks → extract_session (per-chunk LLM + in-mem merge) → write_session`, orchestrated per-session by `ingest()`.

## File-by-file

- **`config.py`** — `qwen3:14b`, `CHUNK_SIZE=2000`, `CHUNK_OVERLAP=200`, `NUM_CTX=8192` (pinned for a reason — see its comment), Neo4j `:7687` no-auth. `SUGGESTED_PREDICATES` is a *hint*, not enforced. Hardware ceiling: one 14B in 12 GB VRAM at a time.
- **`schema.py`** — `GraphExtraction` = Character / Location / Item / Quest / Event / Faction / Relationship. `Character` already has `player` + `aliases` **but nothing uses them for resolution.** `Relationship.predicate` is free-form UPPER_SNAKE. `confidence` (Literal) + `evidence` (chunk index) exist on relationships **only**.
- **`chunking.py`** — solid gap-aware segment packing from Whisper JSON. Keep the packing logic, but note `format_turn` prints the **raw** `speaker` label `Tim (Lindo Laut):` into the chunk — the transcript encodes both player and character as `Player (Character)`, and passing that composite string to the LLM is a direct cause of the `Tim` / `Lindo Laut` / `Tim (Lindo Laut)` triplication. `format_turn` will be changed to emit the parsed character (see `09`). Scene segmentation also hooks in here.
- **`extract.py`** — one LLM call per chunk; `merge_graphs` dedups **by exact `name`/`title` string** within a session (first occurrence wins). No cross-surface-form resolution.
- **`ingest.py`** — per-session orchestration, per-session `try/except`, append-only `ingest_log.jsonl`. No file-hash resume yet (every run reprocesses everything).
- **`store.py`** — the defect epicenter (details below).
- **`reports/load_report_graph.py`** — already implements the *target* `:Entity{id}` shape with an `entity_id` uniqueness constraint, but pushes everything else into `attributes_json` (opaque). Reuse the id/MERGE pattern; **do not** reuse `attributes_json`.

## The four structural defects

1. **Name-keyed identity → duplicate entities.** `store.py` does `MERGE (c:Character {name:$name})` (and the same for Location/Faction/Item/Quest/Event), with constraints `REQUIRE c.name IS UNIQUE`. Because the model emits `Marco`, `Dodo`, `Marco (Dodo)` across chunks, they fork into three nodes. The constraints enforce the **wrong key**. → Fixed in `03_entity_resolution.md`.

2. **Name-based endpoint matching → type collisions + phantom nodes.** The relationship writer uses `MATCH (a {name:$subject})`, matching **any label** by name → the "`Daggerheart` is both `:Location` and `:Faction`" collision, and it can silently MERGE-create empty endpoint nodes when the endpoint wasn't extracted (PLAN.md safety-net #5 is designed, not implemented). → Fixed in `03` + `04`.

3. **Open relationship vocabulary.** `sanitize_predicate` guards Cypher injection but permits any predicate. At scale this is how you get Graph 1's 199 types. → Fixed by the closed vocab in `04_scenes_provenance_vocab.md`.

4. **No provenance on nodes, and no scene/rules/decision/roll semantics.** Only relationships carry `confidence`/`evidence_chunk`/`session_id`; nodes carry none. There is no `Scene`, `RuleEntity`, `Decision`, or `RollEvent`. → Added in `04`, `05`.

## What's already good (keep it)

Typed extraction via structured output (not free-form triples), idempotent `MERGE`, per-session atomic-ish writes, gap-aware chunking, provenance on edges, oldest→newest ingest order, and a clean module split. The evolution is additive/surgical, not a rewrite.
