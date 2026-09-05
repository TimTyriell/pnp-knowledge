# Quality ratchets

The knowledge bundle in `knowledge/` is machine-generated German prose. Prose
has no compiler, so the usual defence — a test that asserts the one correct
answer — does not apply to most of what can go wrong with it. A concept can be
uncited, written up at length from a single mention, linked to the wrong
namesake, or carry a Whisper mishearing into every body it was ever synthesized
into, and every one of those files still parses, still validates, and still
renders.

So `services/kb/tests/` carries a second class of test alongside the ordinary
correctness ones: **measured baselines that are not allowed to quietly grow.**
Each one counts a defect shape across the whole real bundle, compares that count
against a number written into the test, and fails when the count moves the wrong
way. The number is not a target. It is the value that was actually measured on a
real `pnp run`, with a comment beside it recording when it was measured and what
moved it.

## Why several baselines are deliberately not zero

A gate that demands zero on a fuzzy signal gets satisfied by weakening the
detector, and a weakened detector is worse than no detector. Three of these
counts are dominated by known, triaged false positives:

- **Unlinked mentions (1912).** A body mentioning "der Turm" is not always the
  concept `locations/turm`. Forcing every name occurrence into a link would
  over-link ordinary German. The number measures link *coverage*, which is a
  gradient, not a correctness gate.
- **Raw spelling-doctor hits (307).** The fuzzy mishearing detector flags
  legitimate shortened references — "Die Gilde" for "Die Gilde von Ehrenfels" is
  62 hits on its own. Those are triaged by hand in
  `docs/audits/2026-08-30-spelling-sweep.md`. The noise floor is watched so that
  a *new* mishearing cannot hide inside it.
- **Uncited entity concepts (1).** The last remaining one is a false positive of
  the citation regex, diagnosed and then deliberately left in place rather than
  fixed by loosening the regex — see
  [The uncited 1 is a detector false positive](#the-uncited-1-is-a-detector-false-positive).

Two more are non-zero because the underlying behaviour is *designed*:
`important: true` is documented as the escape hatch that forces a deep-tier
writeup onto a low-mention but pivotal entity, so six such entries are the
feature working, not six defects. And 15 dead `entity_rules.yaml` entries are
rules whose target dropped out of a non-deterministic re-extraction — real debt,
tracked as debt, repaid by re-running or editing the rules, never by raising the
number.

## The three kinds of baseline

The distinction matters more than the numbers themselves. Each metric is
classified by whether its defect shape has a known, complete fix.

### Hard ceilings — must stay 0

A pattern whose complete fix is known and has been applied. Zero is a fact about
the system, not a ceiling to negotiate; a non-zero value means a fix regressed
silently.

| Metric | Baseline | Source |
| --- | --- | --- |
| Concepts with >=5 mentions but no deep tier | 0 | `services/kb/tests/test_bundle_invariants.py:273` |
| Deep-tier concepts with zero outgoing links | 0 | `services/kb/tests/test_link_coverage.py:159` |
| Duplicate headings in canon decisions | 0 | `services/kb/tests/test_canon_decisions.py:51` |
| GM rulings reaching no entity | 0 | `services/kb/tests/test_canon_decisions.py:55` |
| Rulings ambiguously grounded | 0 | `services/kb/tests/test_canon_decisions.py:61` |

The three canon-decision constants were ratchets against a measured baseline
back when ruling-to-entity routing was slug-substring matching and the file
could only be nudged downward. After `context.py` was rewritten to route on an
explicit `<!-- okf: entity=... -->` directive, that reason was gone and they were
re-classified as hard zeros. From the module docstring: *"A baseline that can be
raised is an invitation to raise it; this is a fact about the file, not a ceiling
to negotiate."*

### Ratchets — must not grow

A measured count on a signal with irreducible noise, or on real debt being paid
down. It may only go down. Raising one requires a written justification in the
comment beside it.

| Metric | Baseline | Source |
| --- | --- | --- |
| Plain-text mentions not linked | 1912 | `services/kb/tests/test_link_coverage.py:83` |
| Raw spelling-doctor hits | 307 | `services/kb/tests/test_spelling_sweep.py:163` |
| Distinct label/target link mismatches | 14 | `services/kb/tests/test_spelling_sweep.py:219` |
| Occurrences of those mismatches | 23 | `services/kb/tests/test_spelling_sweep.py:220` |
| Dead `entity_rules.yaml` entries | 15 | `services/kb/tests/test_rules_applied.py:53` |
| German article-variant duplicate slugs | 5 | `services/kb/tests/test_rules_applied.py:234` |
| Deep-tier writeups built from <=1 mention | 6 | `services/kb/tests/test_bundle_invariants.py:264` |
| Entity concepts with no citation line | 1 | `services/kb/tests/test_bundle_invariants.py:179` |

### Floors — must not drop

Relation coverage runs the other way: the count may only go *up*. Kept as
absolute counts rather than percentages, so that a shrinking denominator (a merge
rule folding two factions into one) cannot silently mask a numerator regression.

| Metric | Baseline | Source |
| --- | --- | --- |
| Factions linking >=1 member | 30 / 40 | `services/kb/tests/test_link_coverage.py:214-215` |
| NPCs linking >=1 faction | 46 / 219 | `services/kb/tests/test_link_coverage.py:216-217` |

The assertion is written as `fac_with_member >= min(BASELINE, len(factions))`,
so removing a faction is allowed and losing a member link is not.

## What a ratchet's history looks like

The unlinked-mention baseline moved four times across three regenerations. It is
quoted here in full because the comment is the artifact: a ratchet that only ever
tightens is a policy, but one that was consciously *loosened* once, with the
reason and the counter-evidence recorded, is a judgement call someone had to
defend.

Note in particular the third move. It goes the wrong way, it says so in capital
letters, and it records that the fix plan's own prediction about the number was
wrong.

`services/kb/tests/test_link_coverage.py:43-83`:

```python
# Unlinked mentions of another entity's name, measured on this branch. A
# body mentioning another concept's name in plain prose is exactly the
# "nodes not linked correctly" symptom reported for this bundle — the count
# was previously unmeasured (validate.py cannot see it; see module
# docstring), so this baseline is the first real measurement, not a design
# target. Lowered from 1871 to 1816 after a real `pnp run` applied Fix 1
# (autolink_prose) and the alias-seeding fix (resolve.py). Ratchet: it may
# only go down.
#
# 2026-08-30 spelling-drift branch: raised 1816 -> 1889. Folding
# factions/untote_horde_von_zebras into factions/belorus_untotenarmee (a
# spelling-split duplicate, see entity_rules.yaml) gave npcs/belorus.md a
# real new DeepSeek resynthesis with more grounding and more prose — richer,
# correct content, most of whose repeat name mentions are un-autolinked by
# design (autolink_prose only links a name's first occurrence per line). Not
# a linking regression; a byproduct of removing a duplicate identity.
#
# 2026-08-30 review-fix branch: RAISED 1889 -> 1912. This is the one ratchet
# move on the branch that goes the wrong way, and it is deliberate; the number
# was watched across three regenerations rather than set once.
#
# Measured 1867 (a *drop* of 22) after the code fixes alone: the ambiguity
# guard in link_targets() cost 12 names, but _linked_concept_ids() no longer
# letting a directory-qualified link (deities/foo) shadow an unrelated
# cross-type namesake (npcs/foo) more than paid for it. So the fix plan's
# prediction that the guard alone would raise this was wrong.
#
# The rise came from the two GM rulings that followed, plus one alias_block,
# and every point of it is a *wrong* link being refused:
#   - "Flüchtlinge" (~40 occurrences): the GM ruled the Ringtal refugees a
#     different group from Roland's, so factions/fluechtlinge exists again as
#     its own node and its bare generic name is blocked from autolinking.
#   - "Die Stadt": was an alias of locations/ehrenfels, so the ordinary noun
#     linked to Ehrenfels on 10+ pages including locations/sanddorn,
#     seelenwacht, boragdil and hartwacht — pages where it meant that page's
#     own city. Blocked.
#   - "Ende", already blocked earlier in the branch, same shape.
# A generic noun linked to one arbitrary concept is worse than plain text.
# Do not "fix" this by unblocking those aliases; the links it buys back are
# the wrong ones.
UNLINKED_MENTION_BASELINE = 1912
```

## The uncited 1 is a detector false positive

The other half of the same discipline: the last remaining defect was
investigated until it was understood, and then *not* fixed, because the only
available fix was to blunt the measurement.

`services/kb/tests/test_bundle_invariants.py:156-179`:

```python
# Entity concepts with zero recognizable citation line in any of the four
# formats. Was 5 on the pre-run bundle; a real `pnp run` (with re-extraction
# picking different entities each time) settled at 3. Ratchet: may only go
# down. Root cause is in extract.py (a mention without a citation_ts), out
# of scope for this audit's fixes — see docs/audits/2026-08-29-bundle-quality.md.
#
# 2026-08-30 review-fix branch: tightened 3 -> 1 after the regeneration.
# emit_entity now backfills a missing "# Belege" section from the entity's
# own mentions (the section was only ever a prompt instruction, never
# enforced), which repaired the standard-tier pages the model had shipped
# without one.
#
# Correcting the attribution above while here: the single remaining entry,
# deities/saris_patron, is NOT a missing-citation_ts case and is not in fact
# uncited. Its page carries a real citation with a real timestamp and URL —
# "[S1-02-B] Transkript der Session vom 23. Juli 2026, 01:48:07. Online
# verfügbar unter https://..." — which _CITATION_LINE_RE simply does not
# match, because the regex wants the literal word "Session" straight after
# the marker and the model wrote "Transkript der Session vom" instead. So
# this last 1 is a 5th citation-line variant the detector doesn't know, i.e.
# a false positive of the measurement, not a defect in the bundle. Left at 1
# deliberately rather than widening the regex: loosening a detector to reach
# zero would also blind it to genuinely uncited pages.
UNCITED_ENTITY_BASELINE = 1
```

## Running them

```bash
cd services/kb
python -m pytest tests/test_bundle_invariants.py tests/test_link_coverage.py \
                 tests/test_canon_decisions.py tests/test_spelling_sweep.py \
                 tests/test_rules_applied.py
```

All five files are `skipif`-guarded on the bundle being checked out: they
measure the real `knowledge/` bundle, not a fixture, and a checkout without
`knowledge/` skips them rather than passing vacuously.

Alongside the ratchets, `tests/test_audit_2026_08_29.py` holds the other shape —
named, individually verified regressions from a specific audit: a concept id
that must stop existing, a claim a specific body must or must not make. Those
are not counts, and they are not negotiable.

## What this does not measure

Honest limits, so the numbers are not read as more than they are.

- **Truth.** Nothing here checks that a cited claim is what actually happened at
  the table. A citation is verified to *exist* and to name a real session and
  timestamp; whether the synthesized German sentence faithfully represents that
  moment of the recording is unchecked, and unauditable without a human
  listening to the transcript.
- **Prose quality.** Readability, tone, redundancy between sections, and whether
  a deep-tier entry is worth reading at all are entirely outside these
  measurements.
- **Link correctness — only link presence.** The floors count *whether* a
  faction links a member, not whether it links the *right* one. The
  label/target mismatch ratchet is the closest proxy, and it catches shape, not
  semantics.
- **Recall.** There is no measurement of what extraction missed. Every count is
  taken over what was extracted; a character never mentioned in any extraction
  pass is invisible to all fifteen numbers.
- **The composition of the noise floor.** The spelling ratchet notices that the
  total grew; it does not say which hit is new. Identifying that is a manual
  triage step by design (`spelling_doctor.py` plus the audit document).
- **Run-to-run stability.** Extraction is non-deterministic — entity counts swing
  by dozens between full rebuilds of the same pipeline. Several baselines are
  therefore measurements of one particular regeneration, which is exactly why
  every move is dated and attributed in a comment rather than just edited.
