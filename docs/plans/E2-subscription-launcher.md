# E2 — Subscription launcher, run history and scheduled runs

## Intent

E1 built a rigorous offline harness, but it has produced no score: every model task
(35 per graded run) had to be launched by hand. Wanted: one command per phase that runs
the model tasks on the Claude Code and Codex subscriptions, resumes after a usage limit,
records every scored run in a history that only compares comparable runs, and can run on
a schedule. The first number must come before the gold is approved: packet A (claims and
citations against the transcript) needs no gold.

Constraints:

- Subscriptions only. No API key, no provider SDK; the launcher aborts if a key is set.
- `extraction_benchmark.py` stays offline (its AST and socket tests unchanged). A separate
  module, `bench_launch.py`, is the only code that starts a model. This amends E1's
  "the Python harness never launches a model": the harness still doesn't; the launcher is
  started by the human or by a scheduler the human registered.
- Every E1 launch rule (EXTRACTION-BENCHMARK.md §5) holds. Added: no silent model fallback,
  Codex tool use rejected, quota stops one host only, no launch from an agent session.
- Claude Pro quota is small (2026-11-15: a 5-hour window ended after ~3 heavy Opus calls).
  Packet A first; per-host stop; resumable reruns.
- Published history carries no campaign text: whitelisted fields only.

Human decisions, 2026-11-18: scheduled runs use two cross-family judges with disagreements
kept as bounds and no human step; aggregate results are published in `docs/benchmarks/`;
grade provisionally now, approve gold later. Codex judge `gpt-6.1-sol` high, Claude judge
effort high, inventory stays Opus.

## Steps

1. `extraction_benchmark.py` (offline): refuse entity judgments without boolean
   `type_ok`/`subtype_ok` (was a KeyError mid-score); `per_judge_F` beside `per_judge_Q`
   (F needs no gold, so it is the self-preference column); `history_rows`,
   `record_history` (called by `score_run`), `render_leaderboard`, `regressions`, CLI
   `leaderboard`. Tests: group 18 in `tests/test_extraction_benchmark.py`.
2. `bench_launch.py`: `argv_for` (probed flags), `check_env`/`child_env`, `_spawn` (the
   only subprocess call), `parse_claude`/`parse_codex`, `call`, `log_call`
   (`launch.log.jsonl`), `PROMPTS` as constants (hash-stable), inventory built from
   Python-split sentences, `packet_prompt` with inlined inputs, `grade`, `generate`,
   `run` (ISO-week run id). Stale judgments are renamed, not overwritten; rejected replies
   go to `private/raw/` with their usage kept in grading cost. Tests:
   `tests/test_bench_launch.py`, `_spawn` faked.
3. `bench_config.json`: judges, inventory worker, the six E1 arms, `prices.rows` (empty
   until the human fills dated rows; cost shows `unknown` until then).
4. Docs: EXTRACTION-BENCHMARK.md (launcher commands, rules 9 and 12–14, settled open
   items, §12 schedule and history), `docs/benchmarks/README.md` (method page), README
   pointer. Doc drift fixed on the way: QUALITY.md numbers and references, with
   `tests/test_quality_doc.py` so they cannot drift again.

**HUMAN RUN**, in order (none can be done by an agent: the launcher refuses inside one):

1. Fresh run from the seven retrospective outputs (the old `retro` judgments used
   unversioned prompts and stay untouched):
   `Copy-Item -Recurse <root>\runs\retro\attempts <root>\runs\retro2\attempts`, then
   `bench_launch.py grade --run retro2 --packets A`. Exit 75: rerun after the printed reset.
   About 14 Claude and 7 Codex calls.
2. `extraction_benchmark.py leaderboard --out ../../docs/benchmarks/extraction.md`; add one
   hand-written paragraph on self-preference from the per-judge F column; commit.
3. After gold approval: `bench_launch.py grade --run retro2` adds packet B (14 calls).
   Then Gate 2 (calibration) with the existing commands.
4. Choose the scheduled champion and challenger, one manual `bench_launch.py run --arms`,
   then register the task (EXTRACTION-BENCHMARK.md §12).
5. Before Gate 3: confirm the `luna-max` model id in `bench_config.json`; fill price rows.

## Done when

- [ ] Launcher, harness, claims and doc tests pass; lint clean.
- [ ] Both CLIs list their subcommands.
- [ ] No stale status line left in the docs.
- [ ] HUMAN: `docs/benchmarks/extraction.md` has seven `retro2` rows with F, G and F per judge.
- [ ] HUMAN: `Get-ScheduledTask pnp-bench` shows Ready; `launch.log.jsonl` has the first manual run.

    cd services/kb
    .venv/Scripts/python.exe -m pytest -q tests/test_bench_launch.py tests/test_extraction_benchmark.py tests/test_claims.py tests/test_quality_doc.py
    .venv/Scripts/python.exe bench_launch.py --help
    .venv/Scripts/python.exe extraction_benchmark.py leaderboard --help
    cd ../..; ruff check .
    git grep -n "No model has been run" docs/
