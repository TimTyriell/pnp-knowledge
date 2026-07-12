# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An LLM-to-knowledge-graph pipeline for one TTRPG (Daggerheart) campaign.
`src/pnp_graph/` reads Whisper transcripts, has an LLM fill a **fixed
Pydantic schema** via structured output (NOT free-form SPO triples), then
**resolves** every extracted surface form to a canonical `:Entity{id}`
(alias registry + fuzzy match + SRD gazetteer) before writing to a local
Neo4j with idempotent `MERGE`. Repeated runs and multiple sessions accumulate
into one graph instead of duplicating nodes. A retrieval layer (entity
embeddings + Neo4j vector index) makes the graph queryable via `cli ask`.

**Macro-graph philosophy**: the KG is a macro-structural backbone only
(state, locations, ownership, quest status, scene-level Events) — micro
narrative beats are deliberately NOT captured as topology; the vector store
retrieves that detail from raw transcript text on demand ("graph = table of
contents, vector = the book"). There is no `Trait` node type (quirks live in
`Character.description`, embedded); no `RollEvent` node type (rolls are not
narrative topology — WP14); `Item` nodes are minted **only for named/unique
artifacts** (`is_named_artifact`), generic loot is dropped. The skeleton is the
`:Entity` label; the vector "book" is a **separate `:Chunk` label** with its own
vector index (WP14, the 2026 GraphRAG-standard split) so `MATCH (n:Entity)`
returns a clean skeleton.

**Two extraction profiles**, selected via `PNP_PROFILE` env var
(`config.py`): `local` (default) runs a local Ollama model (`qwen3:14b`),
kept for offline/dev smoke tests — its context window can't hold a
megachunk. `flagship` runs the DeepSeek API with much larger chunks (~11k
tokens, a whole scene per chunk) so the model over-summarizes into 1-2
macro-Events instead of a blow-by-blow; this is the real ingest path.
Embeddings and `cli ask` always run locally regardless of profile.

Built for Windows 11, RTX 4070 Ti (12GB VRAM), 32GB RAM. One 14B model in
VRAM at a time on the local profile — extraction and embedding run serially.

The design spec lives in `docs/evolution/` (WP0–WP14); **it is largely
implemented** — WP0–WP8, WP10, WP11 landed; WP4 Scene nodes were shipped then
reverted; WP12 trait removal + the DeepSeek flagship shift, WP13 single-pass
`SceneExtraction` + semantic scene chunking + chunk-level vector index, and
WP14 (Item = named artifacts only, `RollEvent` removed, the `:Entity`/`:Chunk`
label split) all landed. **Open: WP9** (multi-session proof + bitemporal
`valid_from`/`valid_to` stamping in `store.py`; `STATE_PREDICATES` in
`config.py` and the as-of read path in `retrieve.py` already exist). Measured
results and the Scene-revert rationale: `docs/learnings/MIGRATION_NOTES.md`. The
pre-spec plan is archived at `docs/archive/PLAN.md`. Doc map: `docs/README.md`.

## Commands

```bash
.venv\Scripts\activate
# deps installed ad hoc via uv — no pyproject.toml/requirements.txt at repo root
uv pip install langchain-ollama langchain-openai neo4j pydantic pytest

python -m pnp_graph.cli ingest                        # all sessions in transcripts/, oldest->newest
python -m pnp_graph.cli ingest --only 2025-03-26      # one session by date
python -m pnp_graph.cli ingest --dir path\to\dir      # any dir of *.json transcripts
python -m pnp_graph.cli reconcile-report 2025-03-26   # diff local graph vs hand-authored report graph
python -m pnp_graph.cli ask "Wem gehört der Pott?"    # retrieval + local LLM answer; --as-of N for history
python -m pytest tests/                               # all offline, no LLM/DB needed
python compare/test_sink.py                           # self-check for run_both._write_triples, no Neo4j
python compare/run_both.py --only 2025-03-26          # A/B run vs ai-knowledge-graph (historical harness)
python reports/load_report_graph.py                   # load a report's JSON appendix into :7689

# real ingests use the flagship (DeepSeek) profile — needs DEEPSEEK_API_KEY in .env
PNP_PROFILE=flagship python -m pnp_graph.cli ingest --only 2025-03-26
```

Prereqs that are NOT scriptable and must be up first:
- **`local` profile (default, dev/offline only)**: Ollama running with
  `qwen3:14b` and `nomic-embed-text` pulled (`LLM_MODEL`/`EMBED_MODEL` in
  `config.py`). `extract.py` pins `num_ctx` (`NUM_CTX`, 8192) explicitly —
  Ollama's silent VRAM-based auto-default (4096) previously caused runaway
  generation loops that never converged. `nomic-embed-text` is needed
  regardless of profile — embeddings always run locally.
- **`flagship` profile (real ingests)**: `DEEPSEEK_API_KEY` set in `.env`
  (gitignored, loaded via the VS Code launch configs' `envFile`, or export it
  yourself). No local model load for extraction, but Ollama + `nomic-embed-text`
  are still needed for the embedding step.
- **Neo4j** via `docker compose up -d` — three containers, all
  `NEO4J_AUTH=none` (no password, `auth=None` in every driver call):
  `neo4j-main` on `bolt://localhost:7687` (this pipeline, "Graph 2"),
  `neo4j-aikg` on `:7688` (the `compare/` harness sink, "Graph 1"),
  `neo4j-report` on `:7689` (the hand-authored report graph, loaded by
  `reports/load_report_graph.py`, "Graph 3"). `store.connect()` calls
  `verify_connectivity()` so this fails fast instead of hanging in extraction.
  The WP11 vector index needs Neo4j ≥ 5.13 (see `docker-compose.yml`).

Inspect a run in Neo4j Browser (http://localhost:7474):
`MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100`

## Architecture (`src/pnp_graph/`)

Pipeline per session, orchestrated by `ingest()` in `ingest.py`:
`ordered_sessions → read_segments (raw) → scene_chunks (flagship: semantic
scenes via segment_session) or pack_segments (local: char-budget chunks) →
extract_session (one structured-output call per chunk + in-mem merge) →
resolve_graph (canonical IDs + Chunk passages for the vector store) →
write_session (Neo4j MERGE) → embed_entities (vector index, incl. Chunk
raw-text embeddings)`.

- **`config.py`** — every tunable: models, chunk size, Neo4j URL, and the
  **closed vocabularies**. Two extraction profiles selected by `PNP_PROFILE`
  (`local`/`flagship`, default `local`) resolve `PROVIDER`, `LLM_MODEL`,
  `CHUNK_SIZE`, `CHUNK_OVERLAP` — `local` keeps the original 4000 chars / 600
  overlap (raised from 2000 after the S01 quality analysis traced micro-event
  inflation to small chunks); `flagship` (DeepSeek) uses ~44000 chars / 3000
  overlap (megachunks, one whole scene per chunk). `NUM_CTX`/`REPEAT_PENALTY`/
  `NUM_PREDICT` are Ollama-only; `DEEPSEEK_BASE_URL`/`DEEPSEEK_API_KEY`/
  `FLAGSHIP_MAX_TOKENS` are DeepSeek-only. Also the
  `ALLOWED_PREDICATES` + `PREDICATE_SYNONYMS` (off-vocab → `RELATES_TO`,
  logged), `PREDICATE_DOMAINS` (domain/range per predicate),
  `STATE_/EVENT_/IDENTITY_PREDICATES` (bitemporal classes, WP9),
  `META_EVENT_TERMS` (event gate), `RULE_SUBTYPES`, `OOC_DENYLIST`
  (out-of-fiction noise like Twitch raids). No tunables live elsewhere.
- **`chunking.py`** — input is Whisper JSON (`segments` of
  `{start, end, speaker, text}`); `.txt` siblings in `transcripts/` are
  reference only. `session_id_from_path` extracts the date (`2025-03-26`)
  used as `session_id` everywhere downstream, matching pnp-report's
  `Session_Report_S<NN>_<date>` convention. `pack_segments` packs whole
  speaker turns up to `CHUNK_SIZE`, preferring to cut at the **largest silence
  gap** within budget; overlap is turn-based; empty segments filtered.
  `parse_speaker`/`session_cast` split the transcript's `Player (Character)`
  labels — the cast drives player/character mapping and GM handling downstream.
- **`schema.py`** — the extraction contract, forced via structured output
  (`method="json_schema"` on Ollama, `"function_calling"` on DeepSeek — the
  latter's OpenAI-compatible endpoint doesn't support strict json_schema
  reliably): `SceneExtraction` (docs/evolution/13, WP13.6) is ONE combined
  schema covering Character / Location / Item / Quest / Faction / RuleEntity
  / Decision / Relationship plus the single capsule
  `macro_scene_event: Event` (WP13.2 — one macro event per scene chunk, with
  a required `narrative_significance_reasoning`, "pay to mint"). `Item` carries
  a required `is_named_artifact` — same "pay to mint" gate, generic loot is
  dropped in resolve.py; there is no `RollEvent` type (WP14). Supersedes
  the old two-pass `EntityExtraction`+`EventExtraction` split (that split
  existed to keep a 14B reliable on a smaller schema per call) and the N3
  `EventConsolidation` pass (impossible to need once it's one event/scene).
  Also `SceneBoundary`/`SceneSegmentation` (WP13.1, the scene-segmentation
  pre-pass output). No `Trait` node type (macro-graph philosophy — quirks
  live in `Character.description`). To change what's extracted, edit these
  models — there's no separate prompt-only knob.
- **`extract.py`** — one structured-output call per chunk (`extract_chunk`,
  WP13.6) with retry (`_invoke_with_retry`; persistent parse failures dump to
  `state/failures/<sid>/`). Cast + SRD gazetteer lines are injected into the
  prompt. `evidence` (chunk index) is set in code, never by the model.
  `merge_graphs` dedups by name/label in-memory (first occurrence wins per
  session). `segment_session`/`build_segmenter` (WP13.1) is the separate
  scene-boundary pre-pass, flagship-only. `SUGGESTED_PREDICATES` (sourced
  from the Claude-authored S02 report) biases relation naming; the hard
  vocab enforcement happens later in `resolve.py`.
- **`resolve.py`** — **the identity layer** (WP1/WP1b, the spec's gate).
  `Resolver` maps surface forms → canonical ids via `data/alias_registry.json`
  + normalization + `difflib` fuzzy match (ratio ≥ 0.9; stdlib, no
  rapidfuzz/APOC). `resolve_graph` builds the final `{entities, edges}` dict:
  player/character split with per-session `PLAYS` (GM gets only `DIRECTS`),
  out-of-world filter (`OOC_DENYLIST`), event gate (`META_EVENT_TERMS` +
  roll-shaped titles), predicate mapping + domain checks, endpoint
  validation — unresolvable edges are
  **dropped and logged** (`state/failures/<sid>/dropped_edges.jsonl`), never
  MERGE-created. With `chunk_texts` (WP13.5, docs/evolution/13), also splits
  each chunk into passages (`chunking.split_passages`) and mints them as
  `Chunk` nodes (the `:Chunk` label, WP14) linked `IN_SESSION` + `MENTIONS` to
  every entity whose `evidence_chunks` name that scene — the "vector = das Buch"
  half.
- **`store.py`** — idempotent Neo4j writes: skeleton nodes MERGE on
  `:Entity {id}` (constraint `entity_id`; `type`/`session_id` indexes), `Chunk`
  passages MERGE on a separate `:Chunk {id}` label (constraint `chunk_id`,
  WP14). Edge endpoints MATCH label-less (`(a {id})`) so a `MENTIONS`/
  `IN_SESSION` edge joins a `:Chunk` start to an `:Entity` end.
  `sanitize_predicate` strips predicates to `[A-Z0-9_]` — relationship types
  can't be parameterized, this is the injection guard; keep it if you touch that
  code. `write_session` = constraints + `_write_graph` via `execute_write` in
  one driver session (per-session atomic write). `_write_graph` splits entity
  props into `create_props` (all values) vs `match_props` (drops empty
  string/list) so a cross-session re-mention with nothing new never blanks
  out a value a prior session set (e.g. `Character.description`). `run_qa` =
  the QA queries from `docs/evolution/07` (dup names, cross-type collisions,
  missing provenance, orphan events). No `valid_from`/`valid_to` stamping
  yet — that's WP9.
- **`srd.py`** — loads `data/daggerheart_srd.json` into an `SrdIndex`
  (prompt gazetteer + shared `RuleEntity` library); `preload` MERGEs the
  shared SRD nodes once, sessions link to them, never per-session copies.
- **`embed.py`** — `nomic-embed-text` embeddings (768 dims), always local
  regardless of `PNP_PROFILE`. **Two vector indexes** (WP14): `entity_embedding`
  `FOR (:Entity)` and `chunk_embedding` `FOR (:Chunk)`; the embed pass matches
  `(n:Entity OR n:Chunk)`. Backbone types (Session) excluded from search hits.
  `Chunk` nodes (WP13.5) are the one exception to the composed
  `type|name|aliases|description|summary` text — their raw passage `text` is
  embedded verbatim.
- **`retrieve.py`** — GraphRAG-style **local** search without adopting the
  framework (verdict in `docs/evolution/11`): vector top-k seeds merged from
  **both** indexes by cosine score (WP14) → graph neighborhood expansion over
  both labels (optionally as-of a session seq) → formatted context → local LLM
  answer with session citations. `cli ask` wraps it. A `Chunk` seed renders as
  its raw source passage instead of the usual name/status line.
- **`reconcile.py`** — `cli reconcile-report` (WP8): diffs the local graph
  against the hand-authored report graph for one session; proposes alias
  additions. Finds reports in `reports/` (or repo root).
- **`ingest.py`** — per-session orchestration, one `try/except` per session so
  one failure doesn't block the rest; append-only `state/ingest_log.jsonl`.
  **No file-hash resume-skip yet** — every run reprocesses every session
  (open item from archived PLAN phase 2, as are per-session `:Summary` nodes).

## Tests

`python -m pytest tests/` — all offline, no LLM/DB:
- `test_chunking.py` — `pack_segments` invariants.
- `test_extract.py` — prompt assembly, merge, event-consolidation logic (LLM stubbed).
- `test_resolve.py` — the resolver: aliasing, GM handling, out-of-world filter,
  event gate, predicate mapping.
- `test_golden.py` — golden-file regression (WP10): fixed extraction fixture
  through resolve, compared against `tests/golden_resolved.json`.
- `test_retrieve.py` — embedding text + context formatting.

`tests/manual_test_files/` holds manual Neo4j inspection snapshots, not pytest
fixtures. End-to-end verification is still: run an ingest, check the logged
per-chunk counts, `state/ingest_log.jsonl`, and the `run_qa` output.

## `compare/` — historical A/B harness

`compare/run_both.py` ran each session through this pipeline AND the vendored
free-form-triple `ai-knowledge-graph` project (sibling repo at
`c:\dev\pnp\ai-knowledge-graph`, override with `AIKG_DIR`; config
`compare/aikg_qwen.toml`, same model + matched chunk size) into `:7687` /
`:7688` for side-by-side comparison on identical input. That comparison
**decided the architecture** (three-graph table in `docs/evolution/README.md`);
the harness stays runnable for spot-checks but is not part of ingest. Runs
serially — one 14B fits in VRAM. `compare/out/` is generated and gitignored.

## `reports/` — Graph 3, the hand-authored gold cross-check

`reports/` holds the curated `Session_Report_*.md` files (German, each ending
in a fenced ` ```json ` graph appendix authored by Claude, not qwen) and
`load_report_graph.py`, which MERGEs that appendix into `:7689` as generic
`:Entity{id}` nodes — no LLM, no chunking. Used as the gold reference by
`cli reconcile-report`; the main pipeline never touches `:7689` during ingest.
`Session_Report_S02_2025-04-01.md` is also the source of
`SUGGESTED_PREDICATES` in `config.py`. `reports/test_load_report_graph.py`
covers the loader.

## Data & state

- `data/alias_registry.json` — persistent surface→canonical-id map; grows via
  resolver runs and `reconcile-report` proposals. Checked in.
- `data/daggerheart_srd.json` — seed SRD subset (licensing for full content
  unconfirmed; candidate bulk source: `c:\dev\pnp\daggerheart-data`).
- `state/` — gitignored: `ingest_log.jsonl` (append-only run log),
  `failures/<sid>/` (LLM parse failures, dropped edges).

## Conventions

- Content (names, descriptions) stays **German**; predicates, types, and
  confidence tokens are English (`CONFIDENCE_MAP` converges `hoch`→`high`).
- Canonical `id` is the merge key — never `name`. Resolution happens before
  the write; endpoints are MATCHed by id, dropped if unresolved.
- Extract generously, resolve deterministically — recall is a prompt dial,
  correctness lives in `resolve.py`.
- `ai-knowledge-graph/` (sibling folder) is third-party reference — don't edit
  it or confuse its free-form-triple design for this repo's.
