# Data-quality audit of OKF bundle `splitter_des_ewigen` (2026-08-29)

Deep sample along 6 questions (length, name specificity, wrongly split, wrongly merged, faction↔character↔place relations, main characters group A/B), carried out with 3 parallel Sonnet subagents; every finding below was re-checked against the bundle, not just taken over from subagent output.

**Core result:** PC coverage is exemplary, length correlates cleanly with the amount of evidence in aggregate. The three real defects:

1. The 60 richest nodes (deep tier) are graph-invisible — the autolinker only ran on stub nodes.
2. ~25 identity duplicates that produce no conflict file and therefore stay invisible.
3. `important: true` was used as a tier switch in both wrong directions: slapped onto one-scene entities (padding), withheld from recurring figures (stubs) — and 7 of the 29 pins additionally pointed at a concept_id that does not (any longer) exist.

All fixes go to the **inputs** (`entity_rules.yaml`, `sources/Kanon_Entscheidungen.md`, pipeline code in `services/kb/src/pnp_okf/`) — never into the generated bundle (see `knowledge/conflicts/README.md`).

## Inventory

| Type | Nodes | Median words | Max | Deep tier |
|---|---|---|---|---|
| characters | 36 | 721 | 4088 | 19 |
| deities | 32 | 569 | 1928 | 17 |
| domains | 12 | 154 | 1417 | 1 |
| events | 252 | 72 | 6554 | 0 |
| factions | 43 | 167 | 1272 | 2 |
| items | 149 | 73 | 3742 | 0 |
| locations | 151 | 78 | 3863 | 9 |
| npcs | 229 | 83 | 5905 | 12 |
| **total** | **896** | | | **60** |

Healthy: 0 orphaned registry entries, 889 internal links of which **0 broken**, 7 orphan nodes.

## Question 1 — Length: correct in aggregate, tier switch mishandled

Words vs. `mention_count` cleanly monotonic: 1 mention → 75 words (n=765) · 2 → 235 (61) · 3–4 → 357 (33) · 5–9 → 520 (18) · 10+ → 1671 (19). Extraction is proportional to length; the error sits in the **tier assignment**.

*Too long* — all 5 nodes with ≤1 mention and >400 words carry `important: true`: `deities/coram_schildbrecher` (916 words), `deities/akastrale` (800 words — its own evidence quotes an `ENTSCHEIDUNG:` that „vorerst kein umfangreicher Eintrag entstehen soll" (no extensive entry should be created for now), and thereby contradicted it), `locations/boragdil` (592 words out of a ~2-minute scene), `deities/schlangengott` (569), `deities/heiliger_duran` (497 — „wenig bekannt" (little known) about the god himself, the rest is about the amulet).

*Too short* — 9 nodes with ≥5 mentions, no deep tier, no flag: `npcs/hal_harl` (5 M, co-leader of the Silberkerne), `npcs/auranil` (5), `npcs/liam_velora` (7), `npcs/lobrecht` (6), `npcs/miaomani` (6), `locations/ringtal` (6), `locations/banditenlager_der_silberkerne` (5), `factions/silberkerne` (6), `items/amulett_des_heiligen_duran` (7).

Cause: `DEEP_MENTION_THRESHOLD = 8` (`models.py`) — the 5–7 class fell entirely to `standard`.

**Fix:** `DEEP_MENTION_THRESHOLD` 8 → 5 (fixes the 9 stubs structurally, without hand-maintenance); `unimportant: deities/akastrale` (fixes the one case the threshold does not touch).

## Question 2 — Name specificity: systematically too generic

312 nodes with a one-word name. Generic category terms as entities, `mention_count = 1` despite 13–65 occurrences in the session recaps: `events/falle` (30) · `locations/dorf` (21) · `locations/pass` (20) · `locations/taverne` (18) · `items/kristall` (18) · `locations/nebel` (16) · `npcs/gnoll` (13) · `domains/daggerheart` (65 — the **rules system**, not a world domain).

**Proof that these are gaps, not intent:** `ignore:` already contained `npcs/die_kinder` with exactly this justification — but the rule matches on exact strings, and `npcs/kinder` (without the article) kept living beside it. A new structural check (`test_article_variant_does_not_slip_past_a_rule`) found **12** such article duplicates in total, not just the two originally suspected.

Slug/name conflation: `locations/ringtal` is titled „Kleinringtal", its own body describes Ringtal as a *different*, larger place — but links to itself (self-link, see question 5 / fix 4).

**Fix:** 10 generic nodes into `ignore:`, `kristall` as a bare form into `merge:` (already links to `items/gruener_kristall`).

## Question 3 — Wrongly split: ~22 duplicates

**Certain:** 5 PC session-zero stubs never folded (`saris_bendal`↔`saris`, `celin_cookie`↔`cookie`, `marco_dodo`↔`dodo`, `tim_lindo_laut`↔`lindo_laut`, `esterossa_mikasa`↔`esterossa`) — for four of them `merge:` already folded the VTT class label, not their own stub title. Nodes that link to their own duplicate (self-proving): `priesterin_auranie`→`auranil`, `graf_voras`→`voras`, `captain_lobrecht`→`lobrecht`, `das_amulett_von_lindo_laut`→`amulett_des_heiligen_duran`, `das_ende`→`ende_jenseits_der_orkgebiete` (the split rule covered only session 2026-03-18, not 2025-10-07).

Type splits following the `zebros` precedent: `akastrale`, `suedrawell`, `neue_goetter` (each deity vs. NPC/faction). Spelling/article variants: `tavok`, `kol_merefs`, `jorah_vanur`↔`joar_vanur`, `die_alten_goetter`, `der_streitkolben`, `stab_von_lindo_laut`, `die_untoten`, `fluechtlinge`.

**Correctly separate (counter-check passed):** `miko`/`myko`, `sage`/`sange`. For `miaomani`/`miyamani` the `never_merge` justification is *factually stale* (calls Miyamani a „Halbling" (halfling), while the generated node describes a Katari) — the decision is probably still right, the justification no longer is.

**GM decision needed:** `gilde_in_breska` (faction or place?), `vora`/`voras`.

**Fix:** all certain cases as `merge:`/`split:` in `entity_rules.yaml`.

## Question 4 — Wrongly merged

**`npcs/hans_soldat_aus_breska`** links „Hans" to `npcs/hans_wirt_zum_gruenen_sichelmond` — precisely the man its own `split:` rule (**already present**) separates as „zwei unterschiedliche Männer" (two different men). The rule separates correctly, the generated body re-merges them anyway — needs a `pnp run` with the new `never_merge:` pair to correct itself.

**`npcs/jorah_vanur`** linked its subject's first name to `deities/jorah` — a mortal merchant conflated with a god.

**Ring der Teleportation — corrected assessment.** This audit's original hypothesis was a mis-merge (Dodo's ring wrongly filed under Lindo Laut's name). A GM clarification during implementation corrects that: **„Der Ring der Teleportation ist der Ring von Lindo Laut"** (the Ring of Teleportation is Lindo Laut's ring) — `items/ring_von_lindo_laut` was the actual duplicate (now merged), and the ring Dodo destroyed is a *third*, independent object (Abisalis, purple magic) which per `Kanon_Entscheidungen.md` is already meant to be carried in the collective entry „Ringe" (rings). `sources/Kanon_Entscheidungen.md` was extended with exactly this clarification.

**Config drift, broader than originally found:** the hard check `test_important_pins_name_existing_concepts` (new) found **7** dead `important:` pins, not just the one (`deities/kol_meref`) from the first sample: `deities/bodrak` (real: `bodrak_gott_der_stille`), `deities/kaleandra_die_rote` (real: `kaleandra`), `locations/burg_zebros` (real: `burg_des_belorus`), `deities/neiraj` (never was a concept_id, only a merge-key name), plus `deities/gruul` and `deities/sitravil` — neither matches any existing concept, alias or merge key; presumably gone from the bundle without a successor. Four corrected, two removed for lack of a successor (GM question, see below), one removed (no successor needed, Nerash as a deity is always deep tier anyway).

## Question 5 — Relations faction↔figure↔place: largest structural defect

**Measurement:** 26 % of the 42 faction nodes link `/characters/`, 31 % `/npcs/`, 38 % `/locations/`; **20 of 42 factions name not one single member as a link**. Only **13.6 %** of the 228 NPCs carry a `/factions/` link.

**Seed Belorius ↔ undead army ↔ Zebros:** `factions/koenigreich_zebros` — the richest faction node — had **zero links in the entire file**. `npcs/belorus` linked neither the army nor the kingdom. `locations/berge_von_zebros` had a section „Rolle im Konflikt" (role in the conflict) about the undead threat but did not link Belorus.

**Seed Hag Landra ↔ Cornivum ↔ swamp:** `locations/cornivum` named Lenra as the cause **in plain text**, zero links in the whole file. `npcs/lenra` did not mention Cornivum at all.

**Proof that the information is present:** the session recaps `2025-05-14.md` and `2025-06-03.md` list all three entities, correctly linked. The relation existed in the source and was lost **in synthesis**.

**Root cause (code, verified):** `_autolink()` in `synthesize.py` was called exclusively by `render_brief_body()` — `synthesize_entity_body()` (`standard`/`deep`) relied on the LLM itself, which in long structured prose effectively does not link on its own.

**Fix (implemented):** `autolink_prose()` — now runs for all tiers, splits before `# Belege`, skips heading lines, is idempotent (verified by unit test in `test_brief_local.py`). Takes effect on the next `pnp run` **without** new model calls, since the synthesis cache stores the body *before* this post-processing.

**Self-links (side finding, its own fix):** `locations/ringtal` and `npcs/der_seraph_vierter` linked to themselves. Fix: `normalize_body()` gets a `self_id` parameter and degrades a link to its own concept to plain text.

## Question 6 — Main characters group A/B: healthy and balanced

Group membership is **not** inference: `episodes.yaml` and session frontmatter carry a `team:` field, present on 60 of 64 sessions.

- **Group A** (since 2025-03-26): Dodo, Lindo Laut, Cookie, Esterossa, Rotunas, Lunara Velora, Nyrella, Gunther
- **Group B** (since 2026-06-04): Kaya, Sange, Saris, Bruma Stormrak

An exhaustive diff of „sessions that link the PC" against „data in its own chronology" is empty for **all 12 PCs** — the only area that is already fully correct. The word-count gap A vs. B is campaign age, not a quality deficit (normalized per session, B is denser). There are no cross-group interactions — the casts have never met.

**Locked down, not just measured:** `test_every_pc_chronologie_covers_every_linked_session` (new) pins this state, because the PC merges from this audit (`saris_bendal`→`saris` etc.) touch exactly these nodes.

## Question 7 (additional) — Conflict queue fires too rarely

Exactly **1** open conflict across 896 entities. Detection only fires on contradictions *within* one entity's evidence; identity problems *between* entities (questions 3+4) never produce a conflict file, even though `conflicts/README.md` foresees it for exactly this case. `pnp dedup` already finds them — all that is missing is somebody looking. No dedicated automation built (YAGNI, until it turns out that looking alone is not enough).

---

## Implemented

**Pipeline (`services/kb/src/pnp_okf/`):**
- `synthesize.py` / `cli.py` — `autolink_prose()`, wired up for all tiers (fix 1)
- `links.py` / `emit.py` — `normalize_body(self_id=...)`, degrades self-links (fix 4)
- `models.py` — `DEEP_MENTION_THRESHOLD` 8 → 5 (fix 2)
- `resolve.py` — **new finding from the real run:** hand-maintained registry aliases (`aliases:`, per the file header „appended to, never clobbered") never reached `link_targets()` — they survived only cosmetically in the file, without ever being linkable. `_load_preserved_aliases()` now seeds them in when a new entity is created.

**Tests (`services/kb/tests/`):**
- 5 new unit tests for `autolink_prose` (idempotence, `# Belege` boundary, headings, existing links) in `test_brief_local.py`
- 2 new tests for the alias-seeding correction in `test_rules_pins.py`
- 4 new ratchets/hard checks: deep-tier link coverage + faction/NPC relation coverage (`test_link_coverage.py`), citation coverage across all 4 formats + tier-vs-evidence reconciliation (`test_bundle_invariants.py`), article-variant duplicates (`test_rules_applied.py`)
- New file `test_audit_2026_08_29.py`: named regressions (22 duplicates, 4 content gates, hard pin test, self-link test, PC zero guarantee)
- `test_tiering_and_context.py::test_tiers` adapted to the new threshold

**Rules:**
- `entity_rules.yaml` — 25 duplicates folded (`merge:`/`split:`, 3 of them only became visible through the real run: `der_nebel`/`die_hoehle`/`die_falle` as article variants of the already ignored forms), 13 generic nodes (`ignore:`), 7 dead `important:` pins corrected/removed, `unimportant: deities/akastrale`, `alias_block:` for the ambiguous „Hans" collision
- `sources/Kanon_Entscheidungen.md` — Ring der Teleportation clarification after GM feedback
- `entity_registry.yaml` — `Lenra` added as an alias on `npcs/lenra` (now effective thanks to the `resolve.py` correction)

## Not fixed, deliberately

- **3 nodes without a source citation** (after the run: `deities/saris_patron`, `npcs/lord_kalidarn_von_willauch`, `npcs/nyruk` — the set fluctuates with every re-extraction) — the cause lies in `extract.py` (mention without `citation_ts`), outside this audit. Recorded only as a ratchet.
- **Stale `never_merge` justification** `miaomani`/`miyamani` — prose drift between the comment and the generated content is not meaningfully testable; GM question.
- **Identity conflicts do not land in the conflict queue** — `pnp dedup` already covers that, automation is YAGNI until the opposite shows.
- **`deities/sitravil`** — no successor concept findable, removed from `important:` instead of guessed. (`deities/gruul`, the other originally missing pin, reappeared by itself in the real run — with 1 piece of evidence correctly on `standard` tier, no pin needed, see below.)
- **5 pre-existing article duplicates** (`items/handschellen`, `items/das_tagebuch`, `npcs/balor`, `npcs/daemonenmagier`, `npcs/ratten_daemon`) — outside this audit's original list of 22, recorded only as a ratchet.

## Open GM questions (`sources/Kanon_Entscheidungen.md`)

`dunkler_paladin`/`belorus` (same figure?) · `vora`/`voras` · `gilde_in_breska` (faction or place?) · `untote_armee_von_steinbachtal` + `untote_horde_von_zebras` (separate formations or part of the one army?) · `rotunas_freunde`/`gefaehrten_von_rotunas` · `schlangenfigur`/`schlangengott` · `miaomani`/`miyamani` (justification stale) · `ringtal`/„Kleinringtal" (two places, one slug) · `der_waechter`/`waechter_des_berges` · successor for `deities/sitravil`.

**Newly put into the conflict queue by the real run** (`knowledge/conflicts/`, not yet reviewed by this audit): `locations__villau.md`, `npcs__der_seraph_vierter.md`, `npcs__harloen.md`, `npcs__meister_pyrandras.md` — each a self-contradictory evidence finding from the synthesis; per the documented process (`conflicts/README.md`) these go to the GM, not into this audit. The only previously open conflict (`locations__hartwacht`) was not reproduced by this extraction and was removed automatically by the pipeline run.

## Verification status — complete

Recorded before any change (as-is state): **2 tests already red**, independently of this work — `test_every_ruling_reaches_at_least_one_entity` (11 vs. baseline 9) and `test_unlinked_mentions_have_not_grown` (2485 vs. baseline 1871). Repo drift, not part of this audit.

`DEEPSEEK_API_KEY` was, contrary to the original assessment, available after all (via `.env`, not the shell environment) — `pnp run` ran for real, four passes:

1. **Run 1** — fix 1/2/4 + `entity_rules.yaml` parts A–F: 41 new, 387 changed, 64 pruned. Internal links 889 → 4513 (0 broken). Surfaced 2 further real bugs that only a real run could show: the `das_ende` split key (was missing on the actual extraction name „Das Ende" rather than „Ende") and the Hans name collision (see below).
2. **Run 2** — after correcting `das_ende` (split key) and `alias_block: Hans` plus a hand-maintained `Lenra` alias: revealed that registry aliases never arrived in `link_targets()` (see the `resolve.py` fix above) — cornivum→lenra stayed red.
3. **Run 3** — after the `resolve.py` fix: **broader cache invalidation than expected** — since now EVERY entity with maintained aliases gets a possibly changed alias list (not just the 3 concepts targeted for repair), the expensive deep-tier main characters (Dodo, Esterossa, Lindo Laut, Rotunas) among others triggered new model calls — 56 `calling DeepSeek` instead of the originally expected ~9. A deliberate, correct, but more expensive side effect of a real bugfix.
4. **Run 4** — after adding `der_nebel`/`die_hoehle`/`die_falle` to `ignore:` (article duplicates surfaced by run 3 itself): pure cache run, **0 new model calls**.

**Final state:**

```
172 passed, 1 xfailed
```

The one `xfail` is pre-existing and independent of this audit. All 9 originally named regressions from `test_audit_2026_08_29.py` are green.

| Ratchet | before | after |
|---|---|---|
| deep-tier nodes without a link | 53/60 | **0/73** (hard ceiling) |
| under-written nodes (≥5 mentions, no deep tier) | 9 | **0** (hard ceiling) |
| over-written nodes (≤1 mention, deep tier) | 5 | 6 — *legitimate increase*: 3 corrected `important:` pins now work as intended (see below) |
| factions with a member link | 22/42 | **31/40** |
| NPCs with a faction link | 31/228 | **46/218** |
| unlinked name mentions | 1871 | 1816 |
| dead rules (`entity_rules.yaml`) | 37 | **15** |
| article-variant duplicates | 12 | **5** (all pre-existing, outside the list of 22) |
| nodes without a source citation | 5 | 3 (extraction noise, out of scope) |
| concepts in total | 896 | 933 |

**On the „too deep" row (5→6):** not a regression. `important:` is, per its own docstring (`models.py`), „the escape hatch for entities the automatic rules underrate" — built for exactly this, lifting a thinly evidenced but central entity to deep tier. The three newly added cases (`bodrak_gott_der_stille`, `kaleandra`, `burg_des_belorus`) are exactly the pins this audit corrected from a dead concept_id to the right one — they now work as originally intended. Only `akastrale` had a real contradiction with its own `ENTSCHEIDUNG:` („kein umfangreicher Eintrag" — no extensive entry) — resolved via `unimportant:`.

**Spot checks, confirmed by content:**
- `items/ring_der_teleportation.md` now describes Lindo Laut's ring (GM-corrected during implementation)
- `locations/cornivum.md` links `npcs/lenra.md`
- `npcs/hans_soldat_aus_breska.md` no longer links to the wrong Hans
- `factions/koenigreich_zebros.md`, `npcs/belorus.md` now have links
- no more self-links in the bundle
- all 22 named duplicates from question 3 are gone

Ratchets finally lowered (see the commit history for the exact numbers per file): `UNLINKED_MENTION_BASELINE`, `DEEP_TIER_NO_LINK_BASELINE` (now a hard 0), `FACTIONS_WITH_MEMBER_LINK_BASELINE`/`NPCS_WITH_FACTION_LINK_BASELINE`, `too_shallow` (now a hard 0), `too_deep` (5→6, justified), `UNCITED_ENTITY_BASELINE`, `DEAD_RULES_BASELINE`, `ARTICLE_VARIANT_BASELINE`.
