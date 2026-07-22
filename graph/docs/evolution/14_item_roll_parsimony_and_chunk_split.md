# WP14 — Item/Roll parsimony & the :Chunk label split (2026-07-12)

> Realizes the Item/Roll half of WP12's parsimony goal and fixes the one
> labeling mistake in WP13.5. Schema-breaking (re-ingest required). Measured
> against the live 2-session flagship graph (374 nodes: RollEvent 59, Item 26,
> **Chunk 169 = 45 %**, MENTIONS 1712 = 79 % of edges).

## Problem

Two node classes flooded the graph with detail that belongs in the vector
"book", not the macro-skeleton:

1. **RollEvent (59 nodes, 27 %)** — every dice roll minted a node + `ROLLED`/
   `TARGETS`/`IN_SESSION` edges. Rolls are irrelevant to the narrative
   topology; the raw roll data already exists as `pnp-report/roles/
   Session_Report_S<NN>_Rolls.csv`.
2. **Item (26 nodes, 12 %)** — generic loot (`Fackel`, `Heiltrank`, `Krug`,
   `Säcke voll Gold`) minted alongside plot artifacts. `KG_Qualitaetsanalyse_S01`
   already flagged this ("Item nur bei Besitz-/Verwendungs-Relevanz über die
   Szene hinaus") but no gate enforced it.
3. **Chunk passages (169 nodes, 45 %)** — WP13.5's vector "book" was correct in
   concept but stamped `:Entity`, so every skeleton query (`MATCH (n:Entity)`),
   QA algorithm, and the Neo4j Browser drowned in passages. A *labeling* bug,
   not a storage-location one.

## Decisions (confirmed with Tino)

- **Item = named/unique artifacts only.** Generic items → dropped entirely (they
  remain in the vector store). No `inventory_notes` property.
- **RollEvent removed from the graph pipeline entirely.** Roll *stats* are a
  separate future concern (a dedicated LLM call + its own store); out of scope
  here, and the roll CSVs already hold the raw data.
- **Passages become their own `:Chunk` label** with a dedicated vector index —
  single Neo4j DB, not a separate vector store (over-engineering at this scale;
  the native index + `MENTIONS` join is the 2026 GraphRAG-standard shape).

## Changes

### Item Option A (`schema.py`, `extract.py`, `resolve.py`)
- `Item.is_named_artifact: bool` — **required** (no default) → grammar-forced
  per item, the same "pay to mint" mechanism as `Event.
  narrative_significance_reasoning`.
- Prompt gains an explicit rule + negatives (`Fackel`/gold/potion = false;
  `Schwert des Veritas` = true).
- `resolve_graph` items loop: `if not item.is_named_artifact: continue` — a
  generic item is never minted, never an edge.

### RollEvent removal
- `schema.py`: `RollEvent` class + `roll_events` deleted from `SceneExtraction`
  and `GraphExtraction`.
- `extract.py`: roll bullet + `ROLLED` predicate hint dropped from the prompt;
  `roll_events` gone from `extract_chunk`, `merge_graphs`, `_record_evidence`.
- `resolve.py`: the roll loop deleted. The `_ROLL_TITLE_RE` **event-gate drop
  stays** — a roll-titled macro-Event is still dropped (now it goes nowhere,
  which is correct; the detail lives in the vector store).
- `config.py`: `ROLLED` out of `ALLOWED_PREDICATES`/`EVENT_PREDICATES`/
  `PREDICATE_DOMAINS`; `RollEvent` removed from the `IN_SESSION`/`TARGETS`/
  `RESULTED_IN`/`MENTIONS` domain sets.
- `store.py`: `timeline_unlinked` QA now `n.type IN ['Event','Decision']`.

### :Chunk label split (the 2026 GraphRAG-standard shape)
```
(:Entity)                    ← skeleton: characters, locations, events, quests, ...
(:Chunk {text, embedding})   ← the "book": raw passages, OWN vector index
(:Chunk)-[:MENTIONS]->(:Entity)   ← the join, unchanged
```
- `store.py`: `chunk_id` uniqueness constraint; `_write_graph` MERGEs
  `type=="Chunk"` as `:Chunk`, else `:Entity`; **edge endpoints MATCH
  label-less** (`MATCH (a {id}), (b {id})`) so a `MENTIONS`/`IN_SESSION` edge
  joins a `:Chunk` start to an `:Entity` end. Both labels carry a unique-id
  constraint.
- `embed.py`: two vector indexes — `entity_embedding FOR (:Entity)` and
  `chunk_embedding FOR (:Chunk)`; the embed pass matches `(n:Entity OR n:Chunk)`.
- `retrieve.py`: seeds merged from **both** indexes by cosine score; expansion
  matches both labels so the hybrid Chunk↔Entity join is unchanged. A `:Chunk`
  seed still renders its verbatim passage.

## Result (targets vs. the 2-session baseline)

| Class | Before | After |
|---|---|---|
| RollEvent nodes | 59 | **0** |
| Item nodes | 26 (mostly generic) | **only named artifacts** (5 in the first re-ingest) |
| Passages on `:Entity` | 169 | **0** — moved to `:Chunk` |
| `MATCH (n:Entity)` browser view | buried under 45 % passages | **pure macro-skeleton** |

## Migration

Schema break **and** a label change → the old `:Entity{type:'Chunk'}` nodes
would duplicate under `:Chunk` (different label, same id). **Wipe, don't just
re-ingest:**
```bash
python -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687',auth=None); d.session().run('MATCH (n) DETACH DELETE n')"
PNP_PROFILE=flagship python -m pnp_graph.cli ingest --only 2025-04-01
PNP_PROFILE=flagship python -m pnp_graph.cli ingest --only 2025-04-09
```

## Verification

- `python -m pytest tests/` (offline) green — golden regenerated (RollEvent gone
  from the fixture, `Item(is_named_artifact=True)`); new `test_generic_item_not_minted`.
- Post re-ingest: `MATCH (n:Entity{type:'RollEvent'}) RETURN count(n)` → 0;
  `MATCH (n:Item) RETURN n.name` → only named artifacts; `MATCH (n:Chunk) RETURN
  count(n)` holds the passages; `cli ask` still answers from Chunk passages.
