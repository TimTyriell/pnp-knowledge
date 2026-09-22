# Migration: prompt v5 → v6 bundle regeneration

**Status:** done (2026-09-23)
**Trigger:** `b0ba16b` ("Enhance synthesis context with secondary sources and routing directives") bumped `PROMPT_VERSION` `"5"` → `"6"` in `services/kb/src/pnp_okf/prompts.py`.
**Pre-migration commit:** `b93c0c3` (bundle as built under prompt v5)

## Why this migration is not optional

The extraction and synthesis caches are both keyed on `PROMPT_VERSION`
(`extract.py:_cache_key`, and the same pattern in `synthesize.py`):

```
key = sha256(PROMPT_VERSION + model + session_id + dialogue)
```

So the v6 bump invalidated every cached LLM output at once. The bundle
committed at `b93c0c3` was produced under v5; the code that reads and
regenerates it is v6. Until the bundle is rebuilt, the system of record and
the code that maintains it disagree, and every `pnp run` re-derives all 66
sessions from scratch.

Re-extraction resamples the model, which rewords entity names, which changes
the *derived* concept id. Measured on the first attempt:

```
ERROR pnp_okf.emit: [resolve] refusing to proceed: 432/868 previously known
concept(s) (>10%) are absent from this run's resolved entities
```

432 of 868 — half the bundle. The `--allow-rename` guard did exactly its job
and wrote nothing. This is the second time this has happened; `rules_doctor.py`
was written for the 2026-08 mass-rename and applies unchanged here.

## What a full rebuild costs

Measured on the 2026-09-05 migration, not estimated.

A rebuild re-derives every session and every non-brief concept, so the bill
scales with the whole corpus rather than the change:

| | |
|---|---|
| Extraction input | 66 sessions x ~30k tokens (~94k chars of German each) |
| Structured-outputs probe | the **same payload again**, once per uncached session |
| Synthesis | ~235 calls (deep 73 + standard 162); the 864 brief concepts make no call |
| Total | **~10.5M tokens**, ~$8 |

DeepSeek bills peak rates 01:00-04:00 and 06:00-10:00 UTC on weekdays and
off-peak everything else, weekends included -- exactly half. The 2026-09-05
run was a Saturday, so ~$8 is the *floor*; the same rebuild on a weekday
morning is ~$15.

Two things follow:

1. **A `PROMPT_VERSION` bump is a budgeted event.** Bumping a one-character
   constant in `prompts.py` invalidates every cached extraction and synthesis
   at once. Schedule it off-peak, and batch prompt changes rather than
   shipping them one at a time -- three separate bumps cost three rebuilds.
2. **Changing `DEEPSEEK_MODEL` costs the same**, because the model name is in
   the cache key too. Settle the model *before* starting a rebuild. The
   2026-09-05 run paid for extraction roughly twice by switching from
   `deepseek-chat` to `deepseek-v4-pro` at 40% through.

The probe was ~35% of that day's tokens before it was memoised per model
(`extract.py`, `_NO_STRUCTURED_OUTPUTS`); it now costs at most one probe per
worker instead of one per session, saving ~1.9M tokens per cold rebuild.

Extraction is also parallel now (`--workers`, default 8). Before that it was
a serial loop and the same rebuild took ~4 hours of wall clock instead of
~30 minutes; the cost was unchanged, only the time.

## Pre-flight (done)

- Working on branch `chore/docs-ci-and-instrumentation`, tree clean.
- Old bundle is committed at `b93c0c3` — `git checkout b93c0c3 -- knowledge/`
  restores it at any point. **This is the rollback.**
- Id + title snapshot taken before regeneration (933 rows). Without the
  *titles* the old→new rename map cannot be reconstructed, because the id is
  derived from the title.

## Steps

### 1. Regenerate

```bash
cd services/kb
pnp run --transcripts <transcripts_final> \
        --bundle ../../knowledge/bundle/splitter_des_ewigen \
        --allow-rename --allow-prune
```

Both guards must be released: `--allow-rename` for the >10% missing-id check,
`--allow-prune` because the orphaned v5 files then exceed the 10% prune
ceiling. Run detached — this re-synthesises every standard/deep concept, so it
is the expensive call-heavy path, not a warm re-emit.

**Closed 2026-09-23.** Ran under `deepseek-v4-pro`; committed as `9ca1d77`
("regenerate bundle under prompt v6 / deepseek-v4-pro").

### 2. Build the rename map

Match old ids to new by **title**, not by id — the title is what survived and
the id is what changed.

```bash
# new ids+titles, same shape as the pre-regen snapshot
for f in $(find knowledge/bundle/splitter_des_ewigen -name '*.md' ! -name 'index.md'); do
  id=${f#knowledge/bundle/splitter_des_ewigen/}; id=${id%.md}
  printf '%s\t%s\n' "$id" "$(sed -n 's/^title: *//p' "$f" | head -1)"
done | sort > ids_after.tsv

join -t$'\t' -j2 <(sort -t$'\t' -k2 titles_before.tsv) <(sort -t$'\t' -k2 ids_after.tsv) \
  | awk -F'\t' '$2!=$3 {print $2" -> "$3}' > rename_map.txt
```

Titles that appear in only one side are genuine drops/additions, not renames —
list those separately and eyeball them. A dropped title with real content is
the failure mode to catch here.

**Closed 2026-09-23.** Rename map built and tracked in
`docs/audits/2026-09-05-v6-identity-cleanup-handoff.md` (`renamed.tsv`,
`dropped.tsv`, `added.tsv`, `kept.tsv` — 18 renamed / 524 dropped / 757 added /
399 kept).

### 3. Fix dead rules

`entity_rules.yaml` pins target concept ids, and a renamed id silently
orphans its rule. The repo already has the diagnostic:

```bash
cd services/kb && python rules_doctor.py
```

A rule is dead when its target id no longer exists in the bundle. Update each
dead target to the new id from the rename map. Do **not** delete a dead rule
without checking the map — a rule pointing at a renamed concept is still
wanted, just misaddressed. `test_rules_applied.py` ratchets this
(`DEAD_RULES_BASELINE`), so the number is measurable before and after.

**Closed 2026-09-23.** Repointed per
`docs/audits/2026-09-05-v6-identity-cleanup-handoff.md` Task 2 (54 dead →
repointed or escalated); `0e90b31` additionally pinned the seven mis-heard
names back to their corrected ids.

### 4. Re-measure every ratchet

All 15 baselines were measured against the v5 bundle and are now meaningless
as written.

```bash
cd services/kb && python -m pytest -v
```

For each failure, decide deliberately — the existing comments in
`test_link_coverage.py:43-83` are the model for how to record this:

- The metric genuinely improved → **lower** the baseline. Ratchets tighten.
- The v6 prose is richer and legitimately raises a count (this happened
  before, 1889 → 1912) → raise it, and **write down why in the comment**, not
  just the number.
- A hard-`0` invariant broke (`DEEP_TIER_NO_LINK_BASELINE`,
  `UNREACHED_RULING_BASELINE`, `AMBIGUOUS_PERSON_RULING_BASELINE`,
  duplicate headings, too-shallow stubs) → **that is a real regression.** Fix
  the pipeline, do not move the constant. Per `test_canon_decisions.py:48-51`:
  *"A baseline that can be raised is an invitation to raise it; this is a fact
  about the file, not a ceiling to negotiate."*

**Closed 2026-09-23**, later than the rest of this migration. Finished on the
`docs/audits/2026-09-22-rename-guard-override.md` branch, which re-measured
`check_rename_safety` itself (35/1092 → 28, then 27/1107 on a second run) and
led to the I-004 fix; several `docs/QUALITY.md` baselines carry 2026-09-22
dated comments as a result (e.g. `UNCITED_ENTITY_BASELINE` raised 1 → 5,
diagnosed as detector false positives rather than fixed by widening the
regex). All hard `0`s held.

### 5. Re-check name-spelling drift

`canonical_name:` pins a title only; nothing rewrites prose, so a mishearing
baked into v5 bodies is re-derived fresh under v6 and the drift set changes.

```bash
cd services/kb && python spelling_doctor.py
```

Compare against `SPELLING_DOCTOR_TOTAL_BASELINE` and the
label/target mismatch baselines (see `docs/QUALITY.md` for current numbers).

**Closed 2026-09-23.** Missing spelling rules added per
`docs/audits/2026-09-05-v6-identity-cleanup-handoff.md` Task 3
(Breschka/Cepros/Willau/Willoch/Tavok/Tarvok variants).

### 6. Re-check duplicates

Re-extraction re-splits entities the model previously merged, and vice versa.

```bash
cd services/kb && pnp dedup          # writes a report only, no mutation
```

Feed confirmed merges through `entity_rules.yaml` `merge:` and re-run;
`never_merge:` protects the pairs already ruled distinct. The prior run
flagged cross-type collisions worth re-confirming: `factions/sanddorn` vs
`locations/sanddorn`, `deities/heiliger_duran` vs `npcs/heiliger_duran`, and
`npcs/der_seraph` vs its three ordinals.

**Closed 2026-09-23.** Duplicate persons merged per
`docs/audits/2026-09-05-v6-identity-cleanup-handoff.md` Task 5 (cookie/perry,
canfield_lobrecht/lobrecht/kapitaen, voras, waechter trio, wirt, die_gilde,
sanddorninseln).

### 7. Validate the emitted bundle

```bash
cd services/kb && pnp validate --bundle ../../knowledge/bundle/splitter_des_ewigen
```

Broken links should be 0. Note this only checks links that were *written* —
`test_link_coverage.py` measures the mentions that never became links, which
is the number that actually moves under a resynthesis.

**Closed 2026-09-23.** `pnp validate` writes no artifact by design, so there
is no file to point to; the evidence is the guard/validator output recorded
in `docs/audits/2026-09-22-rename-guard-override.md` (35/1092 abandoned ids
→ 28 after triage, 27/1107 on a repeat run — the trail that led to I-004).

### 8. Reconcile the downstream wiki page map

**This is the cross-repo step and the easiest one to forget.**
`pnp-export-data/wiki_pages.toml` maps concept ids to wiki pages. Every
renamed id that appears there is now a dangling reference.

```bash
cd ../pnp-export-data
grep -oE '"[a-z_]+/[a-z0-9_]+"' wiki_pages.toml | tr -d '"' | sort -u > referenced_ids.txt
# any id here that is not in ids_after.tsv is broken
```

Then a dry run to confirm nothing downstream breaks:

```bash
python 01_inventory.py && python 02_extract.py && python 03_generate.py
```

Stage 3 is dry-run by default and writes to `proposals/` only. Do not run
stage 4 as part of this migration.

**Closed 2026-09-23, differently than written above.** No inventory/extract/
generate dry run was recorded; `pnp-export-data/wiki_pages.toml` was instead
edited directly (`deities/ezhura` removed, reconciliation comment at lines
34-37, dated 2026-09-05) per
`docs/audits/2026-09-05-v6-identity-cleanup-handoff.md` Task 6. It now
references 5 concept ids, 0 dangling.

### 9. Commit

Bundle content and the tests that measure it must land together — a commit
where the baselines describe a different bundle than the one beside them is
the state this migration exists to end.

```
chore(knowledge): regenerate bundle under prompt v6

Re-extraction under PROMPT_VERSION 6 renamed N of 868 concept ids.
Rename map in docs/architecture/MIGRATION-prompt-v6.md.
Ratchet baselines re-measured; <list any raised, with reason>.
```

**Closed 2026-09-23.** Bundle regeneration landed as `9ca1d77`; identity
cleanup as `b3f1af3` and `0e90b31`; the later ratchet re-measurement and
I-004 fix as `0c4e7a0` / `9261d79` on this branch.

## Rollback

```bash
git checkout b93c0c3 -- knowledge/
```

Restores the v5 bundle exactly. The caches stay v6, so the next `pnp run`
will want the rename again — rollback buys time, it does not close the gap.
