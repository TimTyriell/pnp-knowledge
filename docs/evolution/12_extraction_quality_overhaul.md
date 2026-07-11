# WP12 — Extraction Quality Overhaul (native parsimony & significance)

> **Priority 1.** Supersedes the recall-first tone of `06` and the aggregation
> design of `10` (WP6b) where they conflict. Written against the measured
> 2-session bloat in `../learnings/KG_Bloat_2Session_20250401-09.md`.

## Problem (one line)

The pipeline extracts everything the transcript says instead of only what is
narratively significant: 35 % of nodes are single-use `Trait`s, 33 % of `Event`s
are orphans, and **0 %** of `Event`s carry a consequence edge.

## Architectural decision

Downstream structural pruning (mint garbage, delete it with a script) is an
**anti-pattern** here. Parsimony is enforced *in the extraction layer*: the LLM
must "pay" to mint a node by proving its significance, is structurally forbidden
from minting `Trait` topology, and sees scene-level context so it can tell a
passing comment from a state change. A manually-triggered cleanup for legacy/
residual data is allowed; nothing prunes on the `ingest` hot path.

## Design invariant added

> **8. Significance is a schema obligation, not a downstream filter.** A node
> type that represents a discrete happening (`Event`) may only be minted with a
> filled-in justification and a typed consequence reference. Recurring
> characterization updates a property, never mints a node.

---

## Component 1 — Scene-level chunking

Micro-events come from ~250-token chunks (`KG_Qualitaetsanalyse_S01` §4). Raise
chunks to scene level so the model sees the narrative arc.

**`config.py`:**
```python
CHUNK_SIZE = 12000      # chars, ~3k token — was 4000 (~1k)
CHUNK_OVERLAP = 1500    # was 600
NUM_CTX = 16384         # was 8192 — MUST hold prompt(~600) + chunk(~3k) + output
NUM_PREDICT = 6144      # was 4096 — larger chunks -> longer JSON, avoid truncation
```
**`chunking.py`:** no code change — `pack_segments` is already parametric on
`CHUNK_SIZE` (`chunking.py:74`); the gap-aware break scales.

**Hard constraint:** `CHUNK_SIZE` is **chars**, not tokens. Scene-level tokens
force a `NUM_CTX` raise, which grows the KV cache on a 12 GB card. **Validate
VRAM first** (one 14B Q4 ~9 GB + 16k KV). OOM fallback: `NUM_CTX=12288`,
`CHUNK_SIZE=9000`. Recall risk (Q4 long-range degrades, `config.py:22`) is
guarded by `reconcile-report`, not assumed away.

## Component 2 — Schema-forced significance ("pay to mint")

Force the model to articulate consequence *before* it may write an `Event`, and
bake the consequence link into the node so the edge exists by construction.

**`schema.py`:**
```python
class EventConsequence(BaseModel):
    kind: Literal["roll", "target", "result"]   # -> ROLLED / TARGETS / RESULTED_IN
    ref: str = Field(description="Name of the roll/character/item/event the "
                     "consequence lands on — must be one of the entities listed")

class Event(BaseModel):
    title: str
    summary: str = ""
    participants: list[str] = []
    location: str | None = None
    state_change_justification: str = Field(     # REQUIRED (no default) = pay-to-mint
        description="The concrete consequence: HP/inventory/quest/relationship "
        "change, or a roll. If you cannot name one, this is NOT an event.")
    consequence: EventConsequence                # REQUIRED -> the edge is born with the event
```
Both fields have **no default** → `method="json_schema"` marks them `required` →
Ollama's grammar-constrained decoding forces them. This is the "attention as
filter" mechanism: the model can't emit the event without reasoning about its
consequence first.

**`resolve.py`** (event loop, `resolve.py:449-465`) builds the typed edge from
`e.consequence`:
```python
tgt = endpoint(e.consequence.ref)
if tgt:
    add_edge(eid, tgt, {"roll": "ROLLED", "target": "TARGETS",
                        "result": "RESULTED_IN"}[e.consequence.kind])
```
Every written `Event` carries a consequence edge by construction. **Honest
residue:** if `consequence.ref` doesn't resolve (hallucination / ASR), the edge
is absent — that single case goes to the manual cleanup, never a hot-path drop.

**Design tension to accept:** the strict consequence set excludes
`PARTICIPATED_IN`, yet 57 % of current events are combat/scene events whose only
in-fiction link is participants. Baking `consequence` in resolves this — a fight
event declares `kind:"target"` / `kind:"roll"` — but the prompt must make that
explicit or the model will leave weak events out (the intended behavior).

## Component 3 — Trait redesign (no new topology)

The WP6b count-aggregation premise is dead (`{1: 374}`). Remove `Trait` as a
node type; fold recurring behavior into a Character property.

- **`schema.py`:** delete `Trait`; drop `traits` from `EventExtraction` /
  `GraphExtraction`. Add to `Character`:
  ```python
  behavior_note: str = Field(default="", description="A recurring habit/"
      "characterization observed in THIS chunk, e.g. 'plays music often'. "
      "One short phrase or empty. NEVER a one-off action.")
  ```
- **`resolve.py`:** delete the trait loop (`resolve.py:529-554`); in the
  Character branch of `register`, union `behavior_note` into a `summary`
  property (same pattern as `aliases`/`evidence_chunks` in `add_entity`).
- **`config.py`:** remove `KNOWN_FOR` from `ALLOWED_PREDICATES` and
  `PREDICATE_DOMAINS`. **`store.py`:** remove the `KNOWN_FOR` block
  (`store.py:57-73`).

Result: −374 nodes at the source, behavior readable as a property. Not an
`attributes_json` blob — a single typed text field, invariant 3 holds.

*Optional heavier variant (only if a count is later needed):* feed the
character's existing `behavior_note`s into the prompt and increment a counter
property instead of appending text. Needs persistent per-character state in the
registry — defer until text-summary proves insufficient.

## Component 4 — Few-shot anti-patterns

**`extract.py`:** append real garbage titles from the export as labelled
negatives, and replace the trait instruction.
```python
_EVENT_ANTIPATTERNS = (
    "\nEXAMPLES OF WHAT IS *NOT* AN EVENT (no tangible consequence — do NOT extract):\n"
    "- WRONG: 'Dodo considers healing' — a thought, nothing changed.\n"
    "- WRONG: 'Esterossa refuses to walk through dirt due to honor' — flavor.\n"
    "- WRONG: 'Group discusses movement order' — meta/deliberation.\n"
    "CORRECT: 'Mage's Fireball hits Esterossa for 12 HP' — HP changed, roll happened; "
    "state_change_justification='Esterossa loses 12 HP', consequence={kind:'target', ref:'Esterossa'}.\n"
)
```
Replace the trait guidance (`extract.py:40-47`) with: *"Recurring habits go into
the character's `behavior_note`, never a separate node. One-off ambient actions
are extracted as nothing."*

---

## Migration / rollout

1. Wipe `:7687` (schema break: new `Event` fields, `Trait` gone).
2. Re-ingest `2025-04-01` + `2025-04-09` (the measured baselines).
3. Regenerate `tests/golden_resolved.json`; review the diff — only Trait/fluff
   events may disappear.
4. `tests/test_resolve.py` + `test_extract.py`: drop trait cases; add a
   consequence-edge case (Event with resolvable `consequence.ref` → typed edge;
   unresolvable → no edge, logged).
5. A/B chunk size (12000 vs 9000) against `reconcile-report` recall.

## Acceptance criteria (vs 2-session baseline: 346 events / 374 traits)

| Criterion | Baseline | Target |
|---|---|---|
| Event count | 346 | **≤ 104 (−70 %)** |
| Events with a consequence edge (`ROLLED`/`TARGETS`/`RESULTED_IN`) | **0 %** | **100 %** of written events |
| `Trait` nodes | 374 | **0** |
| Named Character/Location/Quest recall | — | **no regression** (`reconcile-report`) |

**New CI QA query** (`store.py::_QA_QUERIES`, a blocker) — measurement, not a prune:
```cypher
MATCH (e:Entity {type:'Event'})
WHERE NOT (e)-[:ROLLED|TARGETS|RESULTED_IN]-()
RETURN count(e) AS c   // must be 0; fails CI when extraction violates the contract
```

## Dependencies / risks
- **VRAM** gates Component 1 — validate before anything else.
- **Required `consequence`** can provoke a hallucinated `ref`; negatives +
  "ref must be a listed entity" damp it, residue → manual cleanup.
- **Recall regression** from big chunks is the counter-risk to parsimony;
  `reconcile-report` is the guard, not optional.

## Implementation order
Component 3 (trait removal) first — independent, −374 nodes, smallest diff.
Then 2 (schema significance), then 1 (chunks, needs the VRAM test), 4 alongside.
