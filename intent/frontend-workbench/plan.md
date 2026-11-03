# Implementation plan: local campaign workbench

Status: selected under user delegation, 2026-11-03

## Sequence and files

1. Add `services/dashboard/test_workbench.py` before the implementation. Exercise
   real temporary workspaces: persistence, immutable identity, stale edits,
   review, correction preservation, safe archives, failed writes, and restore.
2. Add `workbench.py` for schemas, immutable bundle revisions, imports/exports,
   sources, review decisions, and extraction worker entry point. Reuse pnp_okf
   serializers/models/validation/extraction as an editable local dependency.
3. Add `workbench_api.py` for validated local routes and worker lifecycle; include
   its router before static mounting in `app.py`. Test HTTP behavior and local
   mutation protections without external services.
4. Add Tailwind/shadcn components and `src/features/workbench/` for typed API,
   Zustand drafts, Query integration, editor, source intake, review, and history.
   Keep the current dashboard reachable independently. Add frontend behavior
   tests before implementing those behaviors.
5. Document local setup, provider configuration, runtime storage, and limitations.
   Add a launcher and preserve a lockfile for reproducible frontend installs.
6. Run focused backend and frontend suites, regression dashboard tests, typecheck
   and production build. Exercise the rendered interface when tools permit it.
   Record actual results and limits in `verification.md`.

## Risks and proof

- Data loss: immutable staged revisions and atomic manifest activation; inject
  write failure and verify the previous bundle remains readable.
- Name drift: no ID regeneration on edit; review explicitly resolves ambiguous
  identities; import/export keeps original paths and arbitrary metadata.
- Accidental AI spending: jobs require an explicit user action and configured
  provider; all verification replaces only the external extraction boundary.
- Cross-site local writes: loopback and Origin/Host checks, validated payloads,
  no request-controlled filesystem paths.
- Import attacks: archive traversal, symlinks, duplicate members, encoding,
  decompression limits, and malformed documents reject before publication.
- Review overwrite: base revision checks; batch review is one accepted revision.

## Stop condition

Both manual and source-assisted creation work end to end, preserved knowledge
survives new sources and round-trip export/import, errors preserve the previous
revision, and the appropriate checks pass. Report genuine remaining limitations;
do not claim a fully packaged or live-campaign-integrated release.
