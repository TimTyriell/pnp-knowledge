# 07 — Neo4j Constraints, QA & Report Cross-check (WP8)

## Constraints & indexes (id-based)

```cypher
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE;
CREATE INDEX entity_type    IF NOT EXISTS FOR (n:Entity) ON (n.type);
CREATE INDEX entity_session IF NOT EXISTS FOR (n:Entity) ON (n.session_id);
```
**Retire** the `character_name` / `location_name` / `faction_name` uniqueness constraints in `store.py:ensure_constraints` — they enforce the wrong key and will fight canonical ids.

## QA queries the pipeline runs each ingest

Run these after `write_session` and record the results in `ingest_log.jsonl` (extend the existing record). Any non-empty "must be empty" result is a release blocker.

```cypher
-- 1. Duplicates after resolution — MUST be empty
MATCH (a:Entity),(b:Entity)
WHERE a.id < b.id AND toLower(a.name) = toLower(b.name)
RETURN a.id, b.id, a.name;

-- 2. Same name across two types (the Daggerheart Location+Faction bug) — MUST be empty
MATCH (a:Entity),(b:Entity)
WHERE a.name = b.name AND a.type <> b.type
RETURN a.name, collect(DISTINCT a.type);

-- 3. Facts without provenance — MUST be 0
MATCH ()-[r]->() WHERE r.confidence IS NULL OR r.session_id IS NULL RETURN count(r);

-- 4. Rules consistency: a used Domain Card outside the PC's class domains
MATCH (pc:Entity{type:'Character'})-[:USES_CARD]->(c:Entity{subtype:'DomainCard'})
MATCH (pc)-[:HAS_CLASS]->(cl:Entity{subtype:'Class'})
WHERE NOT c.domain IN cl.domains
RETURN pc.name, c.name, c.domain, cl.domains;

-- 5. Timeline: every Event/Roll/Decision links to a Scene — MUST be empty
MATCH (n:Entity) WHERE n.type IN ['Event','RollEvent','Decision']
  AND NOT (n)-[:EVIDENCED_IN]->(:Entity{type:'Scene'})
RETURN n.id;

-- 6. Orphan nodes (0 relationships) — should be ~0 except the SRD library
MATCH (n:Entity) WHERE NOT (n)--() RETURN n.id, n.type;
```

## `reconcile-report` — the gold cross-check (WP8)

Because the local pipeline now emits the same `:Entity{id,type}` shape as `reports/load_report_graph.py`, the occasional Claude-authored report becomes a **continuous evaluation signal** instead of a separate silo.

Add `python -m pnp_graph.cli reconcile-report <session>`:
1. Load the report graph for that session (reuse `reports/load_report_graph.py` logic; it reads the trailing ```json``` block of `Session_Report_S*_<date>.md`).
2. Diff it against the local graph for the same `session_id` and report:
   - **Recall gaps** — entities/edges the report has that the local run missed.
   - **ID mismatches** — same entity, different id ⇒ an **alias-registry hole**; emit a suggested `alias_registry.json` addition.
   - **Confidence disagreements** — where report and local disagree on a shared edge.
3. Output a short reconciliation report (and optionally auto-append high-confidence alias suggestions for human approval — never silently).

This turns your best but expensive asset (the hand-authored report) into a cheap, repeatable QA harness for the local pipeline, and it self-heals the alias registry over time.

**Acceptance:** `reconcile-report 2025-03-26` runs, prints recall gaps + id mismatches, and proposes alias-registry additions.
