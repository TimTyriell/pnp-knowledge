# B2 — Glossary-anchored extraction (one budgeted re-extraction)

| | |
|---|---|
| Branch | `feat/anchored-extraction` |
| Base | `origin/main` (after B1 merged and its HUMAN RUN done) |
| Depends on | B1 (uids: the re-extraction must not detach rules), T3 (`RULES_GLOSSARY`), T5 (frozen glossary file), A5/B3 (to measure before/after) |
| Cost | **~$6.50 off-peak full re-extraction plus re-synthesis. HUMAN RUN, budgeted, announced** |
| Size | M code, L operation |

## Goal

Extraction stops naming every entity from scratch. The prompt gets:

1. the **frozen glossary** (T5's `knowledge/state_glossary.yaml`): canonical
   names, aliases and types;
2. the **PC roster per team** (T8's `knowledge/roster.yaml`, in-world names
   only);
3. the **ruled spellings** (`spelling:` family);
4. scope rules moved from `SYNTH_SYSTEM` (only special items, no dungeon
   rooms, what counts as a faction), because entities are born here;
5. an explicit **out-of-character rule**: player names are never entity
   names, aliases or note subjects;
6. `RULES_GLOSSARY` (T3).

`EntityMention` gets `known_name: str = ""`. When the entity matches a
glossary entry, the model copies that entry's canonical name exactly;
otherwise it leaves it empty. Resolve trusts `known_name` first.

## Why

Root cause per `knowledgeAnalysis.md` §2.1. Downstream compensation today
is 585 rules, 624 retired ids and the churn guards. The glossary prefix is
~10–15k tokens, cached by the provider at ~$0.02/MTok.

## Steps

1. **Measure first (no cost):** record the A5 grounding numbers, the B3
   claim-eval numbers (if B3 is done), `rules_doctor.py` counts, the churn
   ratchet, and the entity count. Put them in the PR as "before".
2. `prompts.py`:
   - add `EXTRACT_GLOSSARY_TEMPLATE` (a section "Bekannte Namen" plus
     roster plus spellings);
   - append the scope rules, the OOC rule and `RULES_GLOSSARY` to
     `EXTRACT_SYSTEM`;
   - remove the now-duplicated scope rules from `SYNTH_SYSTEM` **only if**
     you bump `SYNTH_PROMPT_VERSION` in the same change; otherwise leave them;
   - bump `EXTRACT_PROMPT_VERSION` to `"7"`;
   - add new pins (A4 test) and delete T3's "not yet in extraction" test.
3. `models.py`: `EntityMention.known_name` with a description. This changes
   the schema, which is covered by the version bump.
4. `extract.py`:
   - the glossary text goes into the **system** message (stable prefix) and
     into the cache key (sha of the glossary text, like T5);
   - the freeze env vars keep working;
   - document that a glossary refresh re-extracts everything (unless
     frozen).
5. `resolve.py`: if `mention.known_name` matches a registry canonical name
   (case-insensitive), take that concept id directly, before step 1 of the
   resolution order. Log the share of mentions resolved this way.
6. Tests:
   - the prompt contains the glossary;
   - `known_name` short-circuits resolve;
   - the cache key changes with the glossary;
   - a player name in the private roster list is rejected in a post-check
     (T8's `player_name_hits` on mention names/notes, local only).
7. **HUMAN RUN:**
   - `pnp run --estimate` (expect ~68+ extraction calls);
   - run off-peak;
   - the rename guard *will* trip; inspect it with the churn test;
   - `--allow-rename` only after the uid check shows rules are attached;
   - write `docs/audits/<date>-v7-anchored-extraction.md` with before/after
     numbers.
8. After: run `rules_doctor.py` and delete rules the glossary made inert.
   Report how many.

## Done when

- [ ] Before/after table: entity count, duplicates (`dup_doctor.py`), grounding near-ratio, rules dead/alive, player-name ratchet.
- [ ] Churn handled via uids; no wiki page detached (pnp-export-data stage 02 plan unchanged except intended merges).
