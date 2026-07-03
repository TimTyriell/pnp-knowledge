# 02 — Target Architecture

## The decision

Converge the main pipeline onto a single canonical model: **`:Entity{id, type, ...}` with `MERGE` on `id`** — the same shape `reports/load_report_graph.py` already uses — but with **native, queryable properties** (no `attributes_json`) and the richer ontology below. This makes Graph 2 and Graph 3 directly comparable/mergeable and lets the report act as a gold reference.

Single Neo4j label `:Entity` on all nodes; the semantic class lives in a required `type` property (mirrors Graph 3). (`:Entity:Character` multi-label is acceptable if the team prefers — decide once, apply everywhere.)

## Node ontology (closed set)

| `type` | Meaning | Required props | Key optional props |
|---|---|---|---|
| `Player` | Real person at the table (permanent identity anchor) | `id, name, type` | `aliases[], role` (`GM` for the GM) |
| `Character` | PC / NPC / GM-narrator / companion / adversary-as-actor. **Receives all in-fiction edges** (see `09`) | `id, name, type, is_pc, role, session_id, confidence, evidence_scenes` | `aliases[], hp_max, damage_threshold_*` |
| `RuleEntity` | SRD object (Class/Subclass/Ancestry/Community/DomainCard/ClassFeature/Adversary/System) | `id, name, subtype, source, session_id, confidence, evidence_scenes` | `srd_ref, domains[]` |
| `Location` | a place | `id, name, session_id, confidence, evidence_scenes` | `description, parent_location_id` |
| `Item` | in-world object / loot | `id, name, status, session_id, confidence, evidence_scenes` | `owner_id, origin_scene, description` |
| `Quest` | objective/mission | `id, name, status, session_id, confidence, evidence_scenes` | `giver_id, description` |
| `Faction` | group (incl. the party) | `id, name, session_id, confidence, evidence_scenes` | `stance, description` |
| `Event` | story beat | `id, name, summary, session_id, confidence, evidence_scenes` | `outcome` |
| `RollEvent` | a dice roll + result | `id, name, session_id, confidence, evidence_scenes` | `roller_id, trait_or_action, outcome, target_id` |
| `Decision` | deliberate weighty choice | `id, name, session_id, confidence, evidence_scenes` | `decided_by_id, quote, consequence` |
| `Scene` | temporal unit (see `04`) | `id, seq, session_id, summary` | `title` |
| `Session` | a play session | `id, seq, date` | `title` |

The **`PLAYS`** relationship (`Player`→`Character`, **one per session**, parsed from the transcript's `Player (Character)` speaker labels) is central and specified in `09_player_character_mapping.md`.

Rules: model an adversary as a `Character{is_pc:false, role:"adversary"}` that `USES` a `RuleEntity{subtype:"Adversary"}` stat block. Game resources (Hope/Stress) are **not** Items. Never create nodes literally named `character`/`creature`/`item` (Graph 1 anti-pattern).

## Target module layout

```
src/pnp_graph/
  config.py    # + ALLOWED_PREDICATES, PREDICATE_SYNONYMS, SRD/registry paths, REPORT_NEO4J_URL
  schema.py    # + RuleEntity, RollEvent, Decision; provenance on all; is_pc/role
  chunking.py  # unchanged; feeds scenes
  scenes.py    # NEW: chunk→scene segmentation, Scene/Session builders
  srd.py       # NEW: load data/daggerheart_srd.json, preload RuleEntity, SRD alias map
  resolve.py   # NEW: canonical id minting, alias registry, endpoint + vocab validation
  extract.py   # two-pass prompts, retry/repair, evidence as scene ids
  store.py     # MERGE on id, native props, provenance on nodes + edges
  ingest.py    # chunks→scenes→extract→resolve→srd-link→store; file-hash resume
  cli.py       # + status, --dry-run, reconcile-report
data/
  alias_registry.json   daggerheart_srd.json
```

## `schema.py` sketch

`id` is **not** model-filled — it's minted in `resolve.py`. The model fills names/aliases; the resolver assigns ids and fills `evidence_scenes`.
```python
class Character(BaseModel):
    name: str; player: str | None = None
    is_pc: bool = True; role: str = "PC"          # PC | NPC | GM | adversary | companion
    aliases: list[str] = []                        # + optional native hp_max, damage_threshold_*
class RuleEntity(BaseModel):
    name: str; subtype: str; source: str = "daggerheart-srd"
    srd_ref: str = ""; domains: list[str] = []
class RollEvent(BaseModel):
    name: str; roller: str | None = None
    trait_or_action: str = ""; outcome: str = ""; target: str | None = None
    confidence: Literal["high","medium","low"] = "medium"
class Decision(BaseModel):
    name: str; decided_by: str | None = None
    quote: str = ""; consequence: str = ""
    confidence: Literal["high","medium","low"] = "medium"
# GraphExtraction gains: rule_entities, roll_events, decisions; provenance on all node models
```

## `store.py` sketch (MERGE on id, native props, provenance)

```python
def _write_entity(db, e):    # e = resolved dict: id/type/props/evidence_scenes
    db.run("""
      MERGE (n:Entity {id:$id})
        ON CREATE SET n += $props, n.type=$type, n.created_at=timestamp()
        ON MATCH  SET n += $props, n.type=$type, n.updated_at=timestamp()
      WITH n UNWIND $scenes AS sc
        MATCH (s:Entity{type:'Scene', id:sc}) MERGE (n)-[:EVIDENCED_IN]->(s)
    """, id=e["id"], type=e["type"], props=e["props"], scenes=e["evidence_scenes"])

def _write_edge(db, r, allowed):
    rtype = r["type"] if r["type"] in allowed else "RELATES_TO"
    db.run(f"""
      MATCH (a:Entity{{id:$s}}),(b:Entity{{id:$o}})
      MERGE (a)-[rel:`{rtype}`{{session_id:$sid}}]->(b)
        ON CREATE SET rel.confidence=$conf, rel.evidence_scenes=$scenes
        ON MATCH  SET rel.evidence_scenes=apoc.coll.toSet(coalesce(rel.evidence_scenes,[])+$scenes)
    """, s=r["start_id"], o=r["end_id"], sid=r["session_id"], conf=r["confidence"], scenes=r["evidence_scenes"])
```
Endpoints that don't resolve to an existing `id` are **not written** — log them (see `03`). Keep `sanitize_predicate` as the injection guard on the interpolated type.
