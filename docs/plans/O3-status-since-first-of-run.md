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
- A run is consecutive records (chronological) with equal `value` **and** equal `evidence`, so a claim beside an observation stays in the history (T7 acceptance; first draft keyed on value only and broke `test_observed_death_beats_a_later_claim_and_both_stay_in_history`).
- The kept record of a run is its first record.
- `dead → alive → dead` stays three records (real changes).
- History is emitted only when more than one record survives (as now).

**GM correction.** Rotunas' P-12 (2025-06-17) `dead` entry is a false fact:
he plays on long after it. Collapsing alone would make it the `since`.
So O3 also adds a correction family in `entity_rules.yaml`:

```yaml
status_rules:
  drop:
  - characters/rotunas@2025-06-17_RF_tl76B4V0io8   # P-12: not a death, GM 2026-11-16
```

Each entry is `<concept_id>@<session_id>` (session_id = transcript filename stem, not the date); every status **and** attitude
record for that concept from that session is dropped before collapsing. Read
through `_registry_data` (PIPELINE.md §5), like `load_thread_rules`. The
rules-file edit itself is not part of this branch (`knowledge/` is the
private bundle repo); the orchestrator adds it there.

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
4. `status_rules: drop`: add `load_status_rules(registry_path) -> set[tuple[str, str]]`
   (parses `concept@session`, ignores malformed entries with a log warning) and a
   keyword `drop: set[tuple[str, str]] | None = None` on `world_state_by_concept`;
   skip a record when `(cid, record.entry.session_id)` is in it — after the name
   lookup, before grouping. In `cli._run_pipeline`, pass
   `drop=load_status_rules(registry_path)` where `world_state_by_concept` is called.
   Tests: a dropped session's `dead` disappears and `since` moves to the next
   run; loader reads the family from a tmp `entity_rules.yaml`; malformed entry ignored.
5. Full suite. If an existing test expected the repeated history, STOP and report.

## Done when

- [ ] New tests pass; suite green except the known `last_run.json` test.
- [ ] `ruff check .` clean.
- [ ] After the shared HUMAN RUN: `characters/rotunas.md` has one `dead` entry, since P-46 (P-12 dropped by `status_rules`).

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q
ruff check .
# after HUMAN RUN, from repo root:
sed -n '/^world_status:/,/^sources:/p' knowledge/bundle/splitter_des_ewigen/characters/rotunas.md
```
