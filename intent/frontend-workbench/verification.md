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

## Imported Windows campaign regression (2026-11-04)

The existing imported workspace contained all 1,182 entries and all 1,193
original files, with no missing or changed files. Reading/importing succeeded,
but editing an imported entry failed: all concept files used CRLF, while the
editor's three frontmatter reads omitted the newline normalization already
used by the reader. The fix normalizes reads without rewriting imported files.

- The CRLF metadata-preservation and reciprocal-link regressions failed before
  the fix. Dashboard pytest now passes 69 checks; backend Ruff passes.
- An isolated copy of the real ZIP passed import (201), ordinary edit (200),
  and export (200). Only the edited concept changed; no original file was
  missing. Export added the expected workbench metadata file. IDs, rich
  relationships, custom frontmatter, and untouched documents were preserved.
- Fictional browser regressions reproduced internal links leaving the app,
  read-only Session documents offering Edit, and an unbounded 1,182-entry list
  hiding selected details on a narrow viewport.
- The fixes resolve exact campaign link targets inside the workbench, explain
  read-only documents, bound the list, and reveal selected details when needed
  on narrow screens. Unit tests pass 10 checks, TypeScript and production build
  pass, and lint exits 0 with the same two generated-component warnings.
- The complete Chromium suite passes 15 tests with no retries, failures, or
  skips. The new cases exercise CRLF import/edit/export through the real API,
  root and relative Markdown links, read-only Session pages, and all 1,182
  fictional entries at 390 by 844 pixels.
- All six canonical Linux visual comparisons pass against unchanged baselines,
  with no failures, skips, or flaky tests. Evidence is saved separately at
  `.tools/linux-visual-imported-evidence/results.json`. The verified image ID
  and Node/Python versions match the earlier Linux run documented above.

The private bundle and the user's existing workspace were not modified. No
provider calls were made. Remote CI was not run. Restart the workbench server
and refresh the browser to load the fixes; the existing imported campaign can
be reopened without another import.
