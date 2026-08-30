# Review fix plan: `fix/kb-autolink-and-entity-dedup` → `main`

Code review of the branch before merge. Follow-up to
`2026-08-29-bundle-quality.md` (identity/link audit) and
`2026-08-30-spelling-sweep.md` (prose spelling drift) — this document reviews
the *result* of both and plans the fixes for what they broke or missed.

**Status when written:** branch is 22 commits ahead of `main`, fast-forwards
clean, `pytest` in `services/kb` green (195 passed, 1 xfailed). None of the
fixes below have been applied yet.

The rules and registry changes are sound: every `important:`/`unimportant:`/
`canonical_name:`/`alias_block:` key resolves to a real registry concept, and
the `spelling:` map is coherent with `sources/Kanon_Entscheidungen.md`. **The
regenerated bundle is where the defects are** — the regeneration flipped one
mislink, dropped one page's citations, orphaned one open conflict, and left
index blurbs stale. The suite is green because two of the three criticals sit
on code paths with no assertions at all, and the third is inside
`UNCITED_ENTITY_BASELINE = 3`'s existing tolerance.

## Read this first: regeneration is nearly free

`cli.py:190-197` autolinks **after** the synthesis cache read, and
`services/kb/.cache/synth/` holds 1008 pre-autolink bodies. A `pnp run` after
rules-or-code-only changes relinks and re-emits the whole bundle with **zero
new LLM calls**; the last full run took 4m26s (`services/kb/state/last_run.json`).

So: batch every content-affecting fix, then regenerate once. The only LLM call
this plan spends is the single deleted Hartwacht cache entry (§2.2).

## Decisions already taken

- Scope: blockers + mediums. The LOW findings are listed under *Deferred*.
- Hans-class mislink: fix **both** the data asymmetry and the root cause in
  `link_targets`.
- The 12 colliding names that look like genuine unmerged duplicates: **report
  only**, no merges applied — entity merges are GM rulings (§2.3).

---

## 1. Code fixes

### 1.1 `link_targets` must refuse ambiguous names — `synthesize.py:41`

Today the loop is last-write-wins over entities sorted by ascending mention
count, so a name owned by two concepts silently links to whichever is better
attested:

```python
for entity in sorted(entities, key=lambda e: len(e.mentions)):
    for name in [entity.canonical_name, *entity.aliases]:
        ...
        best[name] = entity
```

Drop any name claimed by 2+ concepts instead of picking a winner. Measured
impact: exactly **12 names** out of 1145 in the target table — `Bugbears`,
`Die Mine`, `Mine`, `Erscheinen von Nerash`, `Flucht durch das Portal`,
`Gilde in Breska`, `Heiliger Duran`, `Kampf gegen die Ghule`,
`Kampf gegen die Pilz-Goblins`, `Sanddorn`, `Seelenstein`, `Seelenwacht`.
The docstring's "better-attested entity wins" sentence becomes wrong; update it.

**Test:** two `CanonicalEntity` fixtures sharing an alias; assert the shared
name is absent from `link_targets(...)` while each qualified canonical name
survives. Home: `tests/test_alias_block.py`.

**Ratchet impact — read before starting.** This *raises*
`UNLINKED_MENTION_BASELINE` (`tests/test_link_coverage.py:43-49`, currently
1889), a ratchet documented as "may only go down". Those 12 names now stay
plain text. The trade is intended: a wrong link is worse than no link.

**Recorded dissent:** the design pass recommended *deferring* this, on the
grounds that moving a one-way ratchet the wrong way converts a
silent-good-guess bug into a ratchet move deserving its own audit. It was
included anyway. Mitigation: **land 1.1 as its own commit** so it can be
reverted independently of the criticals, and write the reason for the raise
into the ratchet comment rather than just bumping the number.

### 1.2 Symmetric `alias_block` for Hans — `entity_rules.yaml:1139` (CRITICAL)

1.1 does **not** fix Hans. `alias_block` runs upstream in `resolve.py:598,664`,
so by the time `link_targets` sees the pair the innkeeper's alias is already
stripped and the name no longer looks ambiguous. Add the missing side:

```yaml
  npcs/hans_soldat_aus_breska:
  - hans
```

The rule's own comment at `:1144-1152` already states the intent ("only drops
the ambiguous bare name") — it was applied to one side only. Result:
`bundle/.../npcs/hans_wirt_zum_gruenen_sichelmond.md:12` currently renders

```
[Hans](/npcs/hans_soldat_aus_breska.md) ist der Wirt der Taverne „Zum grünen Sichelmond"
```

i.e. the innkeeper's own name links to the soldier — the same bug the branch
set out to fix, pointing the other way.

**Test:** `entity_rules.yaml` has a `split:` section (`:581` is the Hans pair)
listing concepts known to share a name. Assert that **for every `split:` pair,
no bare name survives as an alias on more than one member** — closes the class,
not just Hans. Home: `tests/test_alias_block.py`.

Note `tests/test_rules_applied.py:182 test_alias_blocks_are_honoured` already
verifies every `alias_block` entry generically against the real post-run
bundle, so the new YAML entries in 1.2 and 2.1 get bundle-level coverage free.

### 1.3 `pnp validate --fix` never degrades self-links — `validate.py:270-278` (CRITICAL)

```python
concept_ids = [str(p.relative_to(bundle_dir).with_suffix("")).replace("\\", "/") for p in files]
...
for path in files:
    original = path.read_text(encoding="utf-8")
    new_text, unresolved = normalize_body(original, index)   # <- no self_id
```

`fix_bundle` **already computes `concept_ids` in the same order as `files`**
(`validate.py:255-258`) to build the index — it just doesn't use them in the
loop. Change to `for path, cid in zip(files, concept_ids):` and pass
`self_id=cid`. Both `emit.py` callers (`:160`, `:299`) already pass it; this is
the one caller that forgets, so the self-link degradation only fires on a full
`pnp run`, never on the retro-apply path.

**Test:** `tests/test_spellings_apply.py` already has a
`# --- fix_bundle retro-apply` section (`:76`) with two `tmp_path` bundle tests
to copy. Add `test_fix_bundle_degrades_a_self_link`: write `npcs/foo.md` whose
body links `[Foo](/npcs/foo.md)`, run `fix_bundle(bundle)`, assert plain text.

### 1.4 `normalize_body`'s `None == None` trap — `links.py:263`

```python
return label if (cid is None and drop_unresolved) or cid == self_id else match.group(0)
```

With `self_id` at its `None` default, an **unresolved** link satisfies
`cid == self_id` and collapses to plain text even when `drop_unresolved=False`
asked for it to be preserved. Guard explicitly: `cid is not None and cid == self_id`.
Dormant today (the only `self_id`-omitting caller uses the `drop_unresolved=True`
default — and 1.3 removes even that), but it is baked into the public contract.

### 1.5 Backfill missing citations — `emit.py:283-323` (`emit_entity`) (CRITICAL)

The `# Belege` section is only an **instruction to the model**
(`prompts.py:140-141`) for standard/deep tiers. Nothing enforces it:
`emit_entity` writes the body as-is, `validate.py` has no citation check.
`npcs/lord_kalidarn_von_willauch` (standard tier, 3 mentions) is the one entity
in the bundle where the model didn't comply — and its **cached** body already
lacks the section, so a rerun alone will not fix it.

Only the brief tier is code-guaranteed, via `render_brief_body`
(`synthesize.py:158-164`):

```python
lines = [body, "", "# Belege", ""]
for i, m in enumerate(entity.mentions, start=1):
    marker = "" if m.quality == "hoch" else f" [Transkriptqualität: {m.quality}]"
    lines.append(f"{i}. Session {m.date} @ {m.citation_ts} ({m.url}){marker}")
```

Extract that loop into a shared helper; have `emit_entity` append it when the
body has no `# Belege` heading (`_BELEGE_HEADING_RE` already exists at
`synthesize.py:96`). Post-cache step, so it repairs cached bodies with no LLM call.

**Check this before implementing.** `UNCITED_ENTITY_BASELINE`'s own comment
(`tests/test_bundle_invariants.py:156-160`) blames a *different* root cause for
the other uncited entities — "a mention without a `citation_ts`" in
`extract.py`. Confirm from `.cache/extract/` that Kalidarn's 3 mentions
actually carry `citation_ts`/`url`; if they don't, this helper emits
half-empty citation lines and the fix belongs in `extract.py` instead. The
registry stores only `mention_count`, so this cannot be checked from
`entity_registry.yaml`.

An alternative design (guard inside `synthesize_entity_body`, rewriting the
cache file in place so future hits are pre-healed) was considered and rejected:
`emit_entity` runs on every path every time and needs no cache mutation.

**Test:** `tests/test_bundle_invariants.py` — emit an entity whose body lacks
`# Belege`, assert the written file has one built from its mentions.

### 1.6 Session index blurbs bypass the spelling map — `emit.py:191-192` and `:240`

`emit_indexes` applies `apply_spellings` only inside `_entry`, the per-type
entity path; its `spellings` param never reaches `sessions/index.md` at all.
The session blurbs are built earlier, in **`emit_sessions`**, at two
`entries.append` sites that both go straight to `_short_desc`:

```python
entries.append((title, f"{date}.md", _short_desc(extraction.recap, 100)))              # :191-192
entries.append((title, f"{date}.md", str(frontmatter.get("description") or "")[:100])) # :240, no-transcript path
```

That is why `bundle/.../sessions/index.md:29,36` still read "Turnier von
Willau" / "Bereska" while the pages they link say "Willauch" / "Breska" — both
keys **are** in the spelling map (`entity_rules.yaml:1038`, `:1042`), so this
is a missed call site, not a missing key.

`emit_sessions` already receives `index: ConceptIndex | None`, which already
carries `.spellings`, and `apply_spellings` is already imported in `emit.py` —
no new parameter threading:

```python
apply_spellings(_short_desc(extraction.recap, 100), index.spellings if index else {})
```

Fix **both** sites.

**Test:** `tests/test_incremental_ingest.py` already exercises `emit_sessions`
— call it with `ConceptIndex([], spellings={"Willau": "Willauch"})` and a recap
containing "Willau", assert the entry's third tuple element says "Willauch".

### 1.6b The spelling sweep missed two concept renames

`events/index.md:267` reads "Turnier von Willau" for a *different* reason than
1.6: the concept itself was never renamed. The registry still holds
`events/turnier_von_willau` (`entity_registry.yaml:1526`) and
`locations/arena_von_willau` (`:2749`) with matching canonical names — even
though `entity_rules.yaml` states the intended outcome twice: *"arena_von_willauch,
never willau"* (`:164`, `:973`). The town got its `canonical_name:` pin
(`:974`) and the Lord got his (`:981`); these two did not.

Data fix: add `canonical_name:` pins for both plus `merge:` keys for the old
spellings, following the pattern used for `npcs/lord_kalidarn_von_willauch` at
`:252-258`. This changes concept **ids**, so `check_rename_safety` applies (it
runs as part of a full `pnp run`, skipped only on `--session`/`--limit` partial
runs) and the old paths should prune as orphans.

### 1.7 Basename-only "already linked" guard — `synthesize.py:100-107`

```python
return {cid for cid in set(targets.values()) if cid in paths or cid.rsplit("/", 1)[-1] in slugs}
```

A linked `deities/foo` marks `npcs/foo` as already-linked, so a real mention
goes unlinked. `validate.py`'s own `cross_type_slugs` check exists because such
collisions are expected, and §1.1's collision list (`Bugbears`, `Sanddorn`,
`Seelenwacht`, `Gilde in Breska`, `Heiliger Duran`) shows it is live. Match on
the full concept id; keep the bare-slug fallback only for links written without
a directory segment, resolving those through the directory the link names.

### 1.8 `autolink_prose` per-line × per-name scan — `synthesize.py:110-141`

The branch turned a single pass per name over the whole text into a nested
per-line × per-name loop; the `linked` check short-circuits only the inner
regex call, not the outer iteration. The only new requirement was *skip heading
lines*. Restore the whole-text single pass and exclude heading lines in the
regex/callback instead of splitting the body into lines. Same targets, same
idempotency, one pass.

Note: this is a code-shape fix, not a measured regression — the run is
dominated by I/O and (when cold) LLM calls, and the relink pass is CPU-only
under a thread pool. If it turns out to cost nothing measurable in Phase 3,
downgrade it to *Deferred* rather than churning the function.

**Test:** existing autolink tests must pass unchanged; add one asserting a name
appearing only inside a `#`-heading is not linked (locks the behaviour the line
loop was introduced for).

---

## 2. Data fixes (`knowledge/`)

### 2.1 Block bare generic nouns — `entity_rules.yaml`

Follow the precedent at `:1155-1163` (`amulett`, `kristall`): qualified aliases
stay linkable, only the ambiguous bare noun is dropped.

- `locations/ende_jenseits_der_orkgebiete`: block `ende` and `das ende`
  (registry `:3002-3003`). Live symptom: `am [Ende](/locations/ende_jenseits_der_orkgebiete.md)`
  on the Kalidarn page, where "Ende" is the ordinary German noun.
- `factions/fluechtlinge_aus_breska`: block `flüchtlinge`. The bare noun is a
  **merge** key at `:147` (identity-level), but the visible defect at
  `bundle/.../events/verhandlung_um_die_aufnahme_der_fluechtlinge_in_ringtal.md:13`
  is a *link*, not a fold — so blocking linkability while leaving the merge
  intact is the smaller, safer change.

### 2.2 Hartwacht: the conflict was not resolved, the model stopped flagging it (CRITICAL)

`conflicts/*.md` are generated unconditionally each run (`emit.py:326`) and
pruned by `prune_conflicts` (`emit.py:370`), so the deleted
`conflicts/locations__hartwacht.md` cannot be restored by hand. On `main` the
body carried:

```
# Offene Konflikte

- Beleg 1 bezeichnet Hartwacht als Stadt … Beleg 2 … uneinnehmbare Orkfestung.
```

The resynthesized body **dropped the heading entirely** and folded the
contradiction into prose (`bundle/.../locations/hartwacht.md:19`: "gilt als
uneinnehmbare Orkfestung; zugleich wird sie als Stadt beschrieben").
`split_conflicts` found no heading, `still_open` lost the concept,
`prune_conflicts` deleted the file — and logged it as
`"conflict resolved, removed from queue"`, which is not what happened.

`.cache/synth/locations__hartwacht.json`'s stored body has no
`# Offene Konflikte` section either, so the miss is baked into the cache and a
plain rerun reproduces it exactly. The prompt (`prompts.py:137-139`) tells the
model to omit the section when it finds no contradiction, so this is a model
judgment call, not a deterministic bug — `emit.py:265`'s "keine
widersprüchlichen Belege" phrase-matching branch is never even reached
(`split_conflicts` returns at the `idx < 0` check).

Three parts, cheapest first:

1. **Delete that one cache entry** (`services/kb/.cache/synth/locations__hartwacht.json`)
   before the Phase 3 run. Costs exactly one LLM call — no `--force`.
2. **Reword the prune log line** (`emit.py:391`) to say the run no longer
   reports the conflict, not that it was resolved. It is the only signal a
   human gets that a queued conflict vanished.
3. **If the fresh synthesis still doesn't flag it**, stop there and record a GM
   ruling on Hartwacht (Stadt vs. uneinnehmbare Orkfestung) in
   `sources/Kanon_Entscheidungen.md` instead. Do **not** tune the synthesis
   prompt to force the flag — that is a riskier, bundle-wide change.

### 2.3 Duplicate-candidate report (no changes applied)

The 12 colliding names from §1.1 fall into three shapes. Report them for GM
review; apply no `merge:`/`never_merge:` without a ruling.

- **Cross-type pairs** — `factions/bugbears` ↔ `npcs/bugbears`,
  `factions/sanddorn` ↔ `locations/sanddorn`,
  `factions/seelenwacht` ↔ `locations/seelenwacht`,
  `factions/gilde_in_breska` ↔ `locations/gilde_in_breska`,
  `deities/heiliger_duran` ↔ `npcs/heiliger_duran`.
- **Date-suffixed event pairs** — `events/kampf_gegen_die_ghule` ↔
  `…_2026-03-10`, plus the Nerash / Portal / Pilz-Goblins pairs.
- **Genuinely distinct same-name concepts** — the two mines, the two
  Seelensteine. These want `never_merge:`, not `merge:`.

---

## 3. Regenerate once, then re-measure

All of §1 and §2 are rules-or-code changes, so **one** `pnp run` covers them:
warm synth cache (1008 entries), autolink and emit rerun on cached bodies,
exactly one LLM call (the Hartwacht entry deleted in §2.2). Commit the
regenerated `knowledge/bundle/`, `knowledge/entity_registry.yaml` and
`knowledge/conflicts/` as one commit, separate from the code and test commits.

Then re-measure and update, writing the reason into the existing comment blocks
(the file already distinguishes plain ratchets from hard ceilings — follow that):

| Baseline | File | Now | Expected move |
|---|---|---|---|
| `UNLINKED_MENTION_BASELINE` | `tests/test_link_coverage.py:43` | 1889 | **Up** — §1.1 refuses 12 ambiguous names by design. Document as intentional. |
| `UNCITED_ENTITY_BASELINE` | `tests/test_bundle_invariants.py:161` | 3 | **Down** — §1.5 backfills, if the citation-data check passes. |
| `SPELLING_DOCTOR_TOTAL_BASELINE` | `tests/test_spelling_sweep.py:156` | 340 | Measured 270 *before* these fixes; re-measure and tighten. |
| `LABEL_TARGET_MISMATCH_BASELINE` / `_OCCURRENCE_BASELINE` | `tests/test_spelling_sweep.py:205-206` | 20 / 26 | Measured 9 / 9 *before* these fixes; re-measure and tighten. |

Tighten **after** the run, never before — a pre-run tightening measures the
about-to-change bundle. The other ~10 baselines were independently re-measured
during review and match reality exactly; leave them alone.

---

## Deferred

- `deities/akastrale` listed in both `important:` (`entity_rules.yaml:1084`)
  and `unimportant:` (`:1133`) — shadowed and inert (`resolve.py:472-473`
  computes `flagged - suppressed`). Pure cleanup.
- Stale docstring at `tests/test_audit_2026_08_29.py:13-16` claiming the tests
  are "expected to be RED on this branch" — all 10 pass since the bundle was
  regenerated in `530677f`. They are now a regression net; say so.
- `_suspect_title_dups` (`validate.py:693-714`) copy-pasting
  `_suspect_person_dups`' O(n²) pairwise `SequenceMatcher` loop — already
  marked `# ponytail: O(n^2) per type` and fine at current scale. Merging them
  risks changing the person-specific token-subset check; factor out only if a
  third such check appears.
- `apply_merges.py:157` targets `npcs/lord_kalidarn_von_willau` (no "ch"), a
  concept id that no longer exists — the merge was later done directly via
  `entity_rules.yaml:252-258`. Dead line in a one-off script.
- The 12 duplicate candidates themselves (§2.3 reports, does not merge).
- `DEEP_MENTION_THRESHOLD` 8→5, changed in the same branch as the autolink
  rework. Confirm it was intentional; if not, revert separately. Not blocking.

---

## Verification

```bash
cd services/kb

# 1. Unit tests before regeneration — the new tests in 1.1-1.6 must fail
#    first (they encode defects that are live right now), then pass.
./.venv/Scripts/python.exe -m pytest -q

# 2. Drop the one stale cache entry (§2.2), then regenerate. Warm cache =>
#    exactly one LLM call; expect ~4-5 min. Watch the log for the reworded
#    prune line and the tier counts.
rm .cache/synth/locations__hartwacht.json
./.venv/Scripts/python.exe -m pnp_okf.cli run

# 3. Full suite again, on the regenerated bundle.
./.venv/Scripts/python.exe -m pytest -q

# 4. Cheap link/spelling retro-pass; must now degrade self-links (§1.3).
./.venv/Scripts/python.exe -m pnp_okf.cli validate --fix
```

Then, from the repo root:

```bash
# Hans: the innkeeper's own name must no longer link to the soldier.
grep -n "hans_soldat" knowledge/bundle/splitter_des_ewigen/npcs/hans_wirt_zum_gruenen_sichelmond.md

# Citations: must print nothing but index.md.
for f in knowledge/bundle/splitter_des_ewigen/npcs/*.md; do
  grep -q "Belege\|Quellen" "$f" || echo "$f"
done

# Generic nouns: no bare "Ende" linked as a location.
grep -rn "\[Ende\](/locations/" knowledge/bundle/ | head

# Stale index blurbs: must come back empty.
grep -n "Willau\b\|Bereska" knowledge/bundle/splitter_des_ewigen/sessions/index.md

# Renames (§1.6b): old ids gone.
grep -n "turnier_von_willau\b\|arena_von_willau\b" knowledge/entity_registry.yaml

# Hartwacht (§2.2): back in the queue, or documented as a still-missing flag.
ls knowledge/conflicts/ | grep hartwacht
```

Finally check `services/kb/state/last_run.json` — `ok: true`, `conflicts_open`
accounted for (was 4; Hartwacht returns only if the fresh synthesis re-flags it
or a canon ruling is added per §2.2), and `dropped_links` not spiking.

---

## Open questions for the GM

Neither can be answered from the bundle; both are recorded rather than guessed.

1. **Hartwacht** — Stadt or uneinnehmbare Orkfestung? Needed only if the fresh
   synthesis in §2.2 still fails to flag the contradiction.
2. **Flüchtlinge** — are the Ringtal refugees the same group as
   `factions/fluechtlinge_aus_breska`? If *not*, the `merge:` key at
   `entity_rules.yaml:147` is also wrong and needs scoping to qualified phrases
   or a per-session `split:`. Blocking the link (§2.1) is correct either way,
   so no fix is blocked on this answer.
