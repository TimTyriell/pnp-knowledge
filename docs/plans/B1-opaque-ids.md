# B1 — Opaque, minted-once concept ids (ADR-004's hybrid)

| | |
|---|---|
| Branch | `feat/opaque-concept-ids` (pnp-knowledge) and `feat/key-on-uid` (pnp-export-data) |
| Base | `origin/main` in both repos, after the T-series is merged |
| Depends on | T-series (so the rule families it re-keys are final); ADR-004 revisit trigger 2 is arguably firing already (the dashboard Glossar and `wiki_pages.toml` both key on `concept_id`) |
| Cost | $0. A warm re-emit (**HUMAN RUN**) writes the new frontmatter key |
| Size | L, cross-repo |
| Gate | **ADR-007 must be accepted by the human before step 3** |

**Status 2026-11-16: not started.** No `uid` exists in code, registry or
frontmatter. This plan was written before S1, C1, D1 and the O-series; the
section *Amendments* below brings it up to date. Where the two disagree, the
amendments win. It also needs the O-series bundle run merged first: that run
brings `keep_concepts:` and `thread_rules.keep_apart`, which B1 re-keys.

## Amendments (2026-11-16)

1. **ADR number.** `ADR-005` (ai-native delivery) and `ADR-006` (agent mode)
   are taken. Write `docs/architecture/ADR-007-opaque-ids.md`. Read every
   "ADR-005" in this plan as ADR-007.
2. **Rule families added since.** Design point 4 lists the families keyed by
   concept id. Add `keep_concepts:` (O1), `thread_rules.keep_apart` (O2) and
   the status rules (O3, `state.load_status_rules`). The loaders to route
   through `_rule_key_to_concept`: in `resolve.py` `_load_never_merge_pairs`,
   `_load_canonical_names`, `_load_alias_blocks`, `_load_ignored`,
   `_load_important`, `load_event_concepts`, `load_keep_concepts`, and the
   `unimportant` family; in `state.py` `load_thread_rules` and
   `load_status_rules`.
3. **`merge:` and `split:` values.** They *define* a target — the directory
   in the value sets the entity type — they do not point at an existing
   concept. **STOP — ask the human** in ADR-007. Default to propose: they
   stay concept ids.
4. **Demoted concepts (O1).** About 700 ids now sit in `retired:` without a
   file. Mint `retired[].uid` for them too, and give the uid back when the
   concept is promoted on recurrence (`_reanchor_to_retired`). Add a test:
   demoted in one run, seen in a second session in the next run, same uid.
5. **Dashboard.** `services/dashboard/rules_edit.py` and `glossary.py`
   line-patch `knowledge/entity_rules.yaml` by concept id. After
   `migrate_rules_to_uids.py --write` the keys read `c_k3m9q2xa  # npcs/harald`.
   The Sync must find a line by uid (resolved through the registry), or it
   stops patching without an error. Add that as a step, with a case in
   `services/dashboard/test_rules_edit.py`.

## Goal

Implement the hybrid that ADR-004 costed and deferred:

- Every concept gets a **stable opaque `uid`**, minted once, stored in the
  registry and in frontmatter, and never derived from the name.
- Filenames (`npcs/harald.md`) and `concept_id` stay derived and human
  readable. A rename moves a file but carries the uid with it.
- **Rule families and downstream maps key on the uid**, so a re-extraction
  that rewords a name (432 of 868 ids moved on v6) no longer detaches a
  rule or a wiki page.

This is the precondition for B2: a budgeted re-extraction becomes a
non-event for identity.

## Design (write into ADR-005 first)

1. **Format:** `uid: c_<8 lowercase base32 chars>`, e.g. `c_k3m9q2xa`.
   Random (`secrets`), checked for collisions against the registry.
   Short enough to type in a rules file.
2. **Where it lives:**
   - `entity_registry.yaml` `entities[].uid` (generated file, but the uid is
     *preserved* across runs exactly like `aliases`);
   - `retired[].uid`;
   - frontmatter `uid:`.
3. **How a concept keeps its uid across a rename:** resolve already maps a
   reworded name back to the old concept via reanchoring, the retired ledger,
   merges and so on. Today, when that fails, the old id retires and a new id
   is minted.
   - New rule: when `write_registry` retires concept X and mints concept Y
     **in the same run**, and Y was reached through `_reanchor_to_retired`
     or a `merge:` rule naming X's aliases, Y **inherits X's uid**.
   - Otherwise Y gets a fresh uid.
   - The rename guard compares **uids**, not concept ids. A rename that
     keeps its uid isn't a loss.
4. **Rules re-keying:** families keyed by concept_id (`ignore`, `important`,
   `canonical_name`, `never_merge`, `alias_block`, `unimportant`,
   `event_concepts`, `thread_rules` keys) accept **either** a concept_id
   **or** a uid.
   - A loader helper `_rule_key_to_concept(key, uid_index)` resolves a uid
     to the current concept id.
   - A one-time script rewrites the rules file's concept_id keys to uids,
     **line-level, comment-preserving**, like the dashboard's Glossar sync
     (see `services/dashboard/rules_edit.py`).
   - It keeps the readable concept_id as a trailing comment:
     `- c_k3m9q2xa  # events/verhandlung_mit_harl`.
5. **API:** `/concepts/{uid}` resolves like a typed id does today (add uid
   to `id_index`). `/concepts` listing includes `uid`.
6. **pnp-export-data:** `wiki_pages.toml` lead/sub entries accept a uid. A
   one-time migration rewrites concept_ids to uids with comments, and
   `02_extract.py` carries `uid` per concept.

## Steps (pnp-knowledge)

1. Branch; write `docs/architecture/ADR-005-opaque-ids.md` from the design
   above. Mark it "Proposed". **STOP — the human accepts or edits it.**
2. `models.py`: `CanonicalEntity.uid: str = ""`.
3. `resolve.py`:
   - `write_registry` preserves `uid` per concept (exactly like
     `preserved_aliases`), mints missing ones, writes them in `entities` and
     `retired`, and implements inheritance (design 3);
   - add `load_uid_index(registry_path) -> dict[str, str]` (uid → concept_id);
   - each id-keyed rule loader maps uid keys through it.
4. `emit.py`: `emit_entity` writes `uid` to frontmatter (put it after `id`).
   Sessions get no uid; their id is their date.
5. `emit.check_rename_safety`: compare the uid sets. Keep the concept_id
   comparison as an informational log line.
6. `api.py`: uid in `id_index` and in the listing.
7. A migration script, `services/kb/migrate_rules_to_uids.py`: dry-run by
   default, `--write` to apply. Line-level edits only. Test it on a copy of
   the rules file in a tmp dir.
8. Tests:
   - uid preserved across two `write_registry` calls;
   - uid inherited on a reanchor rename;
   - fresh uid on a genuinely new concept;
   - rules keyed by uid apply;
   - the rename guard passes on a rename that keeps its uid;
   - the migration script round-trips comments.
9. PIPELINE.md §4: replace "There is no stable id in this system" with the
   new chain. ADR-004 gets a "Superseded by ADR-005" header line.

## Steps (pnp-export-data)

1. `02_extract.py`: copy `uid` from frontmatter into `entities.json`.
2. `pagemap.py`: a lead or sub may be a uid. Resolve through the plan's uid
   map. Error if a uid is unknown.
3. A one-time migration of `wiki_pages.toml` to uids, with concept_id
   comments.
4. Tests in `test_export.py` for uid-keyed groups.

## HUMAN RUN (sequence matters)

1. Merge the pnp-knowledge PR. Run a warm `pnp run` → every concept gets a uid.
2. Run `migrate_rules_to_uids.py --write` and review the diff. Commit.
3. Run a warm `pnp run` again: the identity-churn ratchet is unchanged and
   the rules all still apply (`rules_doctor.py`: no new dead rules).
4. Merge the pnp-export-data PR. Run stages 01–03; the plan must be unchanged.

## Done when

- [ ] Every concept has a uid; a renamed concept keeps it (test).
- [ ] The rules file and `wiki_pages.toml` key on uids.
- [ ] ADR-005 accepted; ADR-004 marked superseded.
