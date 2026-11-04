# Workbench verification

Status: implementation and local functional/visual checks complete; remote CI
remains pending. This is not a release sign-off.

## Completed evidence

- Backend: 66 checks passed in the shared checkout (39 workbench and 27 existing
  dashboard checks), including the parallel agent's lock-contention regression.
  Backend Ruff checks also passed (2026-11-04).
- KB read API/OKF checks: 55 passed. Extraction retry/guard checks: 17 passed
  (implementation lead report, 2026-11-04).
- Frontend tests: `npm test -- --reporter=dot` passed 8 tests in 2 files. The
  rendered authoring flows open a listed campaign, save a Location and verify
  its request type and rendered row, then navigate away from and back to an
  unsaved draft.
- `npm run typecheck` and `npm run build` passed. Vite reported a non-blocking
  791 KB JavaScript chunk advisory.
- `npm run lint` exited 0 with two Fast Refresh warnings in generated shadcn
  button and badge components.
- Browser E2E: `npm run test:e2e` passed all 12 Chromium tests with no flaky
  retries. It used the local workbench Python environment and isolated browser
  cache.
- Canonical Linux visual comparison: all six desktop/narrow screenshots passed
  against existing baselines; no baseline updates were made. The run used
  `mcr.microsoft.com/playwright:v1.64.1-noble`, local image ID
  `sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f`,
  Node 26.13.0, and Python 3.12.3. JSON evidence reports 6 expected and 0
  unexpected tests at `.tools/linux-visual-evidence/results.json`; the HTML
  report is at `.tools/linux-visual-evidence/playwright-report/index.html`.
  These image runtimes differ from the project's documented Node 24 and Python
  3.11 setup.
- All six existing baseline images were also inspected for clipping and
  readability. Their files were left unchanged.
- Review preserves corrected notes in review state, restores accepted
  suggestions as actionable when restoring an earlier bundle revision, and
  groups same-name Character/NPC mentions from one source into one person
  suggestion.
- Production HTTP smoke passed against built assets on port 8091: create
  campaign, create linked Location and NPC entries, save a source, export and
  re-import ZIP preserving entries and sources, and restore a saved version.
  The smoke-test server was stopped.
- Windows launcher smoke: PowerShell parser passed. `Start-Workbench.ps1
  -NoBrowser` ran twice; the first invocation started the API and the second
  reused PID 39444. `/api/workspaces/config` returned the expected shape. The
  process was stopped and the endpoint was confirmed down. It skipped the
  broken dashboard `.venv` and used `.tools/workbench-venv`. At that time the
  available `web/dist` was the older technical dashboard build.
- Remote GitHub Actions were not run.

No live model-provider call was made or used for verification. No real campaign
content has been migrated. Installer packaging and remote CI execution remain
out of scope. Do not mark the first release complete until the acceptance
conditions in `intent.md` have evidence.
