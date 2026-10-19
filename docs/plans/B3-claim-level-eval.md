# B3 — Claim-level evaluation (human-verified)

| | |
|---|---|
| Branch | `test/claim-eval` |
| Base | `origin/main` (after A5 merged) |
| Depends on | A5 (`grounding.py`) |
| Cost | $0 LLM. **Human labelling time: ~2–3 h for 60 claims** |
| Size | M |

## Goal

Measure whether the bundle's *statements* are true, not just whether entity
names exist. Build:

1. a **sampler** that draws N claims from the bundle, stratified by type and
   tier, each with its cited session, timestamp and the transcript window
   around it;
2. a **label file format** a human fills in, one verdict per claim:
   `supported` / `unsupported` / `misattributed` / `claimed_not_observed` /
   `unclear`;
3. a **scorer test**: the supported rate overall and per stratum, with
   baselines set from the first human-labelled run (a ratchet).

The current gold (3 sessions, 71 names, AI-drafted) can't see the failure
classes found on 2026-10-18: an attribution swap (Esterossa/Cookie), an NPC
retelling stored as fact (Rotunas), a diarization error (Miqo/Kip bear), and
a rules misreading (Dodo "1 HP"). This eval can.

## Design

- **What a claim is:** one sentence from an entity body (brief tier: the
  note; standard/deep: a sentence from `## Überblick` or `## Chronologie`)
  that carries a citation marker or sits in a single-source entity.
- **Sampling:**
  - `random.Random(seed)`, seed recorded in the file;
  - strata: type ∈ {Character, NPC, Location, Item, Faction, Event/anchor,
    Thread}, crossed with tier ∈ {brief, standard, deep};
  - target 60 claims, at least 5 per non-empty type;
  - skip sentences under 6 words.
- **Evidence shown to the labeller:** transcript lines in ±90 s of the
  cited timestamp. Reuse `context.excerpts_for`-style windowing, or the
  plain segment filter from `grounding.py`. Include the speaker labels.
- **File:** `services/kb/tests/data/claims/<date>-<seed>.yaml`.

```yaml
seed: 1234
drawn: 2026-10-20
claims:
- id: c001
  concept: events/sturz_von_dodo
  type: Event
  tier: brief
  claim: "Dodo überlebt den Sturz mit einem Hitpoint."
  session: 2025-06-10_RF_cLkCu3Iq3y8
  at: '01:12:40'
  url_at: https://www.youtube.com/watch?v=cLkCu3Iq3y8&t=4360s
  window: |
    [01:12:31] Spieler (Dodo): dann ist es ein Hitpoint
    ...
  verdict: ''          # supported | unsupported | misattributed | claimed_not_observed | unclear
  note: ''
```

  The transcript window holds real speaker labels with player names. Those
  are already in the transcripts, which are private (pnp-crawl). Decide
  (**STOP — ask the human**) whether claim files may be committed to this
  repo. Default: commit them with speaker labels replaced by the character
  name or "Spieler" via a small scrub (keep the part in parentheses), so no
  player first names land in git.

## Steps

1. `services/kb/claim_sampler.py` (script):
   `python claim_sampler.py --n 60 --seed 1234 > tests/data/claims/<date>-1234.yaml`.
   Pure read of the bundle and the transcripts; no LLM.
2. `src/pnp_okf/claims.py`: `split_claims(body) -> list[str]` (sentence
   split that respects German abbreviations like "z. B.", "ca.", "Nr.") and
   `score(labels) -> dict` (rates per stratum, excluding `unclear`). Unit
   tests for both.
3. `tests/test_claim_eval.py`:
   - skips with the reason "no human-labelled claim file" until a file has
     ≥50 non-empty verdicts;
   - then asserts `supported_rate >= CLAIM_SUPPORTED_BASELINE`;
   - the baseline comment explains its origin, as in
     `test_extraction_quality.py`.
4. Docs: PIPELINE.md §10 gets a paragraph on "three measures —
   name-level gold, citation grounding, claim-level eval — what each can
   and can't see".
5. **HUMAN:** label the 60 claims (open each `url_at` if the window isn't
   enough). Set the baseline from the result minus the noise margin (the
   file explains it: with n=60, ±~12pp).

## Done when

- [ ] Sampler, scorer and test merged.
- [ ] First labelled file committed (scrubbed); baseline set; result reported in README's quality section with the command to reproduce it.
