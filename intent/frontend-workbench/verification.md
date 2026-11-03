# Workbench verification

Status: implementation complete; visual browser QA and remote CI remain pending.
This is not a release sign-off.

## Completed evidence

- Backend: 65 checks passed (38 workbench and 27 existing dashboard checks);
  Ruff was clean (implementation lead report, 2026-11-04).
- KB read API/OKF checks: 55 passed. Extraction retry/guard checks: 17 passed
  (implementation lead report, 2026-11-04).
- Frontend tests: `npm test` passed 8 tests in 2 files. The rendered authoring
  flows open a listed campaign, save a Location and verify its request type and
  rendered row, then navigate away from and back to an unsaved draft.
- `npm run typecheck` passed in the shared checkout. `npm run build` passed; Vite
  reported a non-blocking 791 KB JavaScript chunk advisory.
- `oxlint src` passed with two Fast Refresh warnings from generated shadcn
  components. The broader `npm run lint` currently fails on three hook-rule
  errors in the concurrently maintained `e2e/fixtures.ts`.
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
- Remote GitHub Actions were not run; the current workflow includes changes from
  another active workstream and was not revalidated here.

## Pending evidence

- Visual browser QA was unavailable because the connected browser host returned
  no browser inventory. Canonical Linux visual/browser E2E has not run. The HTTP
  smoke covered backend behavior and built asset serving, not visual interaction.

No live model-provider call was made or used for verification. No real campaign
content has been migrated. Installer packaging and remote CI execution remain
out of scope. Do not mark the first release complete until the acceptance
conditions in `intent.md` have evidence.
