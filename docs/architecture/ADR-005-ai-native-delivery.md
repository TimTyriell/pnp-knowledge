# ADR-005 — AI-native delivery: rules as hooks, judgment at gates

**Status:** Accepted, 2026-11-03
**Applies to:** all three pipeline repos (`pnp-crawl`, `pnp-knowledge`,
`pnp-export-data`). Recorded here because this repo holds the architecture docs.
**Related:** ADR-002 (frozen `graph/`), `docs/plans/README.md`, `docs/QUALITY.md`

## Context

Most changes in these repos are written by Claude Code sessions, often several
in parallel, some on a smaller model working from a plan. Writing code stopped
being the slow part. What breaks now is the work around it: a session that
skips a rule, a paid run nobody asked for, a commit on the wrong branch, a diff
nobody reviewed with the repo's actual risks in mind.

Before this ADR the hard rules existed, but as prose: "never call DeepSeek",
"never edit `knowledge/`", "never bump a prompt version" in
`docs/plans/README.md`; "don't weaken the review gate" in pnp-export-data's
CLAUDE.md; "don't run the GPU stages as a test" in pnp-crawl's. Prose is
advisory. A model follows it most of the time, and the cost of the other times
is concrete: a cold rebuild is ~$6.50, a prompt-version bump renames concept ids
that wiki pages key on, an `--apply` writes to a public wiki. On 2026-10-26 a
parallel session switched the shared checkout's branch and a commit landed on
the wrong branch.

The structure follows Anthropic's *AI-native SDLC playbook*: every stage leaves
a versioned artifact the next stage reads; must-hold rules are deterministic
hooks, not instructions; humans own the gates, not the typing.

## Decision

Each rule lives in the cheapest layer that actually holds it.

| Layer | Holds | Where | Fails how |
|---|---|---|---|
| **Hook** (PreToolUse, exit 2) | Rules checkable from one tool call: path, command, value | `.claude/hooks/guard.ps1` per repo | Blocks the call, tells Claude why and which env var lets the human through |
| **CI** | Rules checkable from the tree: tests, ratchets, lint | `.github/workflows/ci.yml` | Red PR |
| **Review** | Rules that need judgment over a diff: a loosened ratchet, a widened retry, a weakened gate | `REVIEW.md` + `/review-pr` | One review comment, human merges |
| **Prose** | Context and *why* | `CLAUDE.md`, plans, ADRs | Nothing enforces it; nothing must-hold lives only here |

What the guards block, per repo (`python .claude/hooks/test_guard.py` proves
each rule and each override):

| Repo | Blocked | Override |
|---|---|---|
| pnp-knowledge | edits under `graph/` | none: frozen, thaw by editing the guard |
| | edits under `knowledge/` except `entity_rules.yaml` | `PNP_ALLOW_BUNDLE_EDIT=1` |
| | changing an existing `*_PROMPT_VERSION` | `PNP_ALLOW_PAID=1` |
| | `pnp run/extract/state/dedup` without `--estimate` | `PNP_ALLOW_PAID=1` |
| pnp-crawl | reading `*.mp3`; editing `audio/`, `transcripts_*` | none: re-run the stage |
| | running `01_download`, `02_transcribe`, `run_pipeline` | `PNP_ALLOW_GPU=1` |
| pnp-export-data | `04_upload.py --apply` | `PNP_ALLOW_WIKI_WRITE=1` |
| all three | `git commit` on `main` | `PNP_ALLOW_MAIN_COMMIT=1` |
| | edits to `.claude/hooks/`, `.claude/settings.json` (the guard itself) | `PNP_ALLOW_GUARD_EDIT=1` |

Overrides are switches in `.claude/guards.env`, one file per checkout,
gitignored, with every switch and its reason listed in the committed
`.claude/guards.env.example`. The guard re-reads it on every call. The guard
also blocks Claude from writing that file, by tool or by shell. An
environment variable of the same name on the Claude process works too. A
file was chosen over environment variables alone because the human has to be
able to find the switches without remembering them; every block message names
the switch and the file.

### The loop, stage by stage

| Stage | Artifact | Gate |
|---|---|---|
| Plan | `docs/plans/<ID>.md`: *Intent* (problem, outcome, constraints, open questions) | human writes or accepts the plan |
| Build | branch + commits from a `git worktree`; plan mode first | guards (hook) |
| Test | the plan's *Done when* commands; `verifier` subagent runs them in a fresh context and reports, never fixes | CI |
| Review | one comment per PR from `/review-pr`, policy in `REVIEW.md` | human merges |
| Paid / public step | `pnp run`, `04_upload.py --apply` | human only (guard override) |
| Maintain | run records (`state/history.jsonl`, crawl `status/`, export `runlog.py`), quality ratchets | a regression becomes a new plan |

Intent, plan and proof share one file instead of the playbook's separate
`intent.md` / `spec.md` / `plan.md`: one author, and the plan file is what a
reviewer and the verifier both read.

### Why review runs locally, by hand

`/review-pr <n>` runs on the Claude subscription, once per PR, triggered by the
human (`claude -p "/review-pr <n>"` for a clean context). A CI bot would need an
API key as a repo secret and pay per token for a few PRs a week. The playbook's
point is that every change gets a review with this repo's risks in mind before
merge. That holds either way.

## Deliberately not adopted

- **Statistical control bands over run history.** The playbook suggests rolling
  mean/σ bands on a production metric, with Claude invoked on a breach. The
  KB's `state/history.jsonl` has about a dozen runs with usage data, and they
  are bimodal: a cold rebuild is ~6.4M tokens, a warm run 0–0.4M, and
  `--limit` runs ingest a handful of sessions. A σ over that is dominated by
  the one cold run and flags nothing useful. The two risks bands would catch
  are already covered deterministically: cost, by `--estimate` before a paid
  run (now forced by the guard); quality drift, by the ratchets in
  `docs/QUALITY.md`, which compare every run to measured baselines. Revisit
  when there are enough runs of each kind to band separately.
- **Managed settings, Slack/Teams agents, OpenTelemetry.** Built for
  organisations enforcing policy across many engineers. One maintainer gets
  nothing from them.
- **An agent-behaviour eval suite** (20–50 tasks re-run when `CLAUDE.md` or
  hooks change). The evaluation effort goes to the pipeline's output instead
  (gold set, claim-level eval B3), which is what the system is judged on.
- **Auto-accept as the default.** The guards make it safer, but `pnp-crawl` is
  not lint-clean and two of its test scripts need private data, so CI can't
  yet catch what auto mode would let through.

## Consequences

- The guards stop the default path, not a determined one. The path rules
  check the Edit/Write tools, and a shell redirect writes past them. Closing
  that takes OS-level sandboxing, which the playbook names as the real
  control. Here the hook catches the honest mistake and review catches the
  rest.
- A blocked call is a rule, not a bug. Each CLAUDE.md says so, and each block
  message names its override.
- A must-hold rule is added by writing a guard case plus a `test_guard.py` case.
  A sentence in CLAUDE.md doesn't count.
- The guards cost about 0.35 s per Bash or Edit call (PowerShell startup), the
  price of putting enforcement in the hot path.
- Guards load from the repo's own `.claude/settings.json`, so they apply to
  sessions started in that repo or one of its worktrees. A session started in
  the parent folder needs the same three hooks registered there.
- pnp-crawl's lint is a ratchet: CI checks the `.py` files a PR touches, the
  same rule the local post-edit ruff hook applies, rather than a one-off
  reformat of pipeline code.
