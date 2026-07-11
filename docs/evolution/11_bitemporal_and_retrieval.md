# 11 — Bitemporal Edge Lifecycle & GraphRAG-style Retrieval (WP9 / WP11)

Concretizes `PLAN.md` phase 3 (append/version) into an implementable edge contract, adds the death workflow, and specifies the **retrieval layer** that makes the graph LLM-readable ("local search"). Also records the framework decision: **we do NOT adopt microsoft/graphrag as the pipeline** — see the verdict at the end.

## Premise (from the campaign owner)

Transcripts are speaker-labeled and **numbered**; newer transcripts are more current/correct than older ones. Narrative development (relationships, deaths, state changes) must stay traceable over time **without deleting history**. Contradictions are never silently resolved: the newer fact becomes current, the older one remains as a historical fact with its own validity window.

## Two time axes (this is what makes it bitemporal)

| Axis | Property | Meaning |
|---|---|---|
| **Valid time** (in-world) | `valid_from` / `valid_to` (Session `seq`, integer) | When the fact was true in the story. `valid_to IS NULL` = currently true. |
| **Knowledge time** (source) | `session_id` (+ `evidence_scenes[]`) | Which transcript we learned it from. Already mandatory per `04`. |

Keeping both axes separate is what lets a **later transcript correct earlier story-time**: "he was actually dead since session 3" becomes `valid_from: 3` with `session_id: "2025-06-11"` — the graph remembers both when it was true *and* when you found out. `seq` is the ordering integer (`ingest.py` already enumerates sessions oldest→newest); `session_id` (the date) stays the stable identifier. If transcripts get explicit numbers in filenames later, `seq` simply adopts them.

## State edges vs. event edges — NOT all edges get a lifecycle

The original proposal said "on change/death, close the edge with `valid_to`" for all edges. That's wrong for half the catalog: **an event that happened never stops having happened.** Classify every predicate once, in `config.py`, alongside `ALLOWED_PREDICATES`:

- **State edges** (a condition that holds until it changes) → full `valid_from`/`valid_to` lifecycle:
  `ALLIED_WITH, HOSTILE_TO, TRUSTS, MEMBER_OF, LOCATED_IN, AT_LOCATION, OWNS, OWNED_BY, KNOWS, FEARS, HAS_CLASS, HAS_SUBCLASS, USES_CARD, PLAYS` *(PLAYS is already per-session per `09` — its "lifecycle" is the per-session edge itself)*
- **Event edges** (a happening, timestamped, immutable — `valid_to` is meaningless) →
  `KILLED, BETRAYED, PARTICIPATED_IN, TRIGGERED, RESULTED_IN, ROLLED, TARGETS, DECIDED, MENTIONED_IN, APPEARS_IN, IN_SESSION, EVIDENCED_IN`
- **Identity edges** (facts about who someone is — survive death) →
  `FAMILY_OF, HAS_ANCESTRY, HAS_COMMUNITY`

New predicates from this plan merged into `ALLOWED_PREDICATES` (`04`): `TRUSTS`, `BETRAYED`, `KILLED`, `FAMILY_OF` (use this instead of a vague `RELATED_TO` — `RELATES_TO` already exists as the explicit *fallback*, don't add a near-duplicate).

## The edge contract (final, supersedes the property list in `04` where they differ)

Every edge carries: `session_id` (source transcript), `evidence_scenes[]`, `confidence ∈ {high, medium, low}` — where **explicit ≈ high, inferred ≈ medium/low**; the explicit/inferred distinction is already encoded in this scale (see `schema.py`'s field description), don't introduce a second axis — plus `description` (**new**: free-text nuance the predicate can't carry, e.g. *"vertraut ihm nur widerwillig, seit dem Vorfall im Wald"*), and, **for state edges only**: `valid_from` (int `seq`), `valid_to` (int `seq` or `NULL`).

**Change workflow (append-only, never delete):**
```cypher
// A state changed in session $seq: close the old edge, open the new one
MATCH (a:Entity{id:$a})-[r:TRUSTS]->(b:Entity{id:$b})
WHERE r.valid_to IS NULL
SET r.valid_to = $seq;
// then MERGE the successor edge with valid_from = $seq (store.py edge writer)
```
The old edge stays queryable forever; "as of session N" = `valid_from <= N AND (valid_to IS NULL OR valid_to > N)`.

## Death workflow

On a Character's death in session `seq`:
1. Node: `status: "deceased"` (never delete; add `died_in_session: seq`). Node property history itself lands with PLAN.md's `:Fact` mechanism later — until then, `status` + `died_in_session` is enough.
2. Close **state edges only** (`valid_to = seq`): ownership, location, memberships, trust/alliances.
3. **Do not touch** event edges (their `KILLED`/`PARTICIPATED_IN` history is the interesting part) or identity edges (kinship doesn't end at death).
4. The player's next character is handled entirely by `09` — the next session's speaker labels produce a new `PLAYS` edge; nothing special to do here.

Character node property additions (extends the `02` ontology table): `status ∈ {alive, deceased, unknown, erwaehnt}`, `first_seen_session` (int), `last_updated_session` (int), optional `died_in_session`.

## Retrieval layer — GraphRAG-style "local search" WITHOUT adopting GraphRAG (WP11)

Goal: make the graph **LLM-readable** for Q&A ("Wer vertraut wem gerade? Was ist mit X passiert?"). This is ~a small module over Neo4j + Ollama embeddings, not a framework:

1. **Embed entities** with `nomic-embed-text` (Ollama, ~0.3 GB — co-resides with the LLM, no VRAM issue). Text per entity: `name + aliases + type + latest description/summary + Trait names`. Store the vector on the node; index with Neo4j's native vector index (**requires Neo4j ≥ 5.13 — check/pin the image version in `docker-compose.yml`**). Re-embed only entities touched by the current ingest.
2. **Query flow** (`retrieve.py` + `cli ask "..."`): embed the question → top-k entities via vector index → expand 1–2 hops, **filtered to `valid_to IS NULL`** (or "as of session N" for historical questions) and excluding `Scene`/`Session` backbone (`10`) → assemble a compact context block (entities with status, current state edges with `description`, recent Events, `Trait` counts) → answer with the local LLM, citing `session_id`s.
3. **Temporal questions come free**: "Wie war das Verhältnis in Session 5?" is just the as-of filter — this is the payoff of the bitemporal contract, and it's a query GraphRAG's local search cannot do.
4. **No community detection / global search** — correct call on 12 GB (thousands of extra LLM calls). The cheap substitute for "global" questions is PLAN.md phase 4's **per-session summaries**: retrieve summaries instead of graph neighborhoods when the question is broad.

## Framework verdict: microsoft/graphrag (local-ollama fork) — do NOT swap the pipeline

Considered and rejected as the extraction/storage engine, for reasons that follow directly from this repo's own evidence:

1. **Its extractor is free-form.** GraphRAG's entity/relation prompts produce an open vocabulary with no canonical IDs and no fixed ontology — that is *Graph 1 (`aikg1`) again*, the approach the three-graph comparison already showed fails at scale (199 predicates, duplicate entities). Bending it to closed vocab + `resolve.py`-style canonical IDs means rewriting its prompts and post-processing — more work than keeping `pnp_graph`, which already has structured output against a Pydantic schema.
2. **Wrong storage model.** GraphRAG is parquet/vector-store-centric; Neo4j is not its native sink. The bitemporal edge contract above (per-edge `valid_from/valid_to`, close-and-append) has no home in its data model at all.
3. **Its unique value is the part explicitly not wanted.** Community detection + global search is what GraphRAG adds over a plain KG; on this hardware it's off the table. What remains — local search — is the small retrieval module specified above.
4. **The fork lags upstream** (TheAiSingularity/graphrag-local-ollama), adding maintenance risk for zero retained benefit.

**What to keep from the GraphRAG idea:** the *retrieval pattern* (WP11 above) and `nomic-embed-text`. **Optional experiment:** the repo already has an A/B harness (`compare/run_both.py`, third Neo4j sink pattern established) — if evidence is wanted, wire graphrag-local-ollama in as a *third contender* on one session and compare its output against the evolved pipeline the same way `aikg1` was compared. Decide on data, not vibes; but don't build on it.

## LLM sizing note (7–9B vs 14B)

The plan mentions Qwen 7–9B Q4/Q5. `qwen3:14b` Q4 (~9 GB + KV at `NUM_CTX=8192`) fits the 4070 Ti alongside `nomic-embed-text`, and extraction/embedding run serially anyway — so the 12 GB budget does **not** force the downshift. Recommendation: keep `qwen3:14b` as the extraction default (structured-output reliability drops noticeably at 7–9B; the two-pass split in `06` becomes load-bearing), use `qwen3:8b` as the speed/VRAM fallback (already documented in `CLAUDE.md`), and revisit only if latency actually hurts. The retry/repair net (`06`) matters more at smaller sizes — implement it before any downshift.

## Roadmap placement

- **WP9 (existing, now concrete):** implement the state/event/identity classification, the edge contract, the change workflow, and the death workflow. Acceptance: a contradicting fact in a later session closes the old state edge (`valid_to` set) and opens a new one; an "as of session N" query returns the old truth for old N and the new truth for current; a character death closes exactly the state edges and nothing else.
- **WP11 (new, after WP9):** `retrieve.py` + `cli ask`, Neo4j vector index, entity embeddings, as-of retrieval. Acceptance: "Wer besitzt aktuell X?", "Was geschah mit Y in Session 3?" and a relationship-history question all answer correctly with session citations on the two-session test corpus.
