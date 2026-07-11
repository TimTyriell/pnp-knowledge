# 10 — Recurring Behavior vs. One-off Events: Avoiding Frequency-as-Importance

Read after `05` (Decision/RollEvent semantics) and before finishing `WP6`/`WP7` — this is a **guardrail on recall**, not a new recall target. Without it, WP7's recall lift will directly cause the problem this doc describes.

## The problem

Two different things currently get modeled identically — as "an `Event` node" — with no signal to tell them apart:

- **Recurring routine behavior:** Lindo Laut plays music in most sessions. If each occurrence mints a fresh `Event` (or `RollEvent`), ~130 sessions produces ~100+ near-identical nodes clustered around one Character. This is repetition, not information — but it *does* inflate that Character's degree/connectivity, so any naive "important entities" query (degree, PageRank, "most-connected node") will rank it above things that actually mattered.
- **A rare one-off:** the party meets a goblin who mentions carrots. This happens once, so it gets exactly one node — structurally indistinguishable from a one-off event that was genuinely pivotal (e.g. the campaign's climactic boss kill), and also indistinguishable from "background color."

**Root cause:** the schema conflates *evidential confidence* ("how sure are we this was said" — already captured) with *narrative significance* ("how much did this matter" — not captured anywhere), and it has no mechanism for collapsing repeated occurrences of the same routine behavior into one aggregated fact.

## Fix 1 — Aggregate recurring behavior into a counted `Trait`, don't repeat `Event` nodes

New node type: **`Trait`** — a recurring characterization/habit, not a discrete happening.

```
id: TRAIT_{CharacterSlug}_{Slug}      e.g. TRAIT_LindoLaut_Musik
type: "Trait"
name: "Spielt oft Musik"
```

Edge, `MERGE`-and-increment rather than created fresh each time:
```cypher
MATCH (c:Entity{id:$char_id})
MERGE (t:Entity{id:$trait_id}) ON CREATE SET t.type='Trait', t.name=$name
MERGE (c)-[k:KNOWN_FOR]->(t)
  ON CREATE SET k.count = 1, k.sessions = [$session_id], k.first_seen = $session_id, k.last_seen = $session_id
  ON MATCH  SET k.count = k.count + 1,
               k.sessions = apoc.coll.toSet(k.sessions + $session_id),
               k.last_seen = $session_id
```
One node, one edge, a growing counter and session list — instead of N nodes. The **recurrence itself becomes the signal** (`count`, `sessions.length`) rather than graph bloat. "Lindo Laut is known for music across 40 sessions" is one clean fact, immediately queryable, and it doesn't distort degree-based analytics.

## Fix 2 — Reserve `Event`/`RollEvent`/`Decision` nodes for occurrences with actual consequence

Extraction-time rule (add to the event-pass prompt in `extract.py`, per `06`):

> Only create a new `Event`/`RollEvent` for an occurrence if at least one is true: (a) a roll happened, (b) it changed a tracked state (HP, quest status, item ownership, relationship), (c) it caused or resulted from another Event/Decision (a real `TRIGGERED`/`RESULTED_IN` link exists), or (d) it's referenced again later in the same session. If it's ambient/flavor color with none of these — including a *repeat* of something already logged as a `Trait` — do not mint an Event; instead emit/reinforce the `Trait` (Fix 1).

This single filter is what keeps WP7's recall lift from becoming exactly the reinforcement problem this doc is about: **recall should increase for distinct, consequential facts, not for repeated instances of the same ambient behavior.**

## Fix 3 — Compute significance, don't ask the model to self-rate it

Do **not** add an LLM-asserted `importance`/`significance` field to `Event` — self-rated importance is unreliable and, worse, invites the model to inflate everything as important in the moment (the opposite of what you want). Instead, derive it **structurally at query time**, from graph shape that's already there:

```cypher
// "Significant" events: caused something, resulted from something, or involved a roll
MATCH (e:Entity{type:'Event'})
WHERE (e)-[:TRIGGERED|RESULTED_IN]->() OR ()-[:RESULTED_IN]->(e)
   OR (e)<-[:TARGETS]-(:Entity{type:'RollEvent'})
RETURN e;

// "Ambient/dangling" events: no causal edges either direction, never referenced again — candidates
// to have been better modeled as a Trait reinforcement, or safe to down-rank in downstream consumers
MATCH (e:Entity{type:'Event'})
WHERE NOT (e)-[:TRIGGERED|RESULTED_IN]-()
  AND NOT (e)<-[:MENTIONED_IN]-()
RETURN e.id, e.name, e.session_id;
```

This is cheap, always in sync with the graph (no separate field to keep updated), and it directly answers the question you asked: it lets you distinguish "the goblin/carrots aside — never referenced again, no consequence, low significance" from "the boss fight — triggered the quest resolution, high significance" even though both are single-occurrence `Event` nodes. Recurrence (`Trait.count`) and consequence (causal degree) are the two orthogonal signals; neither is "how many nodes exist for it."

## QA addition (extends `07`)

```cypher
-- Possible mis-modeled recurrence: near-identical Event names for the same Character,
-- recurring across sessions with no causal edges — should likely be a Trait, not repeated Events.
MATCH (c:Entity{type:'Character'})-[:PARTICIPATED_IN]->(e:Entity{type:'Event'})
WHERE NOT (e)-[:TRIGGERED|RESULTED_IN]-()
WITH c, e.name AS ename, count(DISTINCT e) AS occurrences, collect(e.id) AS ids
WHERE occurrences >= 3
RETURN c.name, ename, occurrences, ids;   -- review: convert to Trait aggregation (Fix 1)
```
Flag, don't auto-fix — a human/agent decides whether a repeating name is genuinely the same ambient habit (convert to `Trait`) or coincidentally similar wording for distinct events (leave as-is).

## What this does NOT change

- `confidence` stays exactly what it already is (evidential certainty) — it is not repurposed as significance.
- This doesn't prune or delete anything (still append-only per PLAN.md) — ambient Events that already exist can stay; the QA query just flags candidates for a one-time cleanup pass, and the extraction-time filter (Fix 2) prevents new ones from accumulating.
- Rare-but-unimportant one-offs (the goblin/carrots) are *fine* as single `Event` nodes — the point isn't to hide them, it's that the significance query now lets you (or the fandom-wiki consumer) tell them apart from what actually drove the story, on demand, without storing a subjective field.

## Roadmap placement

**WP6b — Trait aggregation + Event-minting filter**, immediately after WP6 (`Decision`/`RollEvent` extraction) and **before** WP7 (recall lift) — the filter must exist before recall is pushed up, or WP7 will amplify exactly the reinforcement problem this doc addresses. See `08_roadmap.md`.

**Acceptance:** re-ingesting a session with a known recurring flavor action (e.g. music) produces **one** `Trait` node with an incrementing `KNOWN_FOR.count`, not N `Event` nodes; the "possible mis-modeled recurrence" QA query returns empty on a clean re-ingest; the significance query correctly separates a known consequential Event (e.g. the boss defeat) from a known ambient one (e.g. the goblin/carrots aside) in the same session.
