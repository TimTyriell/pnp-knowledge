# Implementation plan: local campaign workbench

Status: implementation and local checks complete; visual/browser E2E pending,
2026-11-04

## Sequence and files

1. Implement `workbench.py` for schemas, immutable bundle revisions, imports
   and exports, sources, review decisions, and the extraction worker. Reuse the
   editable local `pnp_okf` package for serialization, validation, and extraction.
2. Implement `workbench_api.py` with validated loopback routes and worker
   lifecycle; include its router before static mounting in `app.py`.
3. Build the React/TypeScript workbench in `services/dashboard/web/src/App.tsx`
   and `workbench.ts`, using shadcn/ui, Zustand drafts, and TanStack Query. Keep
   the current technical dashboard reachable independently. Add rendered-flow
   tests in `App.test.tsx` and `App.flow.test.tsx`.
4. Document setup, provider configuration, local storage, and limitations. Add
   `Start-Workbench.ps1`, keep the npm lockfile, and integrate dashboard and
   frontend checks into `.github/workflows/ci.yml`.
5. Record actual results and remaining verification limits in `verification.md`.

## Risks and proof

- Data loss: immutable staged revisions and atomic manifest activation; inject
  write failure and verify the previous bundle remains readable.
- Name drift: no ID regeneration on edit; review explicitly resolves ambiguous
  identities; import/export keeps original paths, auxiliary files, metadata,
  and review decisions.
- Accidental AI spending: jobs require an explicit user action and configured
  provider; all verification replaces only the external extraction boundary.
- Cross-site local writes: loopback and Origin/Host checks, validated payloads,
  no request-controlled filesystem paths.
- Import attacks: archive traversal, symlinks, duplicate members, encoding,
  decompression limits, and malformed documents reject before publication.
- Review overwrite: base revision checks; batch review is one accepted revision.

## Stop condition

Manual and source-assisted creation work end to end, knowledge and review state
survive round-trip export/import, restores preserve recoverability, failed writes
leave the prior snapshot selected, and the appropriate checks pass. Report
remaining verification limits; do not claim a packaged app or live-campaign
integration.
