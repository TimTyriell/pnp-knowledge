# ADR-001: Knowledge layer — OKF bundle in git as system of record; graph as optional derived index

**Status:** Proposed (needs user confirmation)
**Date:** 2026-07-22
**Deciders:** Noah + Claude (architecture session)

## Context

Two working prototypes exist in `c:\dev\pnp` — this is not a paper comparison:

### GraphRAG prototype: `pnp-graph-service` (mature)

- Neo4j + fixed Pydantic extraction schema, canonical `:Entity{id}` with an **alias registry + fuzzy match + SRD gazetteer resolver** — the identity layer is solved and tested.
- **Bitemporal versioning shipped** (WP9): `valid_from`/`valid_to`/`last_observed_session` on state edges, as-of reads in `retrieve.py` (`cli ask --as-of N`).
- Working vector retrieval over `:Entity` + `:Chunk` labels ("graph = table of contents, vector = the book").
- `cli reconcile-report` diffs the machine graph against the hand-authored report graph — a working cross-source reconciliation pattern.
- Costs: 3 Docker Neo4j containers (no-auth, local only), corrections require Cypher, truth lives in a DB — not diffable, not GM-editable, review of an ingest means inspecting a graph, not reading a diff.

### OKF prototype: `okf-experiments-main` (full-campaign run completed)

- `pnp_okf` pipeline (Azure gpt-4o structured outputs): ingest → extract → resolve → synthesize → emit. Ran the **whole campaign** (42 sessions, ~647k words) into `bundle/splitter_des_ewigen/` — characters, npcs, locations, factions, items, events, per-session recaps, all German, every concept citing `Session YYYY-MM-DD @ HH:MM:SS`.
- Human-editable `entity_registry.yaml` with `merge:` entries for Whisper-garbled names.
- **Observed failures in the actual bundle** (this grounds the decision):
  - Duplicate concepts from weak resolution: `characters/esterossa.md` **and** `characters/esterossa_torbhalm.md`; `characters/lindo_laut.md` **and** `characters/lindo_laut_pedro.md` (an in-fiction alias minted as a second person). `pnp_okf`'s resolver is registry + clustering only — far weaker than `pnp-graph-service`'s.
  - Links to concepts that were never emitted (`../gods/vasul.md`, `../gods/belorus.md` — no `gods/` directory exists). OKF tolerates broken links by spec, but nothing maintains them.
  - **No temporal model**: each concept is current-state prose with one `timestamp`. A session-30 as-of view is impossible from the bundle alone.
  - No use of transcript quality signal — verified: the `transcripts_final` JSON carries only `start/end/speaker/text`, no hoch/mittel/niedrig score and no `unsicher` markers. (That's a pnp-crawl gap, not an OKF gap — neither prototype could have used it.)

### Requirements the choice must satisfy

Single campaign scale (hundreds of concepts, not millions); temporal as-of reads ("summary for session 30 reflects what was true then"); GM hand-corrects facts without code; every fact auditable to session + timestamp; human review gate on every change that becomes visible; three consumers needing mostly **entity lookup + change-since-checkpoint**, only occasionally semantic/relationship discovery.

## Decision

**The OKF bundle is the single system of record for campaign knowledge, versioned in git.** Per the 2026-07-22 repo decision, it lives at `knowledge/` inside the `pnp-graph-service` monorepo (private, `TimTyriell/pnp-graph-service`) — which also hosts all services except `pnp-crawl` (see ARCHITECTURE §3.0). The Knowledge-Base service is a thin API over that directory plus the ingestion pipeline. Specifically:

1. **Git supplies the temporal model.** One commit (via a reviewed branch) per ingested session or doc; a tag per session (`s26`). As-of read = read at tag. Diff API = `git diff s25..HEAD -- knowledge/` — path-scoped so code commits in the monorepo never pollute knowledge deltas. This replaces WP9's bitemporal edges with a mechanism that is free, auditable, and human-legible — and it's the piece the OKF prototype was missing.
2. **Port the identity discipline from `pnp-graph-service`, not the database.** The resolver design (alias registry semantics, canonical typed IDs, "resolve deterministically before write", generic-mob/OOC gates) moves into the OKF pipeline. Concepts carry the pnp-report typed ID (`NPC_…`, `CHAR_…`, `LOC_…`) in frontmatter as the canonical key; file paths are display slugs. This directly fixes the duplicate-concept failures observed in the bundle.
3. **Conflict handling is a first-class bundle artifact.** Synthesis receives the current concept + new evidence; contradictions it can't reconcile are written to `conflicts/` as concept files (both claims, both citations, `status: open`) instead of silently choosing. Humans resolve them in review.
4. **The graph becomes an optional, derived, rebuildable index** — added later, only if the revisit trigger fires. It would be populated *from* the bundle and never written to directly; deleting it loses nothing. `pnp-graph-service` stays as-is (reference + the future index implementation), no further feature work now.

## Alternatives considered

- **GraphRAG (Neo4j) as system of record.** Best-in-repo identity + temporal + retrieval already built. Rejected because the two hard human requirements — GM hand-editing and reviewable changes — are exactly what a DB is worst at: every correction is Cypher, every review is graph inspection, and the wiki/summary consumers would still need a rendering layer to produce text. The graph's strengths (multi-hop discovery, semantic search) are not what the three consumers mostly need.
- **OKF as prototyped (as-is).** Rejected: the bundle demonstrates the failure modes (dupes, broken links, no temporality). OKF the *format* is right; the prototype's *pipeline* needs the graph project's identity layer and a git-based temporal/review model around it.
- **Dual-write hybrid now (bundle + graph kept in sync from day one).** Rejected: two writable stores = two truths + sync machinery, violating the "one owner" constraint for speculative benefit. YAGNI until the trigger fires.

## Consequences

- **Positive:** GM edits = edit a markdown file; every change reviewable as a git diff (the HITL gate for knowledge is literally a PR); full history + as-of for free; no database to operate; bundle renders on GitHub; portable (spec-conformant OKF); citations already proven in the prototype.
- **Negative / mitigations:**
  - No semantic search out of the box → phase-later: embed concept files locally (`nomic-embed-text` already in use) for a `/search` endpoint; the derived graph is the fuller answer if needed.
  - Link rot / broken links → extend `pnp_okf.validate` into a CI/link-check gate on the bundle repo; broken link = review-blocking warning.
  - Prose is harder to diff semantically than edges → keep concept bodies structural (the OKF spec itself recommends headings/lists/tables); per-session `## Historie` bullets make session deltas line-diffable.
  - Azure gpt-4o dependency in the prototype vs DeepSeek/Ollama elsewhere → open question #4, consolidate deliberately.

## Revisit trigger (any one of these reopens the decision)

1. Real usage produces relationship/discovery queries ("all NPCs hostile to FACTION_X ever", multi-hop) more than ~weekly that link-walking + grep can't answer → build the **derived** graph index from the bundle.
2. Bundle grows past ~1,500 concepts or per-ingest review diffs stop being humanly reviewable.
3. As-of correctness bugs traced to prose-state ambiguity that structured edges would have prevented.
4. The GM in practice never hand-edits the bundle for two months — the editability argument then carried less weight than assumed.
