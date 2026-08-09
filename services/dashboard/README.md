# pnp-dashboard

Status dashboard over the three-repo toolchain (`pnp-crawl` → `pnp-kb` →
`pnp-export-data`) — never writes to any of those three source repos, see
`../../docs/architecture/status-schema.md` for the data contract.

The **Glossar** tab is the one exception, and it writes only inside *this*
repo: it lists every KB entity with its aliases and their literal occurrence
count across the transcripts, lets you rename an entity or add/remove
aliases, and a Sync button patches `knowledge/entity_rules.yaml` with the
change (comment-preserving line patch, not a full YAML rewrite). It never
touches `knowledge/bundle/` or `entity_registry.yaml` — those stay owned by
the `pnp_okf` pipeline — and it never runs the pipeline; after a sync the tab
just shows a "Bundle veraltet" hint until you run `pnp run` yourself in
`services/kb`. The write endpoint (`POST /api/glossary/edits`) is
loopback-only and validates the patched YAML before writing anything.

## Run

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"

# backend, :8090
.venv/Scripts/python app.py

# frontend dev server, :5173, proxies /api -> :8090
cd web && npm install && npm run dev
```

For a single-process deployment, build the frontend once and let FastAPI
serve it:

```bash
cd web && npm run build   # writes web/dist
cd .. && .venv/Scripts/python app.py   # now also serves / from web/dist
```

## Config (env vars)

- `PNP_CRAWL_DIR` — path to the pnp-crawl repo (default: sibling `../pnp-crawl`);
  the Glossar tab also reads transcripts from `$PNP_CRAWL_DIR/transcripts_final`
- `PNP_EXPORT_DIR` — path to the pnp-export-data repo (default: sibling `../pnp-export-data`)
- `PNP_KB_URL` — KB API base URL (default: `http://127.0.0.1:8070`)
- `PNP_KNOWLEDGE_DIR` — path to this repo's `knowledge/` dir (default:
  `../../knowledge`, i.e. the real one); the Glossar tab reads
  `entity_registry.yaml`/`entity_rules.yaml` from here and writes
  `entity_rules.yaml` here on sync

## Prerequisites for real data

- `pnp-crawl`: run `python pipeline_status.py --json` (or `run_pipeline.py`,
  which now calls it automatically) to produce `status/status.json`.
- `pnp-kb`: `python -m pnp_okf.api` serves `/status` live; `pnp run` writes
  `state/last_run.json` after each pipeline run.
- `pnp-export-data`: run `python 05_report.py` to produce `status/status.json`.

## Tests

```bash
.venv/Scripts/python -m pytest test_merge.py test_glossary.py test_rules_edit.py
```
