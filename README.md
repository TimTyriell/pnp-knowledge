# pnp-knowledge

The **"memory" repo** of the campaign toolchain (input → memory → output):
`pnp-crawl` (transcription) → **this repo** (knowledge) → `pnp-export-data`
(wiki). It owns *what the campaign world currently is* and serves it to the
other services.

> Repo formerly named `pnp-graph-service`. The GraphRAG pipeline that named it
> is now frozen legacy (see [`graph/`](graph/)); the active system is the OKF
> knowledge base under [`services/`](services/) + [`knowledge/`](knowledge/).
> See [ADR-001](docs/architecture/ADR-001-knowledge-layer.md) for why OKF-in-git
> is the system of record and [ADR-002](docs/architecture/ADR-002-repo-layout.md)
> for this layout.

## Layout

```
├── knowledge/            ★ SYSTEM OF RECORD — the OKF campaign bundle
│   ├── bundle/splitter_des_ewigen/   one markdown concept per entity
│   ├── conflicts/                    open cross-source contradictions
│   └── sources/                      campaign book + ingested custom docs
│
├── services/             ACTIVE code (each its own venv)
│   ├── kb/               OKF pipeline (transcripts → bundle) + read-only API
│   └── summary/          pre-session recap / outlook, grounded in the KB API
│
├── reports/              session reports (.md) + rolls/ CSVs — shared data
│
├── docs/architecture/    ADR-001, ADR-002, ARCHITECTURE (system-level)
│
└── graph/                ❄ FROZEN GraphRAG (Neo4j) — reference + future
                            derived index only, no active development
```

**Active vs frozen at a glance:** `knowledge/` + `services/` are live; `graph/`
is frozen. Nothing in `graph/` is on the critical path — see its
[README](graph/README.md).

## Quick start

```bash
# KB read API (serves the bundle to the wiki + summary services)
cd services/kb && python -m pnp_okf.api      # 127.0.0.1:8070

# Pre-session recap
cd services/summary && python summary.py

# Rebuild the bundle from transcripts (DeepSeek; see services/kb/README.md)
cd services/kb && pnp run --transcripts <dir> --bundle ../../knowledge/bundle/splitter_des_ewigen
```

Tests: `services/kb` and `services/summary` each `python -m pytest`; the frozen
graph is `cd graph && PYTHONPATH=src python -m pytest tests`.
