# O3 — World status `since` is where the state began, not its last repeat

Branch `feat/ontology-hygiene`. Fourth in the O-series. Cost $0.

## Intent

The state pass reports a status *whenever a session mentions it*, so the
same fact repeats. `characters/rotunas.md` today:

```yaml
world_status: {value: dead, since: S1-01-A, at: 00:00:01, evidence: observed}
world_status_history:
- {value: dead, since: P-12, ...}
- {value: dead, since: P-46, ...}
- {value: dead, since: S1-01-A, ...}
```

"Dead since S1-01-A @ 00:00:01" is wrong; the death is the first entry.
Cause: `state.py` `world_state_by_concept` sorts records (`_chronological`)
and picks the **last** observed one (`_current`) without collapsing repeats.
Attitudes have the same defect (`friendly` repeated → `since` moves forward).

Wanted: before choosing current and history, collapse **runs of the same
value** to one record:
- A run is consecutive records (chronological) with equal `value`.
- The kept record of a run is the first `observed` record in the run; if the
  run has none, its first record.
- `dead → alive → dead` stays three records (real changes).
- History is emitted only when more than one record survives (as now).

Not in scope: whether P-12 is the true death of Rotunas (T00 names P-34).
That is a GM check on the transcript; write it into the PR as an open
question, do not change code for it.

## Steps

1. **Test first**, in `services/kb/tests/test_world_state.py` (it already
   tests `world_state_by_concept`; reuse its helpers):
   - three observed `dead` records at P-12, P-46, S1-01-A → `world_status.since` is P-12's label, no `world_status_history`.
   - `dead` claimed (session 1) then `dead` observed (session 2) → kept record is session 2, evidence observed.
   - `dead`, `alive`, `dead` (all observed) → history has 3 entries, current is the last.
   - attitude `friendly` ×2 then `hostile` toward party → current hostile; a second test that `friendly`×3 gives since = first.
2. `services/kb/src/pnp_okf/state.py`: add next to `_chronological`:
   ```python
   def _collapse_runs(ordered: list) -> list:
       """One record per run of equal values (O3). The state pass repeats a
       status every session that mentions it; without this, ``since`` moved to
       the latest repeat (Rotunas: "dead since S1-01-A @ 00:00:01")."""
   ```
   Implement per the rules above (pure, no I/O).
3. In `world_state_by_concept`: `ordered = _collapse_runs(_chronological(records))`
   for statuses, and `_current(_collapse_runs(_chronological(records)))` for
   attitudes. Nothing else changes; `render_stand_section` reads the same keys.
4. Full suite. If an existing test expected the repeated history, STOP and report.

## Done when

- [ ] New tests pass; suite green except the known `last_run.json` test.
- [ ] `ruff check .` clean.
- [ ] After the shared HUMAN RUN: `characters/rotunas.md` has one `dead` entry; PR names the P-12 vs P-34 question for the GM.

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q
ruff check .
# after HUMAN RUN, from repo root:
sed -n '/^world_status:/,/^sources:/p' knowledge/bundle/splitter_des_ewigen/characters/rotunas.md
```
