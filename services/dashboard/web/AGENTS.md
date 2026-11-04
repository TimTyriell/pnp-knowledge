# Frontend development and verification

Read [README.md](README.md) for setup, fixture boundaries, and evidence paths.
Use the dashboard's Python environment; the repository-root `.venv` belongs to
the frozen graph pipeline.

- Reproduce the requested behavior before editing. Add the smallest meaningful
  regression test in Vitest for React behavior or Playwright for browser/API
  integration. Keep detailed extraction and persistence cases in pytest.
- Explore with `npm run e2e:serve` and the printed URL. Use a named
  `playwright-cli` session per task; close it and stop the server afterward.
  Never target the user's running workbench or private campaign data.
- Browser tests belong in `e2e/**/*.spec.ts`; unit tests belong in
  `src/**/*.test.{ts,tsx}`. Reuse the isolated fixtures and fictional scenarios.
- Prefer roles, labels, and meaningful region scoping. Use awaited assertions
  and response/event waits; do not add fixed sleeps, positional selectors, or
  order-dependent tests to make failures disappear.
- During development run focused checks. Before reporting completion run
  `npm run lint`, `npm run typecheck`, `npm test`, and relevant
  `npm run test:e2e` tests. Run dashboard pytest when backend behavior changes.
  UI appearance changes also need the Linux visual check or an explicit report
  that canonical-environment verification remains pending.
- Inspect failed assertions, traces, screenshots, and server/browser logs.
  Do not weaken assertions, add skips, increase retries, or accept screenshot
  changes merely to obtain a green run. Explain the requirement or intended
  behavior behind any expectation or baseline update.
- Baselines are generated in the same pinned Linux Playwright container as CI.
  Use the manual baseline proposal workflow, review its six PNGs, then commit
  accepted changes. Ordinary CI only compares.
- Planner/generator/healer tools are optional development aids. Review their
  output; do not introduce automatic healing or test generation into CI.
- Preserve unrelated in-progress edits. Report commands actually run and any
  remaining verification limits; do not claim CI or provider checks ran locally.
