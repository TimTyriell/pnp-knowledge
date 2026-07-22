# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## What this repo is

`pnp-knowledge` (formerly `pnp-graph-service`) is the **"memory" repo** of the
campaign toolchain: `pnp-crawl` (input/transcription) → **this repo**
(knowledge) → `pnp-export-data` (output/wiki). It owns *what the campaign world
currently is*. See [README.md](README.md) for the layout and
[docs/architecture/](docs/architecture/) for the decisions
([ADR-001](docs/architecture/ADR-001-knowledge-layer.md): OKF-in-git is the
system of record; [ADR-002](docs/architecture/ADR-002-repo-layout.md): this
layout + the rename).

Two systems live here, and the top level keeps them apart:

**Active — the OKF knowledge base:**
- **`knowledge/`** — ★ the **system of record**: the OKF campaign bundle
  (`bundle/splitter_des_ewigen/`), `entity_registry.yaml`, `conflicts/`,
  `sources/`. Knowledge edits arrive via `ingest/s<NN>` branches that touch
  only `knowledge/`, reviewed as PRs, tagged `s<NN>` per session on merge.
  Knowledge diffs are path-scoped: `git diff <ref>.. -- knowledge/`.
- **`services/kb/`** — the KB service: the `pnp_okf` OKF-distillation pipeline
  (transcripts → bundle, DeepSeek) plus the read-only HTTP API
  (`python -m pnp_okf.api`, 127.0.0.1:8070). Own `pyproject.toml`, own venv.
- **`services/summary/`** — pre-session recap + ephemeral outlook CLI, grounded
  in the KB API.
- **`reports/`** — all session reports (`Session_Report_*.md`) + `rolls/` CSVs.
  Shared campaign data (also read by the frozen graph's loaders).
- **`docs/architecture/`** — ADR-001, ADR-002, ARCHITECTURE (system-level).

**Frozen — the GraphRAG pipeline:**
- **`graph/`** — ❄ the original Neo4j knowledge-graph pipeline that gave the repo
  its old name. **Frozen**: reference + a possible future *derived index*
  rebuilt from the bundle (ADR-001 revisit triggers), no active feature work.
  Self-contained (`src/pnp_graph`, `data/`, `tests/`, `compare/`, `docs/`,
  `docker-compose.yml`, …). **When working inside `graph/`, read
  [graph/CLAUDE.md](graph/CLAUDE.md)** — it has the full pipeline architecture,
  with all paths relative to `graph/`.

## Working here

- The wiki agent is **not** in this repo — it's the separate `pnp-export-data`
  repo, a pure client of the KB API. Don't re-add wiki code here.
- Each active service has its own venv. The repo-root `.venv` belongs to the
  frozen `graph/` pipeline.
- Before touching `services/*` or `knowledge/`, read the architecture docs.
  Before touching `graph/`, read `graph/CLAUDE.md`.
- Known issue (pre-existing, out of scope for the layout move):
  `graph/tests/test_golden.py` is red — its golden file is stale relative to the
  merged alias/role changes in `750d6f1`. Regenerate with
  `python graph/tests/test_golden.py --update` only after confirming the drift
  is intended.
