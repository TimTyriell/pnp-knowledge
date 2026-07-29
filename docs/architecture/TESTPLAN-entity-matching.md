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

*Not run yet.*
