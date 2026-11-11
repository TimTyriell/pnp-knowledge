# Workbench verification

Status: implementation and local functional/visual checks complete, with GitHub
CI evidence and merge preparation recorded below. The latest review and checks
are tracked in [PR #39](https://github.com/TimTyriell/pnp-knowledge/pull/39).
This is not a release sign-off.

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

## Merge preparation (2026-11-11)

- Work was isolated in `.tools/worktrees/workbench-merge-39` on the preparation
  branch. The original checkout, unrelated local settings, and private campaign
  remained untouched.
- Merge commit `d4f1903` reconciles `main`, retaining the accepted intent and
  delegated approvals. The review command now reads `AGENTS.md`.
- A fresh-context Luna review identified incorrect restore handling. Commit
  `afc458e` preserves accepted decisions whose actual source evidence remains,
  reopens suggestions whose evidence is absent, and reconciles pending targets
  and candidate references with the restored entries.
- Regression tests failed before the fix. They cover selective acceptance when
  restoring between two reviews, preserved rejected decisions and source data,
  note whitespace, missing targets in pending and accepted suggestions, and
  export/reimport after restore. A current-revision restore assertion was
  corrected to retain an accepted suggestion whose corrected note is present.
- Local dashboard: **74 passed**; Ruff passed. Local KB: **422 passed, 63
  skipped, 1 xfailed** in the private-data-free worktree. Summary: **11 passed**.
- Local frontend: lint and typecheck passed, **10 unit tests** and **15 Chromium
  tests** passed, and production build passed. Existing generated-component
  Fast Refresh warnings and the Vite chunk-size advisory remain non-blocking.
- [CI run 43064660075](https://github.com/TimTyriell/pnp-knowledge/actions/runs/43064660075)
  passed all six jobs on the reconciled merge commit, including browser
  behavior and canonical Linux visual comparisons. Follow-up checks for the
  restore correction and final documentation are available on the PR's
  [checks page](https://github.com/TimTyriell/pnp-knowledge/pull/39/checks).
- The independent Luna follow-up found no remaining blocker for the restore
  correction. The required `/review-pr 39` procedure supplies the final review
  comment and reviewed commit on GitHub; its result must be checked against the
  latest PR head before merging.
- The [first required review](https://github.com/TimTyriell/pnp-knowledge/pull/39#pullrequestreview-5862724656)
  covered `0409b60` and returned `Merge: yes`. All six CI jobs passed on that
  head. The review also identified a non-blocking bare-500 error when applying
  suggestions to an imported entry exceeding editor limits. A regression
  reproduced it; the shared API boundary now returns an actionable, input-free
  422 response while preserving the entry, revision, and pending suggestion.
  The corrected implementation receives a follow-up required review and CI on
  the latest PR head. Orphan-revision cleanup and the unrelated-workspace lock
  message remain non-blocking follow-ups.

No paid model-provider test or private campaign migration was performed.
GitHub's main-branch rules require linear history; the final merge is a human
squash merge after the latest checks and required review are complete.
