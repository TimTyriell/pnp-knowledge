# O1 — Single-session Items, Locations and Factions are session mentions, not concepts

Branch `feat/ontology-hygiene`. Sixth in the O-series (largest change; last
code plan). Cost $0 code. **Ends with the shared HUMAN RUN for O1–O7.**

## Intent

Measured 2026-11-16: items 95 %, locations 90 %, factions 90 % rest on one
session. 62 % of all entities have no inbound link from another concept.
pnp-export-data's relevance gate (`MIN_SESSIONS = 2`) already keeps them off
the wiki. They are session detail, and the session note already lists each
one with its note under `# Auftretende Entitäten`.

T4 solved the same problem for Events (305 → 3) with an allowlist and session
anchors. O1 extends that mechanism. Scope ruled by the human 2026-11-16:
**Item, Location, Faction**.

A concept of those types is **demoted** (not emitted as a file) when all hold:
- its mentions span fewer than `MIN_CONCEPT_SESSIONS = 2` distinct `session_id`s;
- it is not `important` (registry/rules flag);
- it is not listed in a new rules family `keep_concepts:`.

What a demoted concept becomes:
- In its session note, the `# Auftretende Entitäten` bullet stays, **without a
  link**: `* {name} — {note} [{ts}]`.
- No file; links to it from other bodies are not generated (the link index is
  built from emitted entities), so prose shows the plain name.
- Its id leaves `entities:` in the registry and lands in `retired:`, exactly as
  T4's anchored events did. This is required: `test_registry_and_bundle_agree`
  demands a file for every registry id. If the name recurs in a later session,
  slug derivation (and `_reanchor_to_retired`) gives back the same id, and it
  is promoted automatically.

Identity is unchanged: the rename guard still sees all entities (it runs before
the T4 filter); only which files are written changes.

## Steps

1. **Tests first**, extend `services/kb/tests/test_event_anchors.py` (reuse
   `_offline_run_args` and the `test_run_keeps_only_allowlisted_events_as_concepts`
   pattern):
   - unit: `is_anchored` for a 1-session Item → True; 2-session Item → False;
     1-session Item with `important=True` → False; 1-session Item in keep → False;
     1-session NPC → False; Event not in `event_concepts` → True; Event in it → False.
   - unit: `load_keep_concepts` reads `keep_concepts:` from `entity_rules.yaml`.
   - end to end through `_run_pipeline`: one session, one Item mention
     "Rostiger Schlüssel" → no `items/rostiger_schluessel.md`; the session note
     contains `* Rostiger Schlüssel — ` and no `](/items/rostiger_schluessel.md)`.
   - end to end: same Item listed in `keep_concepts:` → file exists, bullet linked.
   - unit for `emit_sessions(..., unlinked_mentions={key})` → plain bullet.
2. `services/kb/src/pnp_okf/models.py`: after `SESSION_SCOPED_TYPES` add
   ```python
   # O1: types whose one-session members are session detail, not concepts.
   DEMOTABLE_TYPES = {EntityType.ITEM, EntityType.LOCATION, EntityType.FACTION}
   MIN_CONCEPT_SESSIONS = 2
   ```
3. `services/kb/src/pnp_okf/resolve.py`, next to `load_event_concepts`:
   - `load_keep_concepts(registry_path) -> set[str]` — same body, family `keep_concepts`.
   - ```python
     def is_anchored(entity: CanonicalEntity, event_concepts: set[str], keep: set[str]) -> bool:
         """True when the entity is rendered inside its session note instead of
         as a concept file: T4 events, and O1 one-session items/locations/factions."""
     ```
4. Replace the three copies of the T4 filter with `is_anchored` (load both
   sets once per function):
   - `cli.py` `_run_pipeline`, the block starting `# T4: an Event is a concept only when`;
   - `frozen.py`, the freeze loop condition `e.type == EntityType.EVENT and e.concept_id not in event_concepts`;
   - `cache_gc.py`, the `keep_events` block.
   Update the cli log line to report events and demoted non-events separately.
5. `cli.py`: split `anchored` into `anchored_events` (type Event) and
   `demoted` (the rest). `event_anchors(anchored_events)`. Build
   `unlinked = {(m.session_id, m.citation_ts, m.note) for e in demoted for m in e.mentions}`
   and pass `unlinked_mentions=unlinked` to `emit_sessions`.
6. `emit.py` `emit_sessions`: new keyword `unlinked_mentions: set[tuple[str, str, str]] | None = None`.
   In the mention loop, **before** the `mention_concept_ids` lookup: if the key
   is in `unlinked_mentions`, append `f"* {mention.name} — {mention.note} [{mention.citation_ts}]"` and `continue`.
   Document it in the docstring next to `anchors`.
7. `knowledge/entity_rules.yaml` (allowed by the guard): add a commented
   `keep_concepts:` family after `event_concepts:`. Seed it with:
   (a) verified single-session concepts of the three types:
   ```bash
   cd knowledge/bundle/splitter_des_ewigen
   for f in items/*.md locations/*.md factions/*.md; do
     grep -q "^verified:" "$f" || continue
     n=$(sed -n '/^sources:/,/^---/p' "$f" | grep -c "resource:" ); [ "$n" -le 1 ] && echo "${f%.md}"
   done
   ```
   (b) any single-session id of those types referenced in `../pnp-export-data/wiki_pages.toml`
   (read only; `grep -oE "(items|locations|factions)/[a-z0-9_]+" ../pnp-export-data/wiki_pages.toml | sort -u`,
   then keep only ids that are single-session per the command above minus the `verified` check).
   One comment line per group saying why ("GM-verified", "wiki page").
   If (b) finds more than 20 ids, STOP and report the list.
8. Full suite. Bundle tests read the committed bundle, so they do not move
   until the HUMAN RUN. `test_registry_and_bundle_agree` must stay green in
   the end-to-end test (demoted ids not in registry `entities:`).

## HUMAN RUN (shared by O1–O7, after all code commits)

From `services/kb`, off-peak not required (warm):
1. `.venv/Scripts/python.exe -m pnp_okf.cli run --estimate` — expect only a few
   synthesis calls (O7 subtype changes). **STOP if the estimate exceeds $0.50.**
2. `.venv/Scripts/python.exe -m pnp_okf.cli run --allow-prune` — O1 prunes
   roughly 700 files, far over the 2 % prune guard; that is intended.
3. Review `git -C ../../knowledge diff --stat` and spot-check 5 session notes
   for unlinked bullets and 5 surviving items for links.
4. `PNP_REQUIRE_BUNDLE=1 .venv/Scripts/python.exe -m pytest -q`. Re-baseline
   any moved ratchet (`test_link_coverage.py` baselines, relation coverage,
   positional ids) **in the direction the policy allows, with a comment citing O1**
   (PIPELINE.md §10). A hard-0 invariant that fails is a bug: stop.
5. Commit the bundle on `ingest/<date>-ontology-hygiene` in the bundle repo,
   PR it, tag after merge (docs/RELEASING.md).

## Done when

- [ ] New tests pass; suite green except the known `last_run.json` test.
- [ ] `ruff check .` clean.
- [ ] `keep_concepts:` seeded with comments.
- [ ] After HUMAN RUN: items+locations+factions files ≈ 150–250 (from 786); 0 dangling links; numbers in the PR.

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q tests/test_event_anchors.py
cd services/kb && .venv/Scripts/python.exe -m pytest -q
ruff check .
# after HUMAN RUN, from repo root:
for d in items locations factions; do echo "$d $(ls knowledge/bundle/splitter_des_ewigen/$d | grep -vc index.md)"; done
cd services/kb && .venv/Scripts/python.exe -m pnp_okf.cli validate --bundle ../../knowledge/bundle/splitter_des_ewigen
```
