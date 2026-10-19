# Implementation plans — pnp-knowledge

Written 2026-10-18 from the reviews in `../../../status.md`,
`../../../toWorkOn.md` and `../../../knowledgeAnalysis.md` (workspace root,
not tracked here). Each plan is **one branch, one PR**. Plans are ordered: do
them top to bottom unless a plan says otherwise. Every plan names its
dependencies.

Plans are written so that a small model (Haiku-class) can implement them
without design decisions. Where a decision *is* needed, the plan says
**STOP — ask the human** and gives the default to propose.

## Order

| # | Plan | Branch | Needs | Cost (DeepSeek) | Who |
|---|---|---|---|---|---|
| A1 | [A1-api-input-validation.md](A1-api-input-validation.md) | `fix/api-input-validation` | — | $0 | agent |
| A2 | [A2-narrow-llm-retries.md](A2-narrow-llm-retries.md) | `fix/narrow-llm-retries` | — | $0 | agent |
| A3 | [A3-script-paths-and-strays.md](A3-script-paths-and-strays.md) | `chore/script-paths-and-strays` | — | $0 | agent |
| A4 | [A4-split-prompt-versions.md](A4-split-prompt-versions.md) | `chore/split-prompt-versions` | — | $0 (must stay $0 — see plan) | agent |
| A5 | [A5-citation-grounding-ratchet.md](A5-citation-grounding-ratchet.md) | `test/citation-grounding` | A4 | $0 | agent + human (gold fix) |
| A6 | [A6-autolink-precision.md](A6-autolink-precision.md) | `fix/autolink-precision` | — | ~$0.05 warm re-emit (human) | agent + human |
| A7 | [A7-reconcile-docs.md](A7-reconcile-docs.md) | `docs/reconcile-with-code` | A1–A6 merged | $0 | agent |
| **T** | **[T00-tracking-model.md](T00-tracking-model.md) — design for the whole T-series. Read first.** | — | — | — | — |
| T1 | [T1-provenance-timestamps.md](T1-provenance-timestamps.md) | `feat/source-timestamps` | crawl C3 (episodes sync) | ~$0.05 | agent + human |
| T2 | [T2-teams-per-concept.md](T2-teams-per-concept.md) | `feat/teams-per-concept` | T1 | ~$0.05 | agent |
| T3 | [T3-rules-glossary.md](T3-rules-glossary.md) | `feat/rules-glossary` | A4 | $0 | agent + human review |
| T4 | [T4-event-anchors.md](T4-event-anchors.md) | `feat/event-anchors` | A6, T1 | ~$0.05 + GM list | agent + GM |
| T5 | [T5-state-pass.md](T5-state-pass.md) | `feat/state-pass` | A4, T3 | ~$2–4 one-time (human) | agent + human |
| T6 | [T6-thread-concepts.md](T6-thread-concepts.md) | `feat/thread-concepts` | T5 | $0 | agent |
| T7 | [T7-world-status-and-attitude.md](T7-world-status-and-attitude.md) | `feat/world-status` | T5 | $0 | agent |
| T8 | [T8-roster-and-player-guard.md](T8-roster-and-player-guard.md) | `feat/roster-player-guard` | crawl C4 | $0 | agent + human |
| T9 | [T9-summary-uses-state.md](T9-summary-uses-state.md) | `feat/summary-open-threads` | T6, T7 | $0 | agent |
| B1 | [B1-opaque-ids.md](B1-opaque-ids.md) | `feat/opaque-concept-ids` | T-series merged | $0 | agent, cross-repo |
| B2 | [B2-anchored-extraction.md](B2-anchored-extraction.md) | `feat/anchored-extraction` | B1, T3 | **~$6.50 rebuild (human)** | agent + human |
| B3 | [B3-claim-level-eval.md](B3-claim-level-eval.md) | `test/claim-eval` | A5 | $0 (+ human labelling) | agent + human |

Cross-repo plans live in their own repos: `pnp-crawl/docs/plans/`,
`pnp-export-data/docs/plans/`.

## Rules for the implementing agent (read before every plan)

1. **Branch from `origin/main`** after `git fetch`. Local `main` is stale
   (`8246f55`); `origin/main` is `a87bf11` or newer. Command:
   `git fetch origin && git switch -c <branch> origin/main`.
2. **Never call DeepSeek.** No `pnp run`, `pnp extract`, `pnp dedup`,
   `pnp state` without `--estimate`. A step that needs a paid run is marked
   **HUMAN RUN** — stop there, write what you need into the PR description,
   and hand over.
3. **Never edit `knowledge/`** except where a plan explicitly says so. The
   bundle is written by `pnp run`, not by hand. `knowledge/entity_rules.yaml`
   is hand-written and may be edited when a plan says so.
4. **Never bump `PROMPT_VERSION` / `EXTRACT_PROMPT_VERSION`** unless the plan
   says so. A bump re-extracts the whole corpus (~$6.50) and renames concept
   ids (PIPELINE.md §4, §6).
5. Tests run from `services/kb` with its own venv:
   `cd services/kb && .venv/Scripts/python.exe -m pytest -q`.
   Lint from repo root: `ruff check .` (ruff 0.16.6, as in CI).
   Known pre-existing red test:
   `test_bundle_invariants.py::test_last_run_conflict_count_matches_the_committed_queue`
   — only red locally because `state/last_run.json` is untracked and stale
   (A7 fixes the process). Do not "fix" it by editing `last_run.json`.
6. Use the Write/Edit tools for Python source with backslashes, not bash
   heredocs (PIPELINE.md §11 trap 2).
7. Follow the repo's comment style: comments explain *why*, cite the incident
   or doc that motivated them. Match the surrounding code.
8. Commit message: Conventional Commits, imperative, ≤72 char subject, body
   explains why. End with the attribution line the session gives you.
9. Open the PR with `gh pr create --base main`. PR body: what, why, how
   verified (paste test output summary), and any HUMAN RUN steps left.
10. Write the tests first. This repo ships a `test-driven-development` skill
    in `.claude/skills/`; follow it when one is available to you.
11. If anything in a plan does not match the code you see (a function moved,
    a line number is off by a lot, a test already exists), **STOP and report**
    instead of improvising. Line numbers are from 2026-10-18; anchor names
    (`def …`) are authoritative.
