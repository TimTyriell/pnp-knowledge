# A7 — Make the docs say what the code does

| | |
|---|---|
| Branch | `docs/reconcile-with-code` |
| Base | `origin/main` (after A1–A6 merged, so counts are current) |
| Depends on | A1–A6 |
| Cost | $0 |
| Size | M (writing, not code) |

## Goal

The engineering docs are this repo's strongest portfolio evidence, and
several claims in them are false today. Each false claim undercuts the true
ones. Fix every item below, either by correcting the doc or, where noted, by
a tiny code change. Every number written must be reproducible by a command
written next to it. That is the repo's own rule; see the README's "Reproduce
the counts".

## Checklist (one commit per group is fine)

### Counts

- [ ] `README.md`: concepts and sessions. Currently "1092 / 66"; the real
      numbers were 1114 / 68 on 2026-10-18, and they change after T4. Find the
      existing "Reproduce the counts" command, run it, and paste the output.
      Don't type a number by hand.
- [ ] `docs/architecture/PIPELINE.md` §1 "Suite: 266 passed" and §10 "254
      tests": replace with the current `pytest -q` summary line plus the date.
      Fix §1 "1158 concept files / 6382 internal links" the same way, with the
      command that produced it.
- [ ] `docs/architecture/ARCHITECTURE.md` §1 inventory (says 42 sessions,
      mentions `pnp-report`): update to the three-repo split and current
      counts, or replace the table with a pointer to README's counts section.

### Claims that are false

- [ ] **Tags / as-of.** README:33 and ADR-001 §1 say "tag per session; as-of =
      read at tag". There are **0 tags**, and `summary.py --as-of s26`
      can't work. Decide (**STOP — ask the human**, default **a**):
  - **a.** Keep the feature; write `docs/RELEASING.md` (5 lines): after
    merging an ingest PR, run `git tag s<NN> && git push origin s<NN>`. Tag
    the current `main` once as the baseline (human). Add to README that
    as-of reads are only as good as the tags.
  - **b.** Drop it: remove `--as-of` from the `summary.py` docstring
    examples, and mark ADR-001 §1's temporal model "not implemented (no
    tags); as-of = any commit sha".
- [ ] **ADR-001 §3 / ARCHITECTURE risk 8**: "Synthesis receives the current
      concept + new evidence" and "synthesis always starts from the current
      concept body". False: `context.py:6-10` says hand-written prose in a
      bundle file is overwritten. Add an "Outcome (2026-10)" note to ADR-001:
      "GM edits go to `knowledge/entity_rules.yaml` and `knowledge/sources/`
      (ENTSCHEIDUNG:/DARSTELLUNG:), not to bundle files. A bundle file is
      regenerated." Don't rewrite history; append.
- [ ] **ADR-001 "per-session `## Historie` bullets"**: not implemented. Note
      it in the same Outcome block; deep tier has `## Chronologie`, and T6/T7
      add `## Verlauf` / `## Stand`.
- [ ] **ADR-003:13** "Exactly one of those stages calls a language model":
      `services/summary/summary.py` also calls DeepSeek (ephemeral output,
      never persisted). Amend the sentence to say so and why that's within
      the spirit of the ADR (the KB stays the only *persisted* LLM output).
- [ ] **"Typed relationships"** (PR #13 title, any doc that repeats it):
      `links.py` says "Deliberately untyped". Fix any doc wording; add
      "typed edges" to IMPROVEMENTS.md as a proposal (see
      `knowledgeAnalysis.md` §3.1).
- [ ] **Prompt asks for relative links** (`prompts.py`, SYNTH_SYSTEM: "Beginne
      Pfade NIEMALS mit /") while emit writes absolute links (4727 absolute,
      1 relative). **Don't edit the prompt here.** That changes
      `SYNTH_SYSTEM` and trips A4's pin. Add the item to a new section in
      IMPROVEMENTS.md, "Batch with the next SYNTH_PROMPT_VERSION bump".
- [ ] **Two files called PIPELINE.md.** `docs/PIPELINE.md` describes
      pnp-crawl stage 1. Rename it to `docs/CRAWL-STAGE-1.md` (`git mv`) and
      fix inbound links: `grep -rn "docs/PIPELINE.md" --include=*.md .`.
- [ ] **CLAUDE.md** says "Knowledge edits arrive via `ingest/s<NN>` branches
      … tagged `s<NN>` per session on merge". Align with the tags decision
      above.
- [ ] **ADR-004 trigger 4** says "a re-extraction trips the 2% guard". On
      2026-09-22 a *cached* re-emit tripped it
      (`docs/audits/2026-09-22-rename-guard-override.md`). Add one sentence:
      identity moves even without the model, which strengthens the case for
      B1.

### Process fix: the stale `last_run.json` test

`services/kb/state/last_run.json` is **untracked**. It describes run
`20260922T231332Z` (Event 309, conflicts 18), while the committed bundle
came from the 22:58Z run (305 / 16). So
`test_last_run_conflict_count_matches_the_committed_queue` is red on this
machine only.

- [ ] Add one paragraph to the test's docstring: it compares *local* state to
      the committed bundle, so after `git checkout` of another branch it can
      be red with nothing wrong. The fix is a warm `pnp run` (HUMAN) or
      deleting the stale local `state/last_run.json`.
- [ ] Skip the test (don't fail it) when `last_run.json` is older than the
      newest commit touching `knowledge/conflicts/`. Implement with
      `git log -1 --format=%ct -- knowledge/conflicts` against
      `ended_at`. Skip reason: `"state/last_run.json predates the committed
      conflicts queue -- re-run pnp run"`. Add a unit test with a tmp git repo
      in the style of `tests/test_api.py`'s fixture.

### Branch hygiene (HUMAN, list in the PR)

- [ ] Local `main` is at `8246f55`, while `origin/main` is `a87bf11` (the
      `fix/i004-canonical-name-reanchor` work is already on origin/main). Run
      `git switch main && git merge --ff-only origin/main`.
- [ ] Delete merged local branches: `git branch --merged main`.

## Verify, commit, PR

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
grep -rn "1092\|66 sessions\|266 passed\|254 tests" README.md docs/ CLAUDE.md   # → nothing stale
```

Message (per group): `docs: reconcile <topic> with the code`

## Done when

- [ ] Every checklist item is ticked, or deferred with a reason in the PR.
- [ ] Every number in README/PIPELINE has a command next to it.
- [ ] The full suite is green locally, including the `last_run` test or its new skip.
