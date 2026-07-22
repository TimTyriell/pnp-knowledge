# graph/ — ❄ FROZEN GraphRAG pipeline

This is the original Neo4j-based knowledge-graph pipeline that gave the repo
its old name (`pnp-graph-service`). It is **frozen**: kept as reference and as
the implementation of a possible future *derived index*, but it is **not** the
system of record and receives no active feature work.

Per [ADR-001](../docs/architecture/ADR-001-knowledge-layer.md), the campaign's
knowledge lives in the OKF bundle under [`../knowledge/`](../knowledge/), served
by [`../services/kb`](../services/kb). This graph would only be revived — rebuilt
*from* that bundle — if the ADR's revisit triggers fire (relationship-discovery
queries that link-walking + grep can't answer).

Everything the pipeline needs is self-contained here:

```
graph/
├── src/pnp_graph/     the pipeline (chunking → extract → resolve → store → retrieve)
├── data/              alias_registry.json, daggerheart_srd.json
├── tests/             offline pytest suite (no LLM/DB needed)
├── compare/           historical A/B harness vs ai-knowledge-graph
├── docs/              evolution/ (spec), learnings/, archive/, audit_*.md
├── transcripts/       Whisper JSON inputs (gitignored)
├── state/             ingest log + failures (gitignored)
├── export_graph.py    Neo4j → JSON export
├── load_report_graph.py   load a report's JSON appendix into :7689
└── docker-compose.yml three no-auth Neo4j containers
```

Run (needs the venv at the repo root and Neo4j up via `docker compose up -d`):

```bash
cd graph
PYTHONPATH=src python -m pnp_graph.cli ingest --only 2025-03-26
PYTHONPATH=src python -m pytest tests
```

Report data (`Session_Report_*.md`) lives in the shared top-level
[`../reports/`](../reports/), not here — the loaders reach up one level for it.

See [../CLAUDE.md](../CLAUDE.md) and the in-package docstrings for the full
architecture; the design spec is in [docs/evolution/](docs/evolution/).
