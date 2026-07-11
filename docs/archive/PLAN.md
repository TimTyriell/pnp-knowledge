# pnp-graph — Architecture & Ingestion Plan

Service in the `c:\dev\pnp` campaign toolchain. Turns TTRPG session transcripts
into an accumulating Neo4j knowledge graph via a local Ollama LLM. Downstream
`pnp-fandom-service` reads this graph (or its derived summaries) to write the wiki.

## Decisions (locked)

- **Input**: raw JSON transcripts only (`sample_transcripts/*.json`). Not the
  pnp-report markdown — keeps pnp-graph independent of report authoring.
- **Storage**: typed entities + relationships **plus a per-session summary text**
  for each entity (provenance trail — how an entity looked/changed each session).
- **Update policy**: **append + version, never delete.** Facts get `valid_from` /
  `valid_to` session stamps. Nothing overwritten; query "as of session N" works.
- **Ordering**: process sessions **oldest → newest** (by transcript date), so the
  graph builds in story order and versioning stamps are monotonic.

---

## Target folder structure

```
pnp-graph/
├── transcripts/            # input JSON (renamed from sample_transcripts/); date in filename
├── state/
│   ├── ingest_log.jsonl    # one line per session: status, counts, hash, timestamp
│   └── failures/           # full error context + raw LLM output for failed chunks
├── src/pnp_graph/
│   ├── __init__.py
│   ├── config.py           # model, neo4j url, chunk sizes, paths — all tunables
│   ├── schema.py           # Pydantic models (Character/Location/Item/Quest/Event/Faction/Relationship)
│   ├── chunking.py         # pack_segments + load — moved from extract_to_graph.py as-is
│   ├── extract.py          # LLM call per chunk, retry/repair, merge
│   ├── store.py            # Neo4j writes: versioned MERGE, summaries, constraints
│   ├── ingest.py           # orchestrator: order sessions, resume, per-session txn
│   └── cli.py              # `python -m pnp_graph.cli ingest|status|reset-session <id>`
├── tests/
│   └── test_chunking.py    # the one non-LLM unit (pack_segments invariants)
├── PLAN.md
└── CLAUDE.md
```

Vendored `ai-knowledge-graph/` stays untouched (third-party reference, not the pipeline).

`session_id` = transcript date (`2025-03-26`), parsed from filename. Stable, sortable,
matches pnp-report's `Session_Report_S<NN>_<date>` convention.

---

## Data model in Neo4j

Nodes (unchanged labels): `Character`, `Location`, `Item`, `Quest`, `Event`,
`Faction`, plus `Session {id, date, seq}`.

**Versioned facts.** Instead of `SET node.status = x` (overwrite), mutable properties
become versioned. Two viable shapes — recommend **(A) property-history edges**:

- (A) Each fact assertion is a `:Fact` node: `(entity)-[:HAS_FACT]->(:Fact {key, value, valid_from, valid_to, session_id, confidence})`. `valid_to = null` means current. A new session that changes `quest.status` adds a new `:Fact` and sets the prior fact's `valid_to` to the new session. Query current = `valid_to IS NULL`.
- (B) simpler: keep scalar props as "latest" for fast reads, but also append to a `:Fact` history. Denormalized; latest-value queries stay one hop.

Pick (A) for a clean campaign log; add (B)'s convenience props only if wiki queries get slow.

**Per-session entity summary.** `(entity)-[:SUMMARIZED_IN {session_id}]->(:Summary {text, session_id})`.
One short LLM-written paragraph per entity per session it appeared in. This is what
`pnp-fandom-service` turns into prose; also a human-readable provenance trail.

**Relationships** keep `confidence` + `evidence_chunk`, gain `session_id`, `valid_from`,
`valid_to` (same append-version rule — a relationship that stops being true gets `valid_to` set, not deleted).

---

## Ingestion flow (oldest → newest, resumable)

```
ingest():
  sessions = sorted(transcripts/*.json, by date asc)
  for each session:
     if already in ingest_log as "ok" with matching file hash:  skip   # resume / idempotent
     seq = position in chronological order
     try:
        chunks = chunk(session)
        graph  = extract_all_chunks(chunks)        # per-chunk LLM, retry on parse fail
        summaries = summarize_entities(graph)       # one LLM call per entity (or batched)
        with neo4j tx:                              # ONE transaction per session — atomic
            ensure_constraints()
            upsert Session{id,date,seq}
            apply_versioned(graph, session_id, seq) # close prior facts, add new, stamp
            write_summaries(summaries, session_id)
        log "ok" + counts + file hash
     except: 
        log "failed" + write state/failures/<id>/...   # raw LLM output, traceback, chunk index
        continue                                    # don't let one session block the rest
```

### Safety nets

1. **Per-session atomic transaction.** A session either fully lands or not at all.
   No half-ingested session corrupting the graph. (Current script writes statement-by-statement
   with no transaction — a crash mid-session leaves partial state.)
2. **Resume via ingest_log + file hash.** Re-running skips sessions already "ok".
   If a transcript file changed (re-transcribed), hash mismatch → re-ingest that session,
   first closing/superseding its prior facts (idempotent re-run).
3. **Chunk-level retry + repair.** Local LLM occasionally emits invalid JSON / hallucinated
   schema. On parse failure: retry once with a "return valid JSON only" reminder; on second
   failure, log the chunk to `failures/` and continue (partial session better than none —
   flagged so it can be re-run).
4. **Entity-name normalization guard.** Before MERGE, trim/normalize names so
   "Schleichfurz" / "Schleichfurz " / "der Schleichfurz" don't fork into 3 nodes.
   Keep a per-session alias map; low-confidence near-duplicates logged for review, not auto-merged.
5. **Relationship endpoint validation.** Already partly present — drop any relationship
   whose subject/object isn't an extracted entity (model sometimes invents endpoints),
   log dropped ones rather than silently MERGE-creating empty nodes.
6. **Dry-run / preview mode.** `ingest --dry-run` runs extraction + prints the diff it
   *would* apply (new entities, changed facts, closed facts) without touching Neo4j.
   Lets you eyeball a session before committing — mirrors fandom-service's review gate.
7. **Neo4j precheck.** Fail fast with a clear message if `bolt://localhost:7687` refuses
   (Desktop DBMS not started) — before spending minutes on LLM extraction.

---

## CLI

```bash
python -m pnp_graph.cli ingest                 # all new/changed sessions, oldest→newest
python -m pnp_graph.cli ingest --only 2025-04-01
python -m pnp_graph.cli ingest --dry-run
python -m pnp_graph.cli status                 # table: session, seq, status, entity counts
python -m pnp_graph.cli reset-session 2025-04-01   # close that session's facts, allow re-ingest
```

---

## Implementation phases

1. **Refactor, no behavior change.** Split `extract_to_graph.py` into the `src/pnp_graph/`
   modules above. Move `pack_segments` + tests. Verify `ingest` on `sample_transcripts/`
   still produces the same graph as today (minus the new versioning).
2. **State + resume.** `ingest_log.jsonl`, file-hash skip, `status` command, per-session
   transaction, Neo4j precheck.
3. **Versioning.** `:Fact` history model, `valid_from`/`valid_to` stamping, `seq` ordering,
   "as of session N" example query in CLAUDE.md.
4. **Per-session summaries.** `:Summary` nodes, the summarize-entity LLM step.
5. **Safety hardening.** Chunk retry/repair, `failures/` dumps, name normalization,
   `--dry-run` diff.

Each phase independently runnable on the 3 sample transcripts before moving on.

---

## Open questions for later (not blocking)

- Summary granularity: every entity every session is a lot of LLM calls (26 sessions ×
  N entities). May batch ("summarize these 10 entities for this session" in one call) or
  only summarize entities that *changed* this session.
- German vs English: transcripts are German. Keep graph content German (matches reports/wiki)
  — confirm the wiki target language before adding any translation step.
- Whether `seq` (chronological index) should come from pnp-report's `S<NN>` numbering
  instead of derived date order, if/when reports become a cross-check.
