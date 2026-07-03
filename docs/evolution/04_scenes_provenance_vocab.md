# 04 — Scenes, Provenance & Closed Vocabulary (WP2–WP4)

Three tightly-related concerns. Provenance and vocab (WP2/WP3) are quick; scenes (WP4) add the temporal layer.

## Provenance on every fact (WP2)

Currently only relationships carry `confidence`/`evidence_chunk`/`session_id`; nodes carry nothing. Change:

- Add `confidence ∈ {high,medium,low}`, `session_id`, `evidence_scenes[]` to **all** node writes in `store.py`. No node or edge enters without provenance.
- **Normalize confidence to English** at the boundary. The report uses German (`hoch/mittel`); the local prompt should emit English. Add a map `{"hoch":"high","mittel":"medium","niedrig":"low"}` so mixed inputs converge — this was a real Graph 2-vs-3 discrepancy.

**Acceptance:** QA query for edges/nodes missing `confidence` or `session_id` returns 0; no German confidence tokens in the graph.

## Closed relationship vocabulary (WP3)

Promote `SUGGESTED_PREDICATES` from a hint to an enforced allow-list in `config.py`:

```python
ALLOWED_PREDICATES = {
  "IN_SESSION","EVIDENCED_IN","APPEARS_IN","MEMBER_OF","OWNS","OWNED_BY","LOCATED_IN","AT_LOCATION",
  "HAS_CLASS","HAS_SUBCLASS","HAS_ANCESTRY","HAS_COMMUNITY","USES_CARD","HAS_FEATURE","RUNS","USES",
  "PARTICIPATED_IN","DECIDED","ROLLED","TARGETS","TRIGGERED","RESULTED_IN","INVOLVES","MENTIONED_IN",
  "KNOWS","FEARS","HOSTILE_TO","ALLIED_WITH",
}
PREDICATE_SYNONYMS = {"ALLY_OF":"ALLIED_WITH","HOSTILE":"HOSTILE_TO","OWNED":"OWNED_BY"}
```

Enforcement in `resolve.py`/`store.py`: map through `PREDICATE_SYNONYMS`; anything still off-list → coerce to `RELATES_TO` **and log** for vocab review (drift stays visible, never sprawls to Graph 1's 199 types). Optionally tighten `schema.py:Relationship.predicate` to a `Literal[...]` once the vocab is stable.

**Acceptance:** every relationship type in the graph ∈ `ALLOWED_PREDICATES` (or a logged `RELATES_TO`); no predicate sprawl.

## Scenes as first-class nodes (WP4)

Graph 3 references scenes `S01–S07`; Graph 2 has only chunk indices. Bridge them.

- **Segmentation** — new `src/pnp_graph/scenes.py`. v1 (deterministic, ship first): **1 scene ≈ 1 chunk**, `Snn = chunk_index`. v2 (optional, matches report granularity): one cheap `qwen` pass over chunk summaries to merge chunks into ~5–10 labeled scenes.
- **Nodes/edges:** emit `Scene{id:SCENE_{sid}_{Snn}, seq, session_id, summary}` and `(:Scene)-[:IN_SESSION]->(:Session)`.
- **Evidence migration:** replace `evidence_chunk:int` with `evidence_scenes:[str]` on nodes and edges, and materialize `(:fact)-[:EVIDENCED_IN]->(:Scene)`. Keep **both** the array (fast filter) and the edge (traversal). Wire the scene ids into `resolve.py`/`store.py` so every extracted fact gets stamped with the scene(s) its chunk belongs to.
- **Payoff:** timeline queries none of the three graphs support well — "replay session in order", "what did Cookie do in S06".

**Acceptance:** `Scene` nodes exist with `seq`; every `Event`/`RollEvent`/`Decision` links to a `Scene` (timeline QA query in `07` returns empty); a "replay in order" query works.

> Note: `PLAN.md` open question — whether `seq` should follow the report's `S<NN>` numbering vs derived order. If you build v2 segmentation, align its numbering with the report so `reconcile-report` (see `07`) matches scenes 1:1.
