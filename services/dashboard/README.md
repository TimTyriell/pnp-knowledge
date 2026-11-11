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

The Folgen tab also exposes a second write path: it can freeze a season into
`knowledge/frozen/` and start the fixed `pnp run` or `pnp state` command after
an estimate and explicit confirmation. These endpoints are loopback-only.

## Run

### Local campaign workbench (Windows)

For normal use, run `Start-Workbench.ps1` from the repository root. It opens
the built app in your browser and keeps the Python server in a hidden window.
Use `-NoBrowser` to start or reuse the server without opening a browser. The
server listens only on this computer at `http://127.0.0.1:8090`.

Prepare the app once from PowerShell if the launcher says setup is needed:

```powershell
Set-Location services/dashboard
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -e ../kb -e ".[dev]"
Set-Location web
npm.cmd ci
npm.cmd run build
Set-Location ../../..
./Start-Workbench.ps1
```

This uses the dashboard's own Python environment and the local `services/kb`
package. Node is needed for the one-time frontend install and build; the running
app does not need a Node server. The launcher checks for a working dashboard
`.venv` first and then the workspace-local `.tools/workbench-venv` environment.
It does not install dependencies. If neither environment is ready, follow the
setup commands above. Existing provider environment variables are inherited;
the launcher does not display them or start AI processing.

Campaign workspaces are saved under `services/dashboard/data/workspaces` by
default. Set `PNP_WORKSPACE_DIR` before launch to store them elsewhere. This is
an isolated local authoring area: it does not migrate or modify the live
`knowledge/` campaign. Workspaces retain Markdown revisions and can be exported
as ZIP bundles with source metadata; use the existing private-repository review
and session-tag process when handing accepted knowledge to the canonical
campaign bundle.

### AI source review

AI source review is optional and requires provider configuration in the
PowerShell environment before starting the app. Set `DEEPSEEK_API_KEY` in that
environment through your normal secret manager or private local environment
setup; never put it in the browser, repository, or a committed file. The app
sends source text to the configured provider only after you explicitly choose
to process that source. The provider may charge for processing, and the app
does not show a cost estimate. Manual authoring remains available without
provider configuration.

The setup below remains available for dashboard development and its existing
technical status and glossary views.

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -e ../kb -e ".[dev]"

# backend, :8090
.venv/Scripts/python app.py

# frontend dev server, :5173, proxies /api -> :8090
cd web && npm install && npm run dev
```

For a single-process deployment, build the frontend once and let FastAPI
serve it:

```bash
cd web && npm.cmd run build   # writes web/dist on Windows
cd .. && .venv/Scripts/python app.py   # now also serves / from web/dist
```

## Config (env vars)

- `PNP_CRAWL_DIR` — path to the pnp-crawl repo (default: sibling `../pnp-crawl`);
  used for crawl status only
- `PNP_EXPORT_DIR` — path to the pnp-export-data repo (default: sibling `../pnp-export-data`)
- `PNP_KB_URL` — KB API base URL (default: `http://127.0.0.1:8070`)
- `PNP_KNOWLEDGE_DIR` — path to this repo's `knowledge/` dir (default:
  `../../knowledge`, i.e. the real one); the Glossar tab reads
  `entity_registry.yaml`/`entity_rules.yaml` from here and writes
  `entity_rules.yaml` here on sync
- `PNP_TRANSCRIPT_DIR` — shared `*.json` transcript directory for Glossar,
  season status, estimates, freezes, and starts (default:
  `data/transcripts_final` in this repo)
- `PNP_BUNDLE_DIR` — optional bundle path. It must be inside
  a location whose inferred knowledge root matches `PNP_KNOWLEDGE_DIR`;
  otherwise season estimate/freeze/start are rejected before a child process
  launches. The default is
  `knowledge/bundle/splitter_des_ewigen`.

Season CLI commands receive absolute `--bundle` and `--transcripts` paths from
these settings. Their registry and `knowledge/frozen/` paths therefore share
the same knowledge root shown by the dashboard.

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
