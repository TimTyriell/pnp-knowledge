# Campaign workbench frontend

React/TypeScript UI for the local FastAPI campaign workbench. This project is
also a reference for agentic development: explore an isolated fictional
workspace, reproduce a behavior, change the code, run focused checks, then
inspect the resulting evidence.

## Set up a public checkout

Use Node 24 and Python 3.11. The browser suite needs neither the private
`knowledge/` repository nor sibling services, API keys, or model-provider access.
Run these commands from this `web` directory.

Windows PowerShell:

```powershell
py -3.11 -m venv ../.venv
../.venv/Scripts/python.exe -m pip install -e ../../kb -e "..[dev]"
npm.cmd ci
npx.cmd playwright install chromium
npm.cmd test
npm.cmd run test:e2e
```

Linux:

```bash
python3.11 -m venv ../.venv
../.venv/bin/python -m pip install -e ../../kb -e '..[dev]'
npm ci
npx playwright install --with-deps chromium
npm test
npm run test:e2e
```

The harness defaults to the dashboard's `.venv` interpreter. To use another
environment, set `PNP_TEST_PYTHON` to its executable path (PowerShell:
`$env:PNP_TEST_PYTHON = 'C:/path/to/python.exe'`; Bash:
`export PNP_TEST_PYTHON=/path/to/python`). The interpreter must import the
dashboard dependencies and `pnp_okf`. Tests never install Python packages for you.

For normal product startup and provider configuration, see the
[dashboard README](../README.md). For HMR, run that README's backend and
`npm run dev`; browser acceptance tests deliberately exercise the production
build instead.

## Choose the right check

| Command | Checks |
| --- | --- |
| `npm test` | Fast React behavior tests in Vitest/jsdom |
| `npm run lint` | Frontend, test, and configuration lint |
| `npm run typecheck` | Application, unit-test, and browser-test TypeScript |
| `npm run build` | Production frontend |
| `npm run test:e2e` | Build, then Chromium against real FastAPI and storage |
| `npm run test:e2e:ui` | Build, then Playwright UI mode |
| `npm run test:visual` | Build, then six Linux screenshot comparisons |
| `npm run e2e:serve` | Build, then isolated fictional workspace for exploration |
| `npm run test:report` | Open the latest local HTML report |

Pass Playwright filters through npm to verify a focused change:

```bash
npm run test:e2e -- --grep "draft"
npm run test:e2e -- --repeat-each=2
```

The Python suite owns detailed extraction, validation, revision, and persistence
rules. Run it from `services/dashboard` using that service's environment:
`python -m pytest`. Browser tests own user-visible integration: authoring,
draft recovery, review decisions, history, ZIP transfer, and keyboard access.

## Explore with a coding agent

Start the safe server in one terminal:

```bash
npm run e2e:serve
```

It prints a loopback URL with an automatically allocated port. In another
terminal, open that exact URL using the locked Playwright CLI dependency:

```bash
npx playwright-cli install-browser chromium
npx playwright-cli -s=workbench open http://127.0.0.1:PRINTED_PORT
npx playwright-cli -s=workbench snapshot
# Use the returned element references to inspect and interact.
npx playwright-cli -s=workbench close
```

Keep one named browser session per task. Stop the exploration server with
Ctrl+C when finished. Do not point exploratory commands at a GM's running
workbench or copy its data into fixtures.
Browser installation is a one-time step. The CLI has its own pinned browser
version; `.playwright/cli.config.json` selects an isolated Chromium session
without requiring a system Chrome installation. Exploration artifacts go to
`test-results/exploration`.

Agent loop:

1. Explore the fictional campaign and write the expected visible behavior.
2. Reproduce the bug with the narrowest suitable unit or browser test.
3. Change the responsible code; keep assertions tied to the requirement.
4. Run the focused test, then lint, types, unit tests, and relevant browser tests.
5. Inspect the trace and screenshot if behavior or appearance changed.

[Playwright's planner, generator, and healer](https://playwright.dev/docs/test-agents)
are optional authoring aids. Review generated tests and repairs like other code.
CI never generates tests, heals assertions, skips failures, or updates baselines.

## Isolation and fixtures

Every browser test starts its own Python server on a fresh loopback port and
stores its campaign under that test's output directory. The fixture waits for
readiness, attaches server logs, and stops the process at teardown. No existing
workbench server is reused. Parallel tests and agent sessions have separate
ports, browser storage, and workspaces.
Each server also snapshots the built frontend, so a later build cannot remove
assets while an agent is exploring or a test is running. When running suites
concurrently in the same checkout, pass distinct Playwright `--output` paths;
Playwright clears that directory at the start of a run.

The test-only runner redirects knowledge, crawl, export, and workspace paths to
synthetic directories and uses an unused loopback KB address. Provider
credentials are explicitly empty before imports, so `.env` loading cannot
restore them. The browser fixture rejects unexpected external requests.

The `empty`, `review`, and `failed` scenarios use fictional campaign data.
Review and failed-job states are seeded before serving through
`process_job(..., extractor=...)` with deterministic extraction results or a
deliberate exception. Review submissions, authoring, imports, and exports use
the real HTTP endpoints and storage. These scenarios verify review integration,
not live model quality or real worker execution. Production code has no test
routes or test-mode switches.

## Diagnose a failed test

Local runs have no retries. CI permits one diagnostic retry but fails if a test
is flaky. Traces are recorded for every test and retained on failure, along
with failure screenshots and server/browser error logs. Reports are HTML for
inspection and JSON for agents.

```bash
npm run test:report
npx playwright show-trace test-results/PATH_FROM_FAILURE/trace.zip
```

Read the failing assertion first. In Trace Viewer, inspect its DOM snapshot,
network request/response, and server log attachment. Fix the cause before
changing locators or waits. Use role and label locators, awaited assertions, and
response/event waits; avoid fixed sleeps and selectors based on element order.

CI uploads `dashboard-browser-evidence` for seven days. Behavior and visual
runs retain separate reports under `playwright-report/behavior` and
`playwright-report/visual`; open a downloaded report using
`npx playwright show-report PATH_TO_REPORT`.

## Visual baselines

Six images cover campaign start, a populated editor, and review with an identity
decision at 1440×900 and 390×844. Fixed time, locale, timezone, disabled
animations, and font/content readiness keep comparisons stable.

The canonical environment is the official
`mcr.microsoft.com/playwright:v1.64.1-noble` container used by both browser CI
and the **Propose visual baselines** workflow. Keep its version aligned with
the locked `@playwright/test` version. Windows behavior tests run normally;
pixel comparisons are Linux-only, and an arbitrary Linux host is not the
baseline-authoring environment.

For an intentional UI change:

1. Push the branch and manually run **Propose visual baselines** for that ref.
2. Download the `proposed-visual-baselines` artifact.
3. Inspect all six images and compare them with the intended UI change.
4. Copy only the reviewed PNGs into `e2e/__screenshots__/` and commit them with
   an explanation of the appearance change.
5. Run normal CI again; it compares images and never rewrites expectations.

To reproduce locally inside the same container after installing Node 24,
Python 3.11, and project dependencies, run:

```bash
PNP_TEST_PYTHON=python npm run test:visual
# Only when intentionally proposing reviewed replacements:
PNP_TEST_PYTHON=python npm run test:visual -- --update-snapshots
```

Broad screenshot coverage, additional browser engines, hosted reporting, and
autonomous test healing are deliberately outside this first setup.
