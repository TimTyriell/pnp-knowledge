# Review policy — pnp-knowledge

Read by `/review-pr` (`.claude/commands/review-pr.md`) and by human reviewers.
Hooks already block the run-time mistakes (`.claude/hooks/guard.ps1`); review
catches what only shows in a diff. Ruff and CI catch style and broken tests:
don't repeat them.

## Always report

1. **Ratchet loosening.** A baseline in `services/kb/tests/` moves the wrong
   way without a dated comment naming what moved it, or a detector is
   narrowed until the count passes. See `docs/QUALITY.md`: a weakened detector
   is worse than none.
2. **Money.** A new or widened path to DeepSeek; a change to what keys the
   extraction/synthesis caches (a silent cold rebuild, ~$6.50); a
   `*_PROMPT_VERSION` bump the PR doesn't call out; retries widened beyond the
   errors that are actually transient.
3. **The read-only boundary.** The KB API (`:8070`) gaining a write path, or
   code outside `pnp run` writing to `knowledge/`. The boundary is the
   architecture (ADR-001); `pnp-export-data` relies on it.
4. **Privacy.** This repo is public; `knowledge/` is a private repo because it
   holds player names. Real names, transcripts or bundle content in tracked
   files, fixtures, logs or commit messages.
5. **Concept-id stability.** Anything that renames concept ids without a
   migration (PIPELINE.md §4, §6): downstream wiki pages key on them.
6. **Frozen and guarded paths.** Edits under `graph/` (ADR-002); changes to
   `.claude/hooks/` or `.claude/settings.json` that remove or loosen a rule.
7. **Tests.** New behaviour without a test; a bug fix without a test that
   failed before it.

## Skip

Formatting and import order (ruff), naming taste, refactors the PR didn't
attempt. At most 3 nits, marked as nits, after everything else.

## Language

Docs and code comments in English; generated data (`knowledge/`, `reports/`,
prompts' German examples) stays German. Flag either leaking into the other.

## Output

One review comment. Findings most severe first, one per line:
`path:line — problem — fix`. No praise, no summary of the diff. Last line:
`Merge: yes` / `Merge: after fixes` / `Merge: no`, and why in one clause.
The human merges.
