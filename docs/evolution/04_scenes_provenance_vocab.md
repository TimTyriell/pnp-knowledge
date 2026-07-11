# 04 — Scenes, Provenance & Closed Vocabulary (WP2–WP4)

Three tightly-related concerns. Provenance and vocab (WP2/WP3) are quick; scenes (WP4) add the temporal layer.

## Provenance on every fact (WP2)

Currently only relationships carry `confidence`/`evidence_chunk`/`session_id`; nodes carry nothing. Change:

- Add `confidence ∈ {high,medium,low}`, `session_id`, `evidence_chunks[]` to **all** node writes in `store.py`. No node or edge enters without provenance.
- **Normalize confidence to English** at the boundary. The report uses German (`hoch/mittel`); the local prompt should emit English. Add a map `{"hoch":"high","mittel":"medium","niedrig":"low"}` so mixed inputs converge — this was a real Graph 2-vs-3 discrepancy.

**Acceptance:** QA query for edges/nodes missing `confidence` or `session_id` returns 0; no German confidence tokens in the graph.

## Closed relationship vocabulary (WP3)

Promote `SUGGESTED_PREDICATES` from a hint to an enforced allow-list in `config.py`:

```python
ALLOWED_PREDICATES = {
  "IN_SESSION","APPEARS_IN","MEMBER_OF","OWNS","OWNED_BY","LOCATED_IN","AT_LOCATION",
  "HAS_CLASS","HAS_SUBCLASS","HAS_ANCESTRY","HAS_COMMUNITY","USES_CARD","HAS_FEATURE","RUNS","USES",
  "PARTICIPATED_IN","DECIDED","ROLLED","TARGETS","TRIGGERED","RESULTED_IN","INVOLVES","MENTIONED_IN",
  "KNOWS","FEARS","HOSTILE_TO","ALLIED_WITH",
  "TRUSTS","BETRAYED","KILLED","FAMILY_OF",   # narrative-arc verbs (see 11); FAMILY_OF replaces a vague RELATED_TO
}
PREDICATE_SYNONYMS = {"ALLY_OF":"ALLIED_WITH","HOSTILE":"HOSTILE_TO","OWNED":"OWNED_BY",
                      "RELATED_TO":"FAMILY_OF"}  # RELATES_TO stays the generic fallback — don't confuse the two
```

Enforcement in `resolve.py`/`store.py`: map through `PREDICATE_SYNONYMS`; anything still off-list → coerce to `RELATES_TO` **and log** for vocab review (drift stays visible, never sprawls to Graph 1's 199 types). Optionally tighten `schema.py:Relationship.predicate` to a `Literal[...]` once the vocab is stable.

**Acceptance:** every relationship type in the graph ∈ `ALLOWED_PREDICATES` (or a logged `RELATES_TO`); no predicate sprawl.

> **Edge property contract:** the full per-edge contract (incl. `description` free-text and the `valid_from`/`valid_to` lifecycle for *state* edges) now lives in `11_bitemporal_and_retrieval.md` — it supersedes this doc where they differ. Every predicate is classified once (state / event / identity) in `config.py` next to `ALLOWED_PREDICATES`.

## Scenes as first-class nodes (WP4) — shipped, then reverted

**Superseded (2026-07-11):** v1 (1 scene = 1 chunk) shipped and ran for real
sessions; measured result matched the "node-type imbalance" risk flagged below
almost exactly — ~50% of all edges in the live graph were `Scene` plumbing
(`EVIDENCED_IN` + `IN_SESSION`), while the property array below already
carried the same provenance. Verdict: v1 scenes were pure redundancy with zero
unique signal, and v2 (LLM scene-merging) was never built. Removed entirely —
`scenes.py` deleted, `Scene`/`EVIDENCED_IN` no longer written. Provenance now
lives only as a plain `evidence_chunks: [int]` property on the fact itself (no
node, no edge). If a real narrative timeline is wanted later, that's the v2
LLM-merge design below, done properly — not v1 revived.

The rest of this section is kept as the original design rationale.

Graph 3 references scenes `S01–S07`; Graph 2 has only chunk indices. Bridge them.

- **Segmentation** — new `src/pnp_graph/scenes.py`. v1 (deterministic, quick to ship): **1 scene ≈ 1 chunk**, `Snn = chunk_index`. v2 (**recommended default — see backbone sizing below**): one cheap `qwen` pass over chunk summaries to merge chunks into ~5–10 labeled scenes, matching report granularity.

  **Backbone sizing — why v2, not v1, is the real default.** Measured against the actual sample transcript (33.1 real minutes, 157 segments): `chunking.load_session_chunks` produces **32 raw chunks**. Projected across a 100-hour campaign at that density:
  - **v1 (1 scene = 1 chunk):** ~0.97 chunks/min × 6000 min → **~5,800 `Scene` nodes** campaign-wide. That's the same order of magnitude as the *entire* projected edge count (§`08`'s ~37–49k edges), meaning `Scene` would become a dominant fraction of all nodes in the graph — mostly structural backbone, not content.
  - **v2 (merged, ~8 scenes per 33 min, report-matching):** ~0.24 scenes/min × 6000 min → **~1,450 `Scene` nodes** campaign-wide. Proportionate, and the growth is *linear in campaign duration*, not in how much happened — fundamentally different from the `Trait`/`Event` reinforcement problem in `10`, where growth was proportional to how often something recurred. Scene growth is bounded and predictable; that's fine on its own. The problem v1 creates is **node-type imbalance and query/visualization clutter** (see the two fixes below), not runtime scale — Neo4j handles either count trivially.
  - **Recommendation:** ship v1 only as a quick internal check on one session; **implement v2 before this lands in the main pipeline.** Make the target scene density a `config.py` tunable (e.g. `TARGET_SCENE_MINUTES ≈ 4–5`) rather than hard-deriving 1:1 from `CHUNK_SIZE`, so backbone density can be dialed independently of extraction chunk size.
- **Nodes/edges:** emit `Scene{id:SCENE_{sid}_{Snn}, seq, session_id, summary}` and `(:Scene)-[:IN_SESSION]->(:Session)`.
- **Evidence migration — node-facts vs. relationship-facts are NOT symmetric:**
  Neo4j relationships cannot originate another relationship — an edge can only run between two **nodes**, so `(:fact)-[:EVIDENCED_IN]->(:Scene)` is only buildable when the fact itself is a node.
  - **Node-type facts** (`Event`, `RollEvent`, `Decision`, and newly-minted `Item`/`Location`/`Quest`/`Character` instances) → replace `evidence_chunk:int` with `evidence_scenes:[str]` **and** materialize the real `(:fact)-[:EVIDENCED_IN]->(:Scene)` edge. Keep both: the array for fast filtering, the edge for traversal.
  - **Relationship-type facts** (`OWNED_BY`, `TARGETS`, `MEMBER_OF`, …) → evidence stays as the `evidence_scenes:[str]` **property on the relationship only**. There is no separate `EVIDENCED_IN` edge for these — don't attempt to reify every relationship into a node just to attach one; that's a much bigger schema change nobody has asked for. If per-relationship scene traversal is ever needed, that's a deliberate future decision (reified `:Fact` nodes per PLAN.md's `:Fact` versioning idea), not a default here.
  - Wire the scene ids into `resolve.py`/`store.py` so every extracted fact (node or edge) gets stamped with the scene(s) its chunk belongs to.
- **Payoff:** timeline queries none of the three graphs support well — "replay session in order", "what did Cookie do in S06".
- **Edge-count consequence:** because `EVIDENCED_IN` only fires for node-facts, it adds roughly one edge per node-fact per session (tens, not hundreds) — it does not double the ~200 relationship-facts a session already has. See `08_roadmap.md` for a worked per-session edge-count projection.

**Acceptance:** `Scene` nodes exist with `seq`; every `Event`/`RollEvent`/`Decision` links to a `Scene` (timeline QA query in `07` returns empty); a "replay in order" query works.

> Note: `PLAN.md` open question — whether `seq` should follow the report's `S<NN>` numbering vs derived order. If you build v2 segmentation, align its numbering with the report so `reconcile-report` (see `07`) matches scenes 1:1.
