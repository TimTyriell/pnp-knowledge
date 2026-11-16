# O2 — Thread hygiene: fold title collisions, mark dormant threads

Branch `feat/ontology-hygiene`. Fifth in the O-series. Cost $0 (no state
re-run; all changes happen after the cached fold).

## Intent

Measured 2026-11-16 over `threads/` (193 concepts):
- 150 open, 42 resolved, 1 abandoned. 113 open threads have **one** entry:
  opened once, never touched again. The pre-session summary lists all of them.
- 30 ids end in `_2`.. `_4`, e.g. `die_macht_des_varsul_in_lindo_laut` ×4.
  `Ledger._mint` suffixes when the model answers `NEU` with a title that
  already exists. `thread_rules:` is empty, so nobody folded them.

Two changes, both after the fold:

**A. Title collisions.** Fold `threads/X_<n>` into `threads/X` when both
titles are equal case-insensitively (after strip). Reuse the merge logic
already in `apply_thread_rules` — **do not copy it**: extract it into a helper
and call it from both. Opt-out: `thread_rules: keep_apart: [<thread id>, ...]`
— a listed id is never auto-folded (either side).

Why after the fold and not in `Ledger.apply`: the open-thread list shown to
the model is part of every later state cache key (PIPELINE.md §3a). Changing
the fold re-keys every later session ($2–4). Post-fold costs nothing.

**B. Dormant.** An open thread is `dormant` when at least `DORMANT_AFTER`
(default 6) sessions **of its table** happened after its last entry. Table =
team letters from `episodes.teams_for` of the thread's entry URLs; a thread
with no team counts every later session. Emitted as frontmatter
`dormant: true` (key omitted otherwise). `thread_status` stays `open` — this
is a reading aid, not a ruling. The summary service skips dormant threads.

**STOP — ask the human** if they want a different `DORMANT_AFTER`; default 6
(≈ 6 weeks of play for Team A). Proceed with 6 if no answer is needed by the plan.

## Steps

1. **Tests first**, `services/kb/tests/test_state_ledger.py` (merge) and
   `services/kb/tests/test_thread_emit.py` (dormant, emit):
   - ledger with `threads/foo` and `threads/foo_2` (same title, different case) → after `merge_title_collisions`, only `threads/foo`, entries combined and sorted, `opened` = earliest.
   - `keep_apart: [threads/foo_2]` → both stay.
   - `threads/foo` and `threads/bar_2` with different titles → untouched.
   - existing `thread_rules merge` tests still pass (helper refactor).
   - `dormant_threads`: thread last touched in session 2 of team A; sessions 3–8 are A → dormant; same but sessions 3–8 are team B → not dormant; resolved thread → never dormant; thread with no team and 6 later sessions → dormant.
   - `emit_threads(..., dormant={"threads/foo"})` writes `dormant: true`; other threads have no `dormant` key.
2. `services/kb/src/pnp_okf/state.py`:
   - extract the body of the `merge` loop in `apply_thread_rules` into
     `_merge_into(ledger, loser_id: str, winner_id: str) -> bool` (returns False and appends the existing warning when either id is missing). `apply_thread_rules` calls it.
   - `merge_title_collisions(ledger, keep_apart: set[str]) -> None`: for each id matching `^(.*)_(\d+)$` whose base id exists, titles equal case-insensitively, neither id in `keep_apart` → `_merge_into(ledger, id, base)`. Iterate over a sorted copy of the ids.
   - `DORMANT_AFTER = 6` and `dormant_threads(threads, sessions: list[tuple[str, str]], episodes, n: int = DORMANT_AFTER) -> set[str]` where `sessions` is `(session_id, url)` in date order. Pure. Use `teams_for` from `pnp_okf.episodes`.
3. `services/kb/src/pnp_okf/cli.py` `_run_pipeline`: right after
   `apply_thread_rules(ledger, load_thread_rules(registry_path))` add
   `merge_title_collisions(ledger, set(load_thread_rules(registry_path).get("keep_apart") or []))`
   (load the rules once into a variable). Compute
   `dormant = dormant_threads(ledger.threads.values(), [(t.session_id, t.url) for t in sorted(tmap.values(), key=lambda t: (t.date, t.session_id))], episodes)`
   and pass `dormant=dormant` to `emit_threads`. Use the transcript map variable the function already has; check its name before editing.
4. `services/kb/src/pnp_okf/emit.py` `emit_threads`: new keyword
   `dormant: set[str] | None = None`; frontmatter
   `"dormant": True if dormant and thread.thread_id in dormant else None` (placed after `thread_status`; `None` is omitted, as for `teams`).
5. `services/kb/src/pnp_okf/api.py` `list_concepts`: add `"dormant"` to the
   `for key in ("kind", "thread_status")` tuple. Test in `tests/test_api.py` if it has a thread listing test; otherwise skip.
6. `services/summary/summary.py` `fetch_open_threads`: skip a thread when
   `fm.get("dormant")`. Test in `services/summary/test_summary.py` using the
   existing `_kb_handler` fixture: one dormant + one active thread → only active returned.
7. `knowledge/entity_rules.yaml`: under `thread_rules:` replace `{}` with a
   commented, empty `keep_apart: []` entry explaining the family (guard allows this file).

## Done when

- [ ] All new tests pass; kb and summary suites green (kb: known `last_run.json` test excepted).
- [ ] `ruff check .` clean.
- [ ] After the shared HUMAN RUN: `_<n>` thread ids < 30, and count of `dormant: true` recorded in the PR.

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q
cd services/summary && ../kb/.venv/Scripts/python.exe -m pytest -q   # or the summary venv if present
ruff check .
# after HUMAN RUN, from repo root:
ls knowledge/bundle/splitter_des_ewigen/threads | grep -cE "_[0-9]+\.md$"
grep -l "^dormant: true" knowledge/bundle/splitter_des_ewigen/threads/*.md | wc -l
```
