# T7 — World status and attitude on entity concepts

| | |
|---|---|
| Branch | `feat/world-status` |
| Base | `origin/main` (after T6 merged) |
| Depends on | T6 (`NameIndex`, the state fold inside `_run_pipeline`) |
| Design | [T00 §4.4, §4.6, §4.7](T00-tracking-model.md) |
| Cost | $0; warm re-emit **HUMAN RUN** |
| Size | M |

## Goal

From the ledger's `statuses` and `attitudes`, write onto the matching entity
concepts:

- `world_status` (current), plus `world_status_history` when there is more
  than one entry;
- `attitude` (the latest entry per `toward`);
- a deterministic `## Stand` body section, inserted before `# Belege`.

The model is never called; synthesis caches are unaffected. The section is
added to the already-synthesized body at emit time, the same way the
`# Belege` backfill works.

## Rules (from T00 — implement exactly)

1. **Current status** = the last entry with `evidence == "observed"`. If
   there is none, the last entry of any evidence. Order entries by
   `(entry.date, entry.citation_ts)`.
2. A `claimed`, `rumor` or `speculation` entry never overrides an observed
   one. It stays in the history, labelled.
3. **Allowed values by directory:**
   - `characters`, `npcs`: alive, dead, missing, captured, transformed;
   - `factions`: alive, missing, destroyed (alive = the faction exists);
   - `items`, `locations`: destroyed only;
   - `deities`, `domains`: none, so drop the entries and record them in
     unmatched as `"<name>: <value> not allowed for <dir>"`.
4. **Attitude** only on `npcs/` and `factions/`.
   - `toward == "Gruppe"` → `party`.
   - Otherwise `NameIndex.lookup(toward)`, which must be a `characters/` id.
   - Anything else goes to unmatched.
   - Keep the latest entry per `toward` (observed beats non-observed, as in
     rule 1).
5. `since` = episode marker of the entry's session (`citation_labels([url],
   episodes)[0]`), else the date.

German labels for the body:

```python
STATUS_DE = {"alive": "lebendig", "dead": "tot", "missing": "verschollen",
             "captured": "gefangen", "transformed": "verwandelt", "destroyed": "zerstört"}
ATTITUDE_DE = {"allied": "verbündet", "friendly": "freundlich", "neutral": "neutral",
               "wary": "misstrauisch", "hostile": "feindselig"}
EVIDENCE_DE = {"observed": "beobachtet", "claimed": "behauptet",
               "rumor": "Gerücht", "speculation": "Vermutung"}
```

Put these in `state.py` and reuse `EVIDENCE_DE` in T6's `emit_threads` (move
it there if T6 defined it inline).

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c feat/world-status origin/main
```

### 2. `state.py`: `world_state_by_concept`

```python
def world_state_by_concept(
    ledger: Ledger, names: NameIndex, episodes: Episodes
) -> tuple[dict[str, dict], list[str]]:
    """``concept_id -> frontmatter fragment`` and the unmatched lines.

    The fragment holds any of ``world_status``, ``world_status_history``,
    ``attitude``. Applies T7 rules 1-5; see docs/plans/T7-world-status-and-attitude.md.
    """
```

Each status or attitude dict looks like:
`{"value": ..., "since": marker, "at": entry.citation_ts, "evidence": entry.evidence}`,
plus `"claimed_by": ...` when it is non-empty. For attitudes, add
`"toward": "party" | concept_id`.

`world_status_history` holds all entries in order, but only if there are 2
or more.

### 3. `state.py`: `render_stand_section(fragment, titles) -> str`

`titles` maps `concept_id → canonical name`, so a `toward` of
`characters/lindo_laut` renders as "Lindo Laut". Output:

```markdown
## Stand

- Status: tot seit P-34 (beobachtet, 02:02:27)
- Früher: lebendig (P-01, beobachtet); tot laut Seraph (S1-02-A, behauptet)
- Haltung zur Gruppe: feindselig seit S1-02-A (beobachtet)
- Haltung zu Lindo Laut: freundlich seit P-20 (beobachtet)
```

- The "Früher:" line appears only when there is history, and lists the
  entries other than the current one.
- Use "laut {claimed_by}" when `claimed_by` is set.
- Return `""` for an empty fragment.

### 4. `emit.py`

1. `emit_entity` gets the keyword `world_state: dict | None = None`. In the
   frontmatter literal, after `teams`, add `**(world_state or {}),`.
2. A helper:

```python
def insert_before_belege(body: str, section: str) -> str:
    """Put ``section`` directly above the ``# Belege`` heading, or at the end."""
    if not section:
        return body
    m = _BELEGE_HEADING_RE.search(body)
    if not m:
        return f"{body.rstrip()}\n\n{section}\n"
    return f"{body[:m.start()].rstrip()}\n\n{section}\n\n{body[m.start():]}"
```

### 5. `cli.py`

After the citation relabel loop and before the emit loop:

```python
    world, world_unmatched = (
        world_state_by_concept(ledger, NameIndex(entities), episodes)
        if not partial_run else ({}, [])
    )
    titles = {e.concept_id: e.canonical_name for e in entities}
    for cid, fragment in world.items():
        if cid in bodies:
            bodies[cid] = insert_before_belege(bodies[cid], render_stand_section(fragment, titles))
```

In the `emit_entity(...)` call, add `world_state=world.get(entity.concept_id)`.
Append `world_unmatched` to the T6 `state_unmatched.md` content.

Mind the order: `relationship_edges` reads `bodies`. Running the insertion
after the edges are computed is fine and simpler. Put the block right after
`edges = relationship_edges(...)`.

### 6. Validation (advisory)

In `validate.py`, add `invalid_world_status: list[tuple[str, str]]`:

- flag a `world_status.value` not allowed for the directory (rule 3);
- flag an `attitude` on a directory other than `npcs` or `factions`.

Don't add it to `integrity_ok`.

### 7. Tests: `tests/test_world_state.py` (new)

Build a `Ledger` by hand (`StatusRecord`, `AttitudeRecord` with `Entry`), a
`NameIndex` over 3 tiny `CanonicalEntity`s (a character, an NPC, an item)
and an `Episodes` with two URLs. Assert:

1. **Rotunas case**: observed `dead` at P-34 plus a later claimed `dead`
   (different detail) → current is the P-34 observed entry, and history has
   2 entries.
2. Observed `alive` (P-01), then claimed `dead` (S1-02-A) → current is
   `alive`. The stand section says "Status: lebendig seit P-01" and "tot laut
   Seraph".
3. `destroyed` on a character → not emitted; reported unmatched.
   `destroyed` on an item → emitted.
4. Attitude `toward: "Gruppe"` → `party`. Toward a PC name → that
   `characters/` id. Toward an unknown name → unmatched.
5. Attitude on an item → unmatched (not emitted).
6. `insert_before_belege` puts the section above `# Belege` and is a no-op
   for `""`.
7. `emit_entity(..., world_state=...)` writes `world_status` to the
   frontmatter.

### 8. Verify, commit, PR

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
```

Message: `feat(kb): emit world status and attitude from the state pass`

## HUMAN RUN

Warm `pnp run`. Then check these by hand:

- `characters/rotunas.md` → `world_status.value: dead`, evidence `observed`,
  `since` = the 2026-04-09 episode;
- `characters/cookie.md` → dead;
- `npcs/vitius.md` → attitude toward party;
- 5 random NPCs with a `## Stand` section, checked against `url_at`.

Fix wrong ones by:
- (a) an `ENTSCHEIDUNG:` ruling in `knowledge/sources/` for the GM's record,
  and
- (b) since status comes from the state pass, a re-run of that one
  session's state after a prompt fix. **Don't** hand-edit the bundle.

If (b) is too expensive for a single mistake, propose a `status_rules:`
family (same shape as `thread_rules.status`) in a follow-up. Don't add it
speculatively.

## Done when

- [ ] Rotunas, Cookie and Esterossa show `dead`.
- [ ] A claimed fact never overrides an observed one (test 2).
- [ ] Validate shows 0 `invalid_world_status` on the real bundle.
