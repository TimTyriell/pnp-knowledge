# 09 — Player ↔ Character Mapping & Action Attribution

Read together with `03_entity_resolution.md` — this **corrects and extends** it. Players and characters are **separate nodes**; the link between them is **session-bound** (one mapping per player per session) and is **read directly from the transcript**, not curated or inferred with time windows.

## The mechanism is already in your data

The Whisper transcript encodes both identities in every segment's `speaker` label, in the form **`Player (Character)`**. Confirmed in `transcripts/2025-03-26_RF_ROCKGeeRUFw.json`:

```
"Tim (Lindo Laut)"   "Marco (Dodo)"   "Celin (Cookie)"   "Deniz (GM)"
```

So for each session you get the cast mapping for free by parsing the distinct speaker labels. There is **no** `from/to` validity window and **no** scene granularity — the atomic unit is the **session** (`video_date`, e.g. `2025-03-26`). If a player swaps characters, the next session's labels simply say so (`Tim (Grendel)`), and the mapping for that session changes automatically.

> This is also the root cause of Graph 2's duplicate people: `chunking.format_turn` prints the raw label `Tim (Lindo Laut):` into the chunk, so the model coined `Tim`, `Lindo Laut`, **and** `Tim (Lindo Laut)` as separate entities. Parsing the label structurally (below) fixes attribution *and* removes that duplication at the source.

## Two node types + a per-session control edge

| type | id | Role |
|---|---|---|
| `Player` | `PLAYER_Tim` | Real person. Permanent identity anchor. Holds real name, `PLAYS` history, out-of-character/meta facts. |
| `Character` | `CHAR_LindoLaut` | In-fiction PC (also NPC / adversary / companion). **Receives all in-fiction edges.** |

```
(:Player)-[:PLAYS {session_id, seq}]->(:Character)     # one edge per player per session
```
- One `PLAYS` edge **per player per session**, stamped with `session_id` (+ chronological `seq`).
- **Current character** of a player = the `PLAYS` edge with the highest `seq` (latest session).
- **Character swap** = a different mapping appears in a later session. Nothing to close or rewrite — the per-session edges *are* the history. (This is still append-only and "as of session N"-queryable, consistent with PLAN.md phase 3, just keyed on session rather than a validity range.)

## Source of truth: the transcript (with an optional override)

- **Primary:** parse the per-session `Player (Character)` labels. This is authoritative and requires no manual upkeep.
- **Optional override:** `data/cast_overrides.json` only for fixing mislabels or diarization typos (e.g. a session where a label is malformed). Never required in the happy path.
- **Bootstrap the alias registry from labels:** on first sight of `Tim (Lindo Laut)`, auto-create `PLAYER_Tim` + `CHAR_LindoLaut` + the `PLAYS` edge, and seed their alias lists (`Tim` under the player, `Lindo Laut` under the character). This means `03`'s `alias_registry.json` is largely self-populating.

## Speaker parsing + attribution (the preprocessing)

A small deterministic step — no LLM needed for the mapping itself:

1. **Parse the label** `"Player (Character)"` → `(player, character_or_role)`. Handle `Deniz (GM)` → player `Deniz`, role `GM` (not a PC). Add this to `chunking.py` (or a new `speakers.py`): `parse_speaker(label) -> (player, character, is_gm)`.
2. **Normalize the turn prefix to the character** when formatting chunks for the LLM. Change `format_turn` to print the **character** (or `GM`) as the speaker, e.g. `Lindo Laut:` instead of `Tim (Lindo Laut):`. The model then naturally attributes in-fiction actions to the character, and never sees the composite string that caused the duplicates.
3. **Emit graph rows** per session: `Player` nodes, `Character` nodes, and `PLAYS {session_id, seq}` edges — built from the parsed cast, independent of the LLM.
4. **Attribution guarantee:** because every segment already carries its acting character, any in-fiction fact extracted from that segment attaches to that **Character**. The `Player` node only receives explicitly out-of-character/meta facts.

Feeding the parsed cast into the extraction prompt ("the speakers this chunk are: Lindo Laut, Dodo, GM…; attribute actions to them") makes attribution essentially deterministic.

## Attribution rules

- **Default: everything a player does in-fiction → their character for that session.**
- In-fiction edges (`ROLLED`, `TARGETS`, `USES_CARD`, `PARTICIPATED_IN`, `OWNS`, `HAS_CLASS`, in-character `DECIDED`, `MEMBER_OF` the party) → **Character**.
- Only clearly out-of-character facts (attendance, table meta, a rules question by the person) may stay on the `Player`. When in doubt, attribute to the Character.

## GM special case (Deniz)

`Deniz (GM)` → `PLAYER_Deniz` with `role:"GM"`; the parenthetical is a **role**, not a PC:
- **Voiced NPC** → attribute to that NPC `Character` (feed known NPC names into the prompt; the label only says "GM", so the NPC must come from content).
- **Pure narration / rules adjudication** → a GM-narrator node (`CHAR_Deniz_GM`, `is_pc:false, role:"GM"`) or the `Player`.
- **Adversaries** the GM runs are `Character{is_pc:false, role:"adversary"}`.

## Queries this unlocks

```cypher
-- current character of a player (latest session)
MATCH (p:Entity{type:'Player', id:'PLAYER_Tim'})-[r:PLAYS]->(c:Entity{type:'Character'})
RETURN c.name ORDER BY r.seq DESC LIMIT 1;

-- who a player controlled in a given session
MATCH (p:Entity{type:'Player', id:'PLAYER_Tim'})-[r:PLAYS {session_id:'2025-05-01'}]->(c) RETURN c.name;

-- a player's whole "career" across every character they've played
MATCH (p:Entity{type:'Player', id:'PLAYER_Tim'})-[r:PLAYS]->(c:Entity{type:'Character'})
RETURN r.seq, r.session_id, c.name ORDER BY r.seq;
```

## Edge cases

- **Character swap between sessions** → handled natively by the new session's labels; no death-detection required.
- **Mid-session swap** → not representable at session granularity by design. If it ever happens, fall back to a `cast_overrides.json` entry splitting that session, or accept session-level attribution. (Rare enough to defer.)
- **One player, two characters in one session** → the label can't encode two; the extraction must name which character acted. Flag for review.
- **Companion (Parry)** → `Character` owned by a `Character` (`OWNS`), not by a Player.

## Acceptance

- `Player` and `Character` are distinct nodes; `Tim` and `Lindo Laut` are two nodes joined by a `PLAYS {session_id}` edge parsed from the transcript labels.
- `format_turn` emits the character (or `GM`) as the speaker; the composite `Tim (Lindo Laut)` string never reaches the LLM and never becomes a node.
- Every in-fiction edge from `2025-03-26` points to a `Character`; none point to a `Player`.
- A later session whose labels name a different character produces a new `PLAYS` edge for that session, and "current character" follows it — with earlier sessions still resolving to the earlier character.

## Roadmap placement

**WP1b — Player/Character split + per-session `PLAYS` from transcript labels + attribution**, immediately after WP1 (canonical ids). Session-granular by design — no scene-level phase needed. See `08_roadmap.md`.
