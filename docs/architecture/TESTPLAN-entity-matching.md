# Test plan — entity matching, measured before it is built

**Status:** planned, 2026-07-29. Nothing implemented; no pipeline code changes.
**Decides:** whether an alias-closure and/or phonetically normalised matcher
would have found the merges that were written by hand, and at which threshold.
**Related:** [IMPROVEMENTS.md](IMPROVEMENTS.md) I-001, I-002;
[ADR-001](ADR-001-knowledge-layer.md).

## Why this exists

`knowledge/entity_rules.yaml` grew from 16 to 267 `merge:` entries in seven
days. Before replacing or extending that mechanism, the cheap question is:
**how much of it could a matcher have found on its own?** The rules file is
already a labelled dataset — 259 confirmed positive links, 16 confirmed
negatives, 34 confirmed non-links by session. Answering the question costs a
script and zero LLM calls.

Every option in the phase-2 evaluation (alias closure, phonetic
normalisation, embeddings) is a bet on recall. This plan turns the bet into a
number *before* anything is built.

## Ground truth

Taken from `knowledge/entity_rules.yaml` and `knowledge/entity_registry.yaml`
at the same commit, so concept ids on both sides agree.

| Label | Source | Count | Meaning |
|---|---|---|---|
| **Positive** | `merge:` key → concept_id | 259 | this raw name denotes this concept |
| **Hard negative** | `never_merge:` groups | 16 | a human ruled these distinct |
| **Session-conditional** | `split:` (name, session) → id | 34 (14 names) | same string, different beings — must never link on the name alone |
| **Non-entity** | `ignore:` | 7 | must not link to anything |
| **Distractors** | registry concepts | 1019 | the candidate pool the matcher searches |

Two splits of the positives are reported separately, because they answer
different questions:

- **live (159)** — merge keys that still match a name in the current v5
  extraction cache. Predicts behaviour on future sessions.
- **stale (105)** — keys from earlier prompt generations that no longer fire
  (of which 6 are deliberate id pins). Predicts behaviour across a taxonomy
  change, which is expected roughly monthly.

## E1 — Name → concept linking (primary)

**Task.** Given a raw extracted name *N* and the set of registry concepts as
candidates, rank the candidates. The gold answer is the concept_id the hand
rule assigns.

**Variants.** Each is a drop-in replacement for `resolve._fuzzy_match`; none
is wired into the pipeline for this experiment.

| Id | Matcher |
|---|---|
| V0 | **Baseline.** `difflib.SequenceMatcher` on the concept-id slug, as shipped (`FUZZY_RATIO = 0.9`) |
| V1 | V0, but compared against `{slug} ∪ aliases` of each candidate (alias closure) |
| V2 | Kölner Phonetik on both sides, then difflib |
| V3 | Hand-written German equivalence classes (v≈w≈b≈f, d≈t, k≈g≈c, z≈s≈ts, ei≈ai, y≈i≈ü, collapsed doubles), then difflib |
| V4 | V1 + best of V2/V3 |

V2 and V3 are both listed on purpose: Kölner Phonetik maps `V→3` but `B→1`,
so it does **not** unify `vasul`/`basul` — one of the most frequent real
cases. Whether the plainer equivalence table beats the published algorithm on
this corpus is exactly what is unknown.

**Metrics.**

- `recall@1` and `recall@3` on positives, reported for live/stale/all.
- **False links on hard negatives:** count of `never_merge` pairs the matcher
  would link, at each threshold. This is the number that must stay at 0 for
  any variant proposed for the *automatic* pass.
- **Split violations:** count of `split:` names that link to a single concept
  on the name alone.
- **Threshold sweep** over 0.60–0.95 in steps of 0.05, so the operating point
  is chosen from the curve rather than guessed. Two operating points are
  reported per variant: the highest threshold with 0 false links (candidate
  for `resolve.FUZZY_RATIO`), and the threshold at 90 % recall (candidate for
  `dedup.SUGGEST_RATIO`).

**Unmeasurable by construction — state it, do not fake it.** Precision over
the whole candidate pool cannot be computed: a pair with no `merge:` rule is
not thereby proven distinct. So new links the matcher proposes that no rule
covers are **not** counted as errors. Instead: sample 30 of them at random,
review by hand, and report the hit rate as a separate, clearly-labelled
observation. That number is informative, not a metric.

**Leakage trap.** The 234 aliases in `entity_registry.yaml` were partly
produced by the very merges under test, so V1/V4 must run **leave-one-out**:
when scoring positive pair *(N → C)*, the alias equal to *N* (and its slug) is
removed from *C*'s alias set first. Without this, V1 scores near 1.0 and means
nothing.

## E2 — Generic-noun parent heuristic (secondary)

Tests the deterministic part of the `part_of:` proposal: can the parent
location be derived instead of pinned by hand?

**Task.** For each `split:` rule covering a generic noun (`mine`, `die mine`,
`kapelle`, `sumpf`, `seelenstein`, …), predict the parent from the session
alone, using the location concept with the most mentions in that session.

**Gold.** The hand-assigned concept and its `canonical_name:` pin, which
already name the parent in prose — `locations/sumpf_bei_nebelwacht`,
`locations/verlassene_mine_an_der_farm`, `items/haralds_seelenstein`. Mapping
those to a parent concept is a one-off manual step (≈14 names) and is part of
this experiment, not of the implementation.

**Metric.** accuracy@1 over the 34 split rules, plus the list of misses with
the reason (session visited several locations / the parent is an NPC not a
place / no location dominates).

**Decision value.** If accuracy is high, F4 stops being a per-session tax. If
it is low, the fallback is one hand-written `parent:` line per case — still
cheaper than today's 3 entries in 3 blocks, so E2 cannot fail outright; it
only sizes the saving.

## Acceptance criteria

Written down before the run, so the result decides and not taste.

1. **Adopt V*x* for the suggestion path** (`dedup.SUGGEST_RATIO`) if it lifts
   `recall@3` on the live positives by ≥ 15 points over V0 at a threshold
   where hard-negative false links ≤ 2. Rationale: a false suggestion costs
   one `never_merge:` line; a missed one costs a `merge:` line plus the time
   to notice it.
2. **Adopt V*x* for the automatic path** (`resolve.FUZZY_RATIO`) only if it
   reaches 0 false links on hard negatives **and** 0 split violations at its
   operating threshold. Anything else stays a suggestion — the automatic pass
   must remain conservative, since a silent misfold is what deleted Rotunas.
3. **If no variant clears (1)**, the string-matching path is at its ceiling
   and the phase-2 order changes: embeddings over mention notes (option C)
   move ahead of A/B.
4. **E2 adopts the heuristic** if accuracy@1 ≥ 70 %; below that, keep an
   explicit `parent:` entry per case and only take the derived-id part.

## Method notes

- Run against a **single commit** of `entity_rules.yaml` +
  `entity_registry.yaml`; concept ids drift between commits and would
  silently mis-score. Record the hash in the results table.
- Use the extraction cache in `services/kb/.cache/extract/` (57 sessions,
  1550 mentions, 1138 distinct names) — no re-extraction, no LLM, no cost.
- 105 stale keys and 3 dead `important:` pins are known and expected; they
  are data for the stale split, not bugs to fix inside this experiment.
- Normalisation runs on the **concept-id slug**, not on `canonical_name` —
  same reasoning as `resolve._tokens`: a display pin must not move merge
  decisions.

## Deliverables

- `services/kb/eval_matching.py` — standalone, argparse, no pipeline imports
  beyond `pnp_okf.okf.slugify` and the models. Prints the metric table and
  the sweep; writes nothing.
- A **Results** section appended to this file: variant table, chosen
  thresholds, the 30-sample review, E2 accuracy, and a one-paragraph verdict
  against the acceptance criteria above.
- The verdict becomes an entry in [IMPROVEMENTS.md](IMPROVEMENTS.md) (or an
  ADR if it changes the resolution architecture).

## Out of scope

No changes to `resolve.py`, `dedup.py` or `entity_rules.yaml`; no bundle
regeneration; no LLM calls; no embedding model. The `part_of:` frontmatter,
the cache-key split and the Whisper vocabulary list are separate pieces of
work that this measurement only informs.

## Results

Run 2026-09-22 at commit `0e90b31`, via `services/kb/eval_matching.py`
(no argparse — it follows `rules_doctor.py`/`spelling_doctor.py`'s shape
instead; there are no flags worth passing and `evaluate()` stays importable
for the test). Zero LLM calls, as planned.

### The corpus drifted, and one split inverted

| | planned (2026-07-29) | actual (2026-09-22) |
|---|---|---|
| `merge:` positives | 259 | **276** |
| `never_merge:` | 16 | **18** |
| `split:` | 34 / 14 names | **29 / 20 names** |
| `ignore:` | 7 | **144** |
| live / stale | 159 / 105 | **114 / 162** |

The live/stale split inverted. This is now mostly a *stale-taxonomy* test —
it measures recovery across a prompt-generation change more than behaviour on
future sessions. Also: **26 of the positives are trivial**, i.e.
`slugify(name)` already equals the target slug, so V0 gets them free and every
variant's floor is inflated by them.

### E1 — name → concept linking

`recall@3` on live positives, and hard-negative false links, at each threshold:

| t | V0 | V1 | V2 | V3 | V4 | false (V0/V1/V4) |
|---|---|---|---|---|---|---|
| 0.60 | 0.570 | **0.789** | 0.474 | 0.535 | 0.772 | 9 / 12 / 12 |
| 0.70 | 0.482 | 0.702 | 0.474 | 0.482 | 0.684 | 6 / 7 / 7 |
| 0.80 | 0.404 | 0.561 | 0.421 | 0.386 | 0.535 | 5 / 6 / 7 |
| 0.90 | 0.272 | 0.263 | 0.298 | 0.272 | 0.289 | **0** / 1 / 2 |
| 0.95 | 0.219 | 0.105 | 0.272 | 0.211 | 0.123 | **0** / **0** / 2 |

### Verdict against the acceptance criteria

**1 — suggestion path: NOT MET, by any variant.** V1 does lift live `recall@3`
by +21.9 points over V0 (0.789 vs 0.570) — but only at t=0.60, where it makes
**12** hard-negative false links, far past the ≤2 the criterion allows. At the
thresholds that satisfy the false-link bound, alias closure is *no better than
the shipped matcher*: at t=0.90 V1 scores 0.263 against V0's 0.272, and at
t=0.95 it collapses to 0.105 against 0.219. The lift and the safety never
coexist.

**2 — automatic path: only V1 @ t=0.95 qualifies** (0 false links, 0 split
violations) and its live `recall@3` is **0.105**, which is not a matcher worth
shipping. Worth recording about the current production setting: V0 at the
shipped `FUZZY_RATIO = 0.9` makes 0 false links but **2 split violations** —
the automatic pass is not as conservative as criterion 2 demands.

**3 — therefore this fires: the string-matching path is at its ceiling.** Per
the criterion as written, the phase-2 order changes and embeddings over mention
notes (option C) move ahead of alias closure and phonetic normalisation.

**4 — E2 rejected: accuracy@1 = 1/15 = 6.7%**, against a 70% bar. 5 of the 20
split names were dropped as having no derivable gold parent (two rules' own
comments say not to guess). The misses are not noise — they fall into two
named shapes: the session's dominant location simply is not the parent (10
cases), and in 3 `seelenstein` cases **the parent is a person, not a place**
(`characters/rotunas`, `npcs/abisalis_harald`), which the heuristic cannot
express at all. Keep an explicit `parent:` entry per case.

**V2 (Kölner Phonetik) was implemented and the testplan's prediction held.** It
never reaches 0 false links at any threshold and is dominated by V0 almost
everywhere. It is not worth its ~40 hand-written lines; V3's plain German
equivalence table beats it.

### The unruled-links sample found a live bug

The 30-sample review of proposed links no rule covers (`random.Random(0)`, so
it reproduces) surfaced something the experiment was not looking for. At
t=0.95, V1 proposes:

```
'evakuierung des halblingdorfs'      -> events/evakuierung_des_halblingsdorfs  (0.983)
'begegnung mit lanra'                -> events/begegnung_mit_landra            (0.974)
'heiliger streitkolben (aus zebras)' -> items/heiliger_streitkolben_aus_zebros (0.969)
'heilige treppe'                     -> locations/heilige_treppen              (0.966)
```

Those are exactly the pairs that tripped `check_rename_safety` on the same
day's v0.2 re-emit (see
[2026-09-22-rename-guard-override.md](../audits/2026-09-22-rename-guard-override.md)).
**They score 0.966-0.983, well above the shipped `FUZZY_RATIO` of 0.9, and
still did not merge** — because the resolver's fuzzy pass only compares
entities *within one run*. The corrected id exists solely in the registry, so
the two never meet.

`_load_preserved_aliases` (`resolve.py:388`) is supposed to cover this, but it
guards with `if concept_id and aliases:` — an entry with `aliases: []` is
skipped, so its `canonical_name` never becomes a reanchor candidate. A registry
entry whose alias list is empty *and* whose `canonical_name` no longer
slugifies to its own `concept_id` has **no anchor at all**:

```yaml
- concept_id: locations/taverne_in_willauch   # corrected
  canonical_name: Taverne in Willau           # mis-heard
  aliases: []                                 # nothing to match on
```

This is a better lead than anything E1 measured, and it is cheap: seeding the
reanchor candidates from `canonical_name` as well as `aliases` is a one-line
change. It is filed in [IMPROVEMENTS.md](IMPROVEMENTS.md) rather than made
here, because it moves resolution for all 1092 entities and wants its own
measured run.
