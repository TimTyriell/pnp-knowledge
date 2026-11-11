# Browser setup verification

Verified locally on 2026-11-04 with Node 24.11.1 and Playwright Test 1.64.1.
Windows used Python 3.11.15. Linux used Python 3.11.18 inside
`mcr.microsoft.com/playwright:v1.64.1-noble` (image digest
`sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f`).

| Check | Result |
| --- | --- |
| `npm test` | 8 React tests passed |
| `npm run typecheck` | Application, unit tests, configuration, browser tests passed |
| `npm run lint` | Passed; two existing shadcn Fast Refresh export warnings |
| `npm run build` | Passed; existing bundle-size warning |
| Dashboard pytest | 66 passed on Windows and 66 on Linux, including lock contention regression |
| Chromium behavior, `--repeat-each=2 --workers=2` | 24 passed on Windows and 24 on Linux |
| Linux visual comparison, `--repeat-each=2 --workers=2` | 12 passed against six reviewed PNGs, without updating them |
| Harness self-check | Concurrent ports/storage isolated, missing interpreter explained, inherited key disabled, stopped servers unreachable |
| Playwright CLI | Installed its pinned Chromium, opened/snapshotted fictional workspace in a named isolated session, closed browser |
| Deliberate failure probe | Nonzero exit, screenshot, trace, browser/server logs, HTML and JSON reports verified; temporary failing test removed |
| CI definitions | Both workflow files parsed as YAML; hosted GitHub Actions have not been run |

The browser checks found a Windows lock-sentinel read outside the conflict
handler and review actions overflowing a narrow viewport. Both received small
fixes and regression coverage. Test servers snapshot the built assets so another
agent's build cannot delete files they are serving.

No private campaign data, sibling services, provider credentials, paid calls,
live extraction, or real model-worker execution were used. Existing npm audit
findings in Vite and source-map-js were left outside this testing change.
