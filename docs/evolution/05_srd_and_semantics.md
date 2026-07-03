# 05 — SRD Grounding & TTRPG Semantics (WP5–WP6)

These two work packages are where "more knowledge" becomes visible: the graph gains rules-awareness and captures how sessions actually generate meaning (choices + dice).

## SRD / RuleEntity grounding (WP5)

The biggest content upgrade over Graph 2, which has no rules layer at all.

### The asset — `data/daggerheart_srd.json`

A static, campaign-independent reference: canonical Classes, Subclasses, Ancestries, Communities, Domains, Domain Cards, Class Features, and common Adversaries. Each entry:
```json
{ "id":"RULE_CLASS_Bard", "name":"Bard", "subtype":"Class",
  "source":"daggerheart-srd", "srd_ref":"core", "domains":["Grace","Codex"] }
```
Seed from what's already in the three sample graphs — Bard/Troubadour, Guardian, Ranger/Beastbound, Faerie/Highborne, Ribbet/Ridgeborne, Inspiring Words, Rally, I Am Your Shield — and mark `TODO: complete from full SRD`. Confirm SRD licensing/source before bulk-importing (see assumptions in `08`).

### New module — `src/pnp_graph/srd.py`

- **Pre-load** all SRD entries as `RuleEntity` nodes (idempotent `MERGE` on id), independent of any session, before ingest.
- **SRD alias map** for fuzzy references (`"Fairy"→Faerie`, `"Frosch"→Ribbet`, `"Waldläufer"→Ranger`).
- During resolution (`03`), rules references **link to the existing SRD node by id** — never create a fresh per-session copy. This is what makes the rules layer accumulate cleanly across 100h.

### Adversary modeling

Model the monster as a `Character{is_pc:false, role:"adversary"}` (the story actor) that `USES` a `RuleEntity{subtype:"Adversary"}` (the stat block). Resolves Graph 3's blur where the monster existed only as a RuleEntity.

### Payoff — a real consistency check

Because play links to the rulebook, you can validate it (see `07` QA query 4): a Domain Card a PC `USES_CARD` should belong to a Domain their Class grants. Flags both data errors and genuine table mistakes.

**Acceptance:** `RuleEntity` library pre-loaded; PCs link to **shared** SRD ids (not per-session copies); rules-consistency query runs and is clean or flags real issues.

## Decision & RollEvent semantics (WP6)

Graph 2 captures none of these; they are the heart of TTRPG meaning and the source of Graph 3's traceable causal chains.

### Schema (already sketched in `02`)

Add `RollEvent` (roller, trait_or_action, outcome, target) and `Decision` (decided_by, quote, consequence) node models, plus `roll_events`/`decisions` lists on `GraphExtraction`.

### Extraction (prompt work — see `06`)

The event-pass prompt must actively elicit:
- **Rolls:** who rolled, what trait/action, the outcome (`success_with_fear`, `crit`, `failure`…), and the target.
- **Decisions:** weighty player/GM choices, with a short **verbatim `quote`** and the **`consequence`**.
- **Causal edges** connecting them: `DECIDED`, `ROLLED`, `TARGETS`, `TRIGGERED`, `RESULTED_IN`.

### Target

Reproduce a chain comparable to Graph 3's:
`Decision("Ritual bewusst falsch") —TRIGGERED→ Monster` … `Cookie —ROLLED→ RollEvent —TARGETS→ Monster —RESULTED_IN→ "Monster besiegt" —RESULTED_IN→ Loot`, and a new `Quest` triggered by the aftermath.

**Acceptance:** ingesting `2025-03-26` yields a traceable `Decision → … → Quest` causal chain of comparable shape to Graph 3.
