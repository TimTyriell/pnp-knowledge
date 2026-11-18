# ADR-007 — Opaque, minted-once concept uids (ADR-004's hybrid)

**Status:** Proposed, 2026-11-18. Accepted by merging the PR that adds it.
**Supersedes:** ADR-004 (identity stays derived from the name).
**Related:** ADR-001, `docs/plans/B1-opaque-ids.md`, PIPELINE.md §4.

## Context

A `concept_id` is derived from the name the model chose. A re-extraction
rewords names and the ids move — 432 of 868 on the v6 run. Everything keyed on
a concept id detaches: rule families in `entity_rules.yaml`, the dashboard's
Glossar, `pnp-export-data`'s `wiki_pages.toml`. ADR-004 costed a hybrid and
deferred it until a second consumer keyed on ids; the dashboard and the wiki
map both do now, and B2 (one budgeted re-extraction) needs identity to survive
it.

## Decision

1. **Format.** `uid: c_<8 lowercase base32>`, e.g. `c_k3m9q2xa`. Random
   (`secrets`), collision-checked against the registry. Short enough to type.
2. **Where it lives.** `entity_registry.yaml` `entities[].uid` and
   `retired[].uid` (generated, preserved across runs), and frontmatter `uid:`
   after `id`. Filenames and `concept_id` stay derived and readable.
3. **Keeping it across a rename** (`resolve.assign_uids`, run right after
   `resolve_entities`):
   - an id that already has a uid (live or retired) keeps it;
   - a new id inherits the uid of a concept that was live last run, is absent
     now, shares a name (canonical or alias, case-insensitive) and is in the
     same identity space (same type, or both persons);
   - anything else gets a fresh uid.

   Uids are assigned before anchored events and O1-demoted concepts are
   filtered out, and every retired entry gets one, so a demoted concept comes
   back under its uid when its id recurs. A uid is unique across live and
   retired: an inherited uid leaves its old retired entry.
4. **Rename guard** compares uids where the previous registry had them, so a
   rename that keeps its uid is not a loss. The first run after this change
   still compares by concept id.
5. **Rules.** The families that point at an existing concept accept a uid or a
   concept id: `ignore`, `important`, `unimportant`, `event_concepts`,
   `keep_concepts`, `never_merge`, `canonical_name`, `alias_block`,
   `status_rules.drop`. One function, `_registry_data` → `rekey_uids`, turns
   uids back into concept ids, so no loader changed. An unknown uid matches
   nothing (reported as a dead rule, like a stale concept id).
   **`merge:` and `split:` values stay concept ids** — they *define* a target
   (the directory sets the entity type) rather than point at one.
   `thread_rules` keys are thread ids, not concepts: unchanged.
6. **Migration.** `services/kb/migrate_rules_to_uids.py` rewrites the rules
   file line by line, comments intact, the concept id kept as a trailing
   comment: `- c_k3m9q2xa  # characters/esterossa`. Dry run by default.
7. **Dashboard.** The Glossar sync edits a concept under its uid once the file
   uses it, and rekeys the rules before display.
8. **API.** `/concepts/{uid}` resolves like a typed id; `/concepts` lists
   `uid` when present.
9. **Not a model field.** The uid is a `concept_id -> uid` map beside the
   entities, not a `CanonicalEntity` field: synthesis cache keys hash
   `entity.model_dump()`, so a field would re-key every cached synthesis.

## Consequences

- Rules and wiki pages survive B2's re-extraction as long as the renamed
  concept shares one name with its old self — the common case. A rename with
  no shared name still detaches; the rename guard catches a mass one.
- `ignore:` ids never reach the registry (their mentions are dropped), so they
  never get a uid and stay concept ids. Harmless: they are never renamed.
- The first warm run after merge writes `uid:` into every concept file, so
  every file shows a diff once (and `generated.at` moves with it).
- Order of the human run: warm `pnp run` → `migrate_rules_to_uids.py --write`
  → warm `pnp run` (rules still apply, `rules_doctor.py` shows no new dead
  rules) → pnp-export-data migration.

## Open question for the human

Point 5's `merge:`/`split:` exception is the default the plan proposed.
Merging this ADR accepts it.
