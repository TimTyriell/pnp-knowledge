# 03 — Entity Resolution & Canonical IDs (the #1 fix, WP1)

This is the gate. Cross-session versioning, dedup, provenance, and report reconciliation all depend on it. **Do this first.**

## Root cause (recap)

`store.py` merges on raw `name`, so `Marco` / `Dodo` / `Marco (Dodo)` become three nodes. Graph 2 had 15 `Character` nodes for ~5 real people. Graph 3 solved this with deterministic ids + aliases. We replicate that on the local pipeline.

## New module: `src/pnp_graph/resolve.py`

Inserts a resolution stage **between** `extract_session` and `write_session`: `extract → resolve → (srd-link) → store`.

### ID scheme (deterministic, human-readable)

`CHAR_{Slug}` (PC/NPC/GM), `COMP_{Slug}` (companion), `RULE_{SUBTYPE}_{Slug}`, `QUEST_{Slug}`, `ITEM_{Slug}`, `LOC_{Slug}`, `FACTION_{Slug}`, `EVT_{Slug}`, `DEC_{Slug}`, `ROLL_{Slug}`, `SCENE_{session}_{Snn}`, `SESS_{date}`.

`slug()` = transliterate → strip → snake_case. Fold German so surface variants collapse: ß→ss, ä/ö/ü folded, drop a leading article (`der/die/das`), strip parenthetical player tags (`Marco (Dodo)` → `Marco`). So `Schleichfurz`, `Schleichfurz `, `der Schleichfurz` map to one id.

### Alias registry — `data/alias_registry.json` (campaign-persistent, editable)

> **Important:** Players and characters are **separate nodes** (see `09_player_character_mapping.md`). Player names resolve to `PLAYER_*` ids; character names resolve to `CHAR_*` ids. Do **not** fold a player name into a character's aliases. The registry has two sections:

```json
{ "players": {
    "PLAYER_Tim":  {"canonical":"Tim",  "aliases":["Tim (Spieler)"]},
    "PLAYER_Marco":{"canonical":"Marco","aliases":["Marco (Spieler)"]},
    "PLAYER_Celin":{"canonical":"Celin","aliases":["Celin (Spieler)"]},
    "PLAYER_Deniz":{"canonical":"Deniz","role":"GM","aliases":["GM","Dwarf Masters Host"]} },
  "characters": {
    "CHAR_LindoLaut":   {"canonical":"Lindo Laut","aliases":["Lindo"]},
    "CHAR_Marco_Dodo":  {"canonical":"Dodo","aliases":["Goblin-Dragonborn"]},
    "CHAR_Celin_Cookie":{"canonical":"Cookie","aliases":[]},
    "CHAR_Deniz_GM":    {"canonical":"Deniz (GM)","is_pc":false,"role":"GM","aliases":["GM-Narrator"]} } }
```

The **player↔character link is not stored here** — it's the per-session `PLAYS` edge, parsed from the transcript's `Player (Character)` speaker labels (`09`). Both the player and character alias entries above can be **auto-bootstrapped** from those labels on first sighting.

### Resolver: `resolve_name(surface, type_hint) -> id`

1. **Exact alias hit** in the registry → return its id.
2. **Normalized hit** (casefold, strip punctuation/parenthetical, fold umlauts) → return id.
3. **Fuzzy** (`rapidfuzz`, score ≥ ~90) **within the same `type`** → accept, **log** the match for review.
4. **Below threshold** → mint a new id, append the surface form to the registry (write-back), **log** as "new entity — review."

Never auto-merge across types. Ambiguous/low-confidence matches are logged, not silently merged (this is PLAN.md safety-net #4, done properly and keyed on `id`).

### Player vs character (do NOT fold them)

Players and characters are **separate nodes** joined by a per-session `PLAYS` edge parsed from the transcript labels — full design in `09_player_character_mapping.md`. In `resolve.py`, phase 1 resolves a surface form to **either** a `Player` (`PLAYER_*`) **or** a `Character` (`CHAR_*`); a later attribution phase (`09`) re-routes in-fiction actions from the acting player to their **active character**. Mirror resolved aliases onto each node's `aliases[]` prop, but keep player aliases and character aliases in their own namespaces.

### Endpoint validation (safety-net #5)

Every relationship's `subject`/`object` is resolved to an id **before** the write. If an endpoint doesn't resolve to an entity produced this session (or an SRD/pre-existing id), **drop the edge and log it** to `state/failures/<sid>/dropped_edges.jsonl` — never MERGE-create a phantom node.

## `store.py` changes

- Replace all `MERGE (X {name})` with `MERGE (n:Entity {id})` (see `02`).
- Relationship endpoints: `MATCH (a:Entity{id:$sid_a}),(b:Entity{id:$sid_b})` — never `{name}`.
- Replace the `character_name/location_name/faction_name` constraints with a single `entity_id` uniqueness constraint (see `07`).

## Acceptance (WP1 done when)

- Re-ingesting `2025-03-26` yields **exactly one** node each for Lindo Laut, Dodo, Cookie, Deniz (was 15 Character nodes for ~5 people).
- Duplicate-name QA query and cross-type-name QA query (see `07`) both return empty.
- `entity_id` uniqueness constraint is live; unresolved endpoints appear in the dropped-edges log, not as phantom nodes.
