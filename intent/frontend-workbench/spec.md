# Design: local campaign workbench

Status: selected under user delegation, 2026-11-03

## User experience

The start page offers create campaign or import bundle. A campaign has Knowledge,
Sources, Review, and History views. Preserve the existing technical dashboard
behind a separate navigation item. Its availability must not gate authoring.

Knowledge supports search, type filters, entry creation, aliases, related-entry
selection, and a Markdown description with formatting controls and safe preview.
Save explicit edits; retain unsaved drafts locally across navigation and reload.

Sources accepts pasted text or UTF-8 .txt/.md files. The user supplies a title
and date. Extraction is an explicit action with a provider/cost disclosure.
Missing provider configuration must not block manual authoring. Reuse the KB's
cached extractor without running the live pipeline or changing its prompts.

Review groups extracted mentions by identity, shows their notes and evidence
beside existing content, and allows accept/reject/edit. Exact unique names and
aliases identify existing entries; fuzzy or multiple matches require an identity
choice. New entries can be accepted together. Existing descriptions are preserved;
new evidence is appended as source-attributed notes, never silently rewritten.
Manual edits and rejected proposals are durable. Repeated source processing is
idempotent. Stale reviews fail with an actionable conflict instead of overwriting.

## Ownership and persistence

Python/FastAPI owns authoring commands. React/TypeScript uses shadcn/ui and
Tailwind, Zustand for UI and drafts, and TanStack Query for server state.
Do not add a Node application server or change the read-only KB API.

Store workspaces under an ignored dashboard data directory, configurable with
PNP_WORKSPACE_DIR. They do not write to knowledge/ or invoke its ingest process.
Accepted OKF/Markdown bundle files are stored in immutable revisions on disk; a
small atomically replaced `workspace.json` stores current sources, jobs,
proposals, and the selected bundle revision. History restores create another
bundle revision from the chosen content while keeping current source/review/job
state. An accepted suggestion stays accepted when its source heading and note
remain in the restored entry; otherwise it re-pends with its corrected note.
Suggestion targets and candidates are reconciled with the restored entries so
the resulting bundle remains portable. A failed preparation leaves the prior
bundle revision selected. This is
application-owned local data, not Git history and not adoption of the canonical
live repository. Export is the explicit handoff to its existing PR/tag process.
This exception to the live storage lifecycle does not change ADR-001 for the
live campaign.

Retain arbitrary imported frontmatter, Markdown, and auxiliary bundle files.
An import does not rewrite existing concept paths or IDs. New entries receive
server-assigned paths once; title edits do not move them. Validate links and
types with the existing bundle validator before activating a revision/export.

Persist sources and jobs separately from accepted knowledge. Jobs execute in a
separate Python process, have durable status, and become retryable failures
after interruption. Only one worker job per application instance at a time.
Model output is untrusted input. Bound files, archive sizes, model output, and
text; reject unsafe paths and invalid YAML. Never render imported HTML.

Loopback-only routes and same-origin mutation checks protect local writes.
The browser cannot choose arbitrary filesystem paths. Export a ZIP containing
the bundle, sources, and review/job state; import it into a fresh workspace
after checking entries, duplicates, and file sizes. Imported auxiliary files
and unsupported frontmatter remain intact.

## Delivery boundaries

Text input is bounded and the UI explains the limit rather than truncating it.
No audio, hosted accounts, automatic wiki publication, live campaign migration,
or model calls during verification. Import preserves unsupported metadata and
files rather than making them editable. Processing jobs reuse KB extraction,
not full synthesis; this reduces rewrites and the number of paid calls.

Developer startup uses existing per-service tooling; a PowerShell launcher opens
the built local application. Bundle import/export and workspace revisions provide
portable recovery, including pending and rejected review decisions. CI installs
the local KB package for dashboard checks and runs the frontend tests and
production build. Distribution as an installer is deferred; do not describe the
development setup as a packaged app.
