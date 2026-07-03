# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local LLM-to-knowledge-graph pipeline for one TTRPG (Daggerheart) campaign.
`src/pnp_graph/` reads Whisper transcripts, has a local Ollama model fill a
**fixed Pydantic schema** via structured output (NOT free-form SPO triples / NOT
LangChain's `LLMGraphTransformer`), merges entities by name in-memory per session,
then writes to a local Neo4j with idempotent `MERGE` so repeated runs and multiple
sessions accumulate into one graph instead of duplicating nodes.

Standalone — not part of the `c:\dev\pnp` multi-repo workspace, not a git repo.
Built for Windows 11, RTX 4070 Ti (12GB VRAM), 32GB RAM.

Per `PLAN.md`, this is mid-refactor: phase 1 (split into `src/pnp_graph/` modules,
behavior-preserving) is done. Phases 2-5 (resume/state, `:Fact` versioning,
per-session summaries, retry/repair safety nets) are designed in `PLAN.md` but not
yet implemented — `ingest.py`/`store.py` currently do plain overwrite `MERGE`, no
versioning, no resume skip beyond append-only `ingest_log.jsonl`.

`docs/evolution/` is a newer, larger spec that rides on top of `PLAN.md` (doesn't
replace it) — read `docs/evolution/README.md` first, then only the one doc for the
work package at hand. Its core thesis: this pipeline's `store.py` currently `MERGE`s
on `name` (duplicate-prone), while `reports/load_report_graph.py` (a **separate,
non-LLM** loader for the hand-authored `Session_Report_*.md` graphs) uses canonical
`:Entity{id}`. `docs/evolution/08_roadmap.md` lists WP0–WP10 in order; **WP1
(canonical IDs + `resolve.py`) is the gate** — it's also a hard prerequisite for
`PLAN.md`'s phase-3 `:Fact` versioning, so do WP1 before that phase.

## Commands

```bash
.venv\Scripts\activate
# deps installed ad hoc — no pyproject.toml/requirements.txt at repo root
uv pip install langchain-ollama neo4j pydantic
python -m pnp_graph.cli ingest                       # all sessions in transcripts/, oldest->newest
python -m pnp_graph.cli ingest --only 2025-04-01      # one session by date
python -m pnp_graph.cli ingest --dir path\to\dir      # any dir of *.json transcripts
python -m pytest tests/                               # or: python tests/test_chunking.py
python compare/test_sink.py                           # self-check for run_both._write_triples, no Neo4j needed
python compare/run_both.py --only 2025-03-26           # A/B run vs ai-knowledge-graph, see compare/ below
```

Prereqs that are NOT scriptable and must be up first:
- **Ollama** running with `qwen3:14b` pulled (`LLM_MODEL` in `config.py`; fall back
  to `qwen3:8b` on VRAM trouble). `extract.py` pins `num_ctx` (`NUM_CTX` in
  `config.py`, 8192) explicitly — Ollama's silent VRAM-based auto-default (4096)
  previously caused runaway generation loops that never converged.
- **Neo4j** via `docker compose up -d` (see `docker-compose.yml`) — three containers,
  all `NEO4J_AUTH=none` (no password, `auth=None` in every driver call): `neo4j-main`
  on `bolt://localhost:7687` (this pipeline, "Graph 2"), `neo4j-aikg` on `:7688` (the
  `compare/` A/B harness sink, "Graph 1"), `neo4j-report` on `:7689` (the
  hand-authored report graph, loaded separately by `reports/load_report_graph.py`,
  "Graph 3" — see `docs/evolution/README.md`). `store.connect()` calls
  `verify_connectivity()` so this fails fast with a clear error instead of hanging
  in extraction first.

Only test coverage is `tests/test_chunking.py` (pure invariants on `pack_segments`,
no LLM/DB needed). Everything past chunking is unverified except by running it —
the "is it working" check is the per-chunk entity counts logged during a run, the
`state/ingest_log.jsonl` record, and the starter Cypher query printed at the end.

## Architecture (`src/pnp_graph/`, package, see `PLAN.md` for full design)

Pipeline is `ordered_sessions → load_session_chunks → extract_session (per-chunk
LLM + merge) → write_session`, orchestrated per-session by `ingest()` in `ingest.py`.

- **`config.py`** — every tunable (model name, chunk size/overlap, Neo4j URL,
  `SUGGESTED_PREDICATES`, paths). No tunables live elsewhere.
- **`chunking.py`** — input is JSON, not `.txt`. Each transcript JSON has a
  `segments` list of `{start, end, speaker, text}` (Whisper output); `.txt`
  siblings in `transcripts/` are ignored/reference only. `session_id_from_path`
  extracts the date from the filename (e.g. `2025-03-26`) — this is the
  `session_id` used everywhere downstream, matching pnp-report's
  `Session_Report_S<NN>_<date>` convention. `pack_segments` is segment-aware, not
  char-aware: packs whole speaker turns up to `CHUNK_SIZE`, preferring to cut at
  the **largest silence gap** (`segments[end+1].start - segments[end].end`) within
  budget over a raw char boundary — overlap is also turn-based. Empty/whitespace
  segments are filtered before chunking.
- **`schema.py`** — `GraphExtraction` (characters / locations / items / quests /
  events / factions / relationships) is the contract.
  `with_structured_output(..., method="json_schema")` in `extract.py` forces the
  model to fill it. To change what's extracted, edit these Pydantic models —
  there's no separate prompt-only knob.
- **`extract.py`** — one LLM call per chunk (`extract_chunk`), `evidence` (chunk
  index) is set in code, never by the model. Relationships are open-vocabulary but
  seeded: `SUGGESTED_PREDICATES` (in `config.py`, sourced from a prior
  Claude-authored S02 session report) biases the model toward reusing relation
  types; it's a hint, not an enum. `merge_graphs` dedups by name/title in-memory
  before any DB write — first occurrence wins per session, later duplicate-named
  entities within that session are dropped (not merged field-by-field).
  Relationships dedup on `(subject, predicate, object)`. `extract_session` runs
  this across every chunk of one session.
- **`ingest.py`** — orchestrator. Iterates `ordered_sessions` (oldest → newest by
  date, so the graph builds in story order), one `try/except` per session so one
  failed session doesn't block the rest; failures are logged to
  `state/ingest_log.jsonl` with `status: "failed"` and continue, not yet to
  `state/failures/<id>/` with raw LLM output (planned, phase 5). No file-hash
  resume-skip yet despite the log existing — every `ingest` run currently
  reprocesses every session.
- **`store.py`** — Neo4j write is idempotent: uniqueness constraints on
  Character/Location/Faction name, everything is `MERGE`. Events store
  `name = title` so the generic relationship writer can `MATCH (a {name:...})`
  across every node type. `sanitize_predicate` strips a predicate to `[A-Z0-9_]`
  so it's safe to interpolate as a Cypher relationship type — relationship types
  can't be parameterized, so this is the injection guard; keep it if you touch
  that code. `write_session` runs `ensure_constraints` + `_write_graph` via
  `execute_write` (managed transactions) in one driver session — `_write_graph` is
  the per-session atomic write `PLAN.md` calls for. No versioning yet — repeated
  runs overwrite scalar properties (`SET`) rather than appending `:Fact` history.

Inspect a run in Neo4j Browser (http://localhost:7474):
`MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100`

## `compare/` — A/B harness against `ai-knowledge-graph`

`compare/run_both.py` runs each session through **both** extraction approaches
side by side, into two separate local Neo4j DBMS, to compare this repo's typed-
schema approach against the vendored free-form-triple `ai-knowledge-graph`
project on identical input:

- this repo's pipeline (`pnp_graph.cli ingest --only <session>`) → `:7687`, unchanged.
- `ai-knowledge-graph/generate-graph.py` (sibling repo, config at
  `compare/aikg_qwen.toml`, same `qwen3:14b` model and matched chunk size so the
  comparison isolates approach, not model) → triples JSON → `_write_triples`
  MERGEs those into a second DBMS on `:7688` (generic `:Entity` nodes, reusing
  this repo's `sanitize_predicate` as the injection guard).
- Runs **serially**, never both LLM jobs at once — single 12GB-VRAM GPU can't
  host two `qwen3:14b` concurrently. "A/B" here means side-by-side output
  comparison, not concurrent execution.
- `compare/test_sink.py` is a standalone self-check (no pytest, no Neo4j) for
  `_write_triples`'s malformed-triple filtering and predicate sanitization.

## `reports/` — Graph 3, the hand-authored gold cross-check

`reports/load_report_graph.py` is a **third, separate loader** — no LLM, no
chunking. It pulls the trailing fenced ` ```json ` appendix out of a
`Session_Report_*.md` (already a curated graph written by Claude, not qwen) and
`MERGE`s it into `:7689` as generic `:Entity{id}` nodes (closed canonical ID, not
`name`-keyed like `store.py`). It reuses `pnp_graph.chunking.session_id_from_path`
and `pnp_graph.store.sanitize_predicate` from the main package but is otherwise
independent. This is Graph 3 in `docs/evolution/`'s three-graph comparison — kept
as a quality reference, not something the main pipeline writes to or reads from at
runtime. `reports/test_load_report_graph.py` covers it.

## Not the pipeline

- The pre-refactor monolith `extract_to_graph.py` is **deleted** — `src/pnp_graph/`
  fully replaces it. If you see references to it, they're stale.
- `ai-knowledge-graph/` moved out to its own top-level sibling folder
  (`c:\dev\pnp\ai-knowledge-graph`) — third-party reference project (its own
  `pyproject.toml`, `generate-graph.py`, free-form-triple approach). Don't edit it
  or confuse its design for this repo's. `compare/run_both.py` locates it via
  `REPO_ROOT.parent / "ai-knowledge-graph"` (override with `AIKG_DIR` env var).
- `quick_test/` and `Session_Report_S02_2025-04-01.md` are reference/scratch, not
  part of the pipeline.
