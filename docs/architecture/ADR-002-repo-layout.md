# ADR-002: Consolidate frozen GraphRAG under `graph/`; rename repo to `pnp-knowledge`

**Status:** Accepted
**Date:** 2026-07-22
**Supersedes:** the layout notes in [ADR-001](ADR-001-knowledge-layer.md) §Decision and ARCHITECTURE §3.0

## Context

After ADR-001 (OKF-in-git is the system of record; the Neo4j GraphRAG pipeline
is frozen), the memory repo accumulated both systems at the top level as peers:

- Active OKF: `services/kb`, `services/summary`, `knowledge/`.
- Frozen GraphRAG: `src/pnp_graph`, `compare/`, `data/`, `tests/`,
  `export_graph.py`, `docker-compose.yml`, most of `docs/`, `transcripts/`,
  `state/`, plus the report loaders in `reports/`.

Nothing signalled which was which. `src/` reads as *the* code, but it's the
frozen part; the active tests live under `services/*` while `tests/` at the root
holds graph tests only. A reader can't tell the live system from the legacy one,
and the repo name `pnp-graph-service` points at the frozen half.

## Decision

**1. Consolidate every frozen GraphRAG artifact under a single top-level
`graph/` directory.** The top level becomes: `knowledge/` (system of record),
`services/` (active code), `reports/` (shared data), `docs/architecture/`
(system docs), and `graph/` (frozen, self-contained). Rule: `knowledge/` +
`services/` = live, `graph/` = frozen.

The move is mechanical and history-preserving (`git mv`):

- Package name `pnp_graph` is unchanged → **zero import edits**.
- Graph config resolves paths from `REPO_ROOT = Path(__file__).parents[2]`,
  which becomes `graph/` after the move, so `data/`, `transcripts/`, `state/`
  self-heal by moving together.
- Report *data* stays in the shared top-level `reports/`; only the graph report
  *loaders* moved into `graph/`, with their report path repointed one level up.
- Fixed alongside: `.vscode/launch.json` (`PYTHONPATH` → `graph/src`, cwd →
  `graph`), `.gitignore` (paths under `graph/`).

**2. Rename the GitHub repo `pnp-graph-service` → `pnp-knowledge`.** The repo is
the campaign's knowledge/"memory" service; the graph that named it is now a
frozen subdirectory. GitHub keeps redirects, but remotes and cross-repo
references are updated to the new name.

**3. Not `services/graph/`.** `services/` means "things we actively run"; a
distinct top-level `graph/` states "frozen" more clearly than nesting it beside
the live services.

## Alternatives considered

- **`services/graph/`** — groups all code, but blurs active-vs-frozen, the exact
  problem being solved. Rejected.
- **`legacy/graph/` or `archive/graph/`** — louder, but the graph is a documented
  *future derived index*, not dead; `graph/` + a FROZEN README says enough.
- **Delete the graph** — it's the ADR-001 fallback implementation and a rich
  design record; deleting it forfeits the revisit path. Rejected.
- **Keep the repo name** — cheap, but leaves the misleading name that motivated
  this ADR. Rejected now that the rename cost (redirects + a few references) is
  small and paid once.

## Consequences

- Top level is readable at a glance; new contributors see the live system first.
- The frozen graph is quarantined and self-contained (`graph/README.md` states
  its status), so it stops competing for attention with active work.
- One-time costs: contributors re-clone or update the remote URL; the local
  working directory should be renamed to `pnp-knowledge` for consistency; the
  docker-compose project namespace changes with its directory (existing dev
  volumes are throwaway no-auth data — `docker compose down` in the old location
  first if reclaiming them).
- Pre-existing `graph/tests/test_golden.py` drift (golden file stale vs the
  merged alias/role changes in `750d6f1`) is unaffected by this move and tracked
  separately.

## Revisit trigger

If the graph is ever un-frozen (ADR-001's discovery-query trigger), revisit
whether it graduates from `graph/` back into `services/` as an active component.
