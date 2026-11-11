# S1 — Season freeze: frozen Prolog ground truth, pipeline runs on the active season only

Repo: `pnp-knowledge`. Branch `feat/season-freeze`, cut from `origin/main` **after PR #39
(`feat/local-campaign-workbench`) is merged**. Written so a Haiku worker implements each work
package (WP) without design decisions and a Sonnet reviewer checks it. Anchor names (`def …`)
are authoritative; line numbers are from 2026-11-11 on `feat/local-campaign-workbench`.

## 1. Context

A `*_PROMPT_VERSION` bump or model change re-derives the whole back catalogue (75 transcripts,
~$6.5, concept-id churn). The only protection is `PNP_EXTRACT_FREEZE_BEFORE/VERSION`
(`extract.py::_frozen_prompt_version`): it only swaps the version inside the cache key, the data
lives in gitignored `.cache/`, it is date-based, and it does nothing for synthesis or state.

Wanted: the Prolog (season `P`, 55 sessions, complete) becomes a **committed ground truth**. The
normal workflow only calls the model for the current season (Staffel 1). Older seasons are read
from frozen files and re-read only on a manual trigger. General per-season feature, managed from
the dashboard.

Decisions (user, 2026-11-11):
1. Ground truth = snapshot of the current v6 pipeline output as-is, plain files.
2. Frozen seasons keep **full detail** in synthesis; freezing only stops re-reading.
3. UI = Technical dashboard, Folgen tab, and it **starts paid runs itself**.

Consequence for the open "glossary into synthesis now vs hold for B2": **hold**. Freeze P at v6
first; B2's bump then only touches Staffel 1.

## 2. Requirements

| # | Requirement |
|---|---|
| R1 | A season is frozen iff `knowledge/frozen/<season>/manifest.json` exists. No flag, no env var. |
| R2 | Frozen dir holds per season: every session's extraction; the raw synthesized body of every non-brief entity whose mentions all lie in that season; every session's state result when the state cache is complete. Plain JSON, hand-correctable. |
| R3 | For a frozen session the model is never called, regardless of prompt versions, model name, `--reextract`, `--force`, or an empty `.cache/`. |
| R4 | A changed transcript of a frozen session logs one warning and still uses the frozen file. |
| R5 | A corrupt or incomplete freeze (bad manifest, listed session without file) **raises**. It never silently falls back to a paid call. |
| R6 | Normal `pnp run` stays a full run (all sessions, rename guard on). Not a partial run. |
| R7 | A frozen body is used only if the entity's mentions are all in one frozen season **and** the mention fingerprint matches; otherwise normal synthesis. Cross-season entities synthesize as today. |
| R8 | `--thaw <season>[,<season>]` or `--thaw all` on `run`/`extract`/`state`/`dedup` ignores those seasons' frozen files for that run. Never modifies them. |
| R9 | `pnp freeze <season>`: no model call; exits 2 if a session of the season has no extraction; default mode never overwrites an existing frozen file; `--from-cache` overwrites from the current cache. |
| R10 | `pnp run --estimate` prints a `frozen:` line; frozen sessions and bodies are not counted as calls. |
| R11 | Sessions whose video id is not in `episodes.yaml` have no season and are always active. |
| R12 | `GET /api/seasons` reports per season: label, episode count, transcript count, manifest summary or null, current prompt versions, unlisted transcripts. |
| R13 | Dashboard can freeze a season, fetch an estimate, start `pnp run` / `pnp state` with optional thaw after explicit confirmation, show progress and result. One run at a time, loopback-only, fixed argv. |
| R14 | `PNP_EXTRACT_FREEZE_*` unchanged (precedence: frozen file > env pin > current version). |
| R15 | No prompt-version bump, no model call, no edit under `knowledge/` by any agent. |

Out of scope: seasons in workbench campaigns; condensing Prolog; B2; running without transcripts
on disk; a guard change (the guard regex only blocks `run|state|extract|dedup`, so `freeze` is
already allowed).

## 3. How to execute this plan (orchestrator = main session)

Setup, once:

```bash
cd c:/dev/lindo-lauts-notebook/pnp-knowledge
git fetch origin
git worktree add ../.wt/pnp-knowledge-season-freeze -b feat/season-freeze origin/main
```

All work happens in `c:/dev/lindo-lauts-notebook/.wt/pnp-knowledge-season-freeze` (= `$WT`).
The shared checkout gets branch-switched by other sessions; never work there. The worktree has
no venvs; use the main checkout's interpreters:

```bash
KBPY=c:/dev/lindo-lauts-notebook/pnp-knowledge/services/kb/.venv/Scripts/python.exe
DBPY=c:/dev/lindo-lauts-notebook/pnp-knowledge/services/dashboard/.venv/Scripts/python.exe
# kb tests (pyproject sets pythonpath=src, so the worktree's source wins):
cd $WT/services/kb && $KBPY -m pytest -q
# dashboard tests MUST force the worktree's pnp_okf, or they import the main checkout's:
cd $WT/services/dashboard && PYTHONPATH=$WT/services/kb/src $DBPY -m pytest -q
# lint, from $WT:
$KBPY -m ruff check .
```

Loop, **one WP at a time, in order** (each depends on the previous):

1. Spawn worker: `Agent(subagent_type="general-purpose", model="haiku")`. Prompt = §4 rules +
   the full text of that WP + §3 commands. Worker commits when its WP's checks pass.
2. Spawn reviewer: `Agent(subagent_type="general-purpose", model="sonnet")`. Prompt = §2
   requirements + that WP's text + §5 checklist + "review `git -C $WT show HEAD`; do not edit".
3. Reviewer says `CHANGES` → send the findings to the same worker (`SendMessage`), worker fixes
   in a new commit, reviewer re-reads. Max 2 rounds, then the orchestrator decides.
4. After WP8: run the repo's `verifier` agent (`.claude/agents/verifier.md`) on
   `docs/plans/S1-season-freeze.md`, push, `gh pr create --base main`, then `/review-pr <n>`.

## 4. Rules for the worker (paste into every worker prompt)

1. Work only in `$WT`. Never `git switch`. Never touch `graph/`, `knowledge/`, `.claude/hooks/`.
2. **Never call DeepSeek.** Never run `pnp run|extract|state|dedup` without `--estimate`. Never
   run `pnp freeze` or `--estimate` against the real bundle — only with `--transcripts`,
   `--bundle`, `--cache` pointing into a pytest `tmp_path`. Real-bundle steps are **HUMAN RUN**.
3. Never change `prompts.py`. Never change a `*_PROMPT_VERSION`.
4. Write the tests first (`.claude/skills/test-driven-development`), see them fail, then implement.
5. Use Write/Edit for Python source, never bash heredocs (they eat backslashes here).
6. Comments explain *why*, in the surrounding style. No new dependencies.
7. If code does not match what the WP describes (function missing, signature different, test
   name taken): **STOP and report**. Do not improvise.
8. Commit per WP: Conventional Commits, subject ≤72 chars, body says why, ends with the
   attribution line given by the session. Stage only the files the WP names.
9. Final message: files changed, the exact commands run and their last output line, anything skipped.

## 5. Reviewer checklist (paste into every reviewer prompt)

Report `VERDICT: OK` or `VERDICT: CHANGES` plus findings as `path:line — problem — fix`.

- Diff touches only the files the WP names. No `prompts.py`, `knowledge/`, `graph/`, guard edits.
- Every test listed in the WP exists and asserts what the WP says (not weaker).
- No code path lets a frozen session reach `extract_session`, `_call_llm` or `build_client`
  (R3), and no `except` turns a broken freeze into a fallback (R5).
- Existing function signatures that tests monkeypatch are unchanged
  (`extract_session(transcript, cfg, cache_dir, *, client=None, force=False)`).
- New arguments are optional with a default that preserves today's behaviour.
- Reviewer runs the WP's check commands and pastes the last line of each.

---

## WP1 — plan file

Files: `docs/plans/S1-season-freeze.md` (copy of this plan), `docs/plans/README.md`.

Add after the B3 row in the README table:

```
| S1 | [S1-season-freeze.md](S1-season-freeze.md) | `feat/season-freeze` | PR #39 merged | $0 code; freeze itself is free (human) | agent + human |
```

Check: `git diff --stat` shows exactly those two files. Commit: `docs: add season-freeze plan (S1)`.

---

## WP2 — `frozen.py`: the read side

New file `services/kb/src/pnp_okf/frozen.py`. New test file `services/kb/tests/test_frozen_store.py`.

On-disk layout this module reads (WP5 writes it):

```
knowledge/frozen/<season>/manifest.json
knowledge/frozen/<season>/extract/<session_id>.json     # SessionExtraction.model_dump(mode="json")
knowledge/frozen/<season>/synth/<concept__id>.json      # {"fingerprint": str, "body": str}
knowledge/frozen/<season>/state/<session_id>.json       # SessionState.model_dump(mode="json")
```

`manifest.json`:

```json
{"schema": 1, "season": "P", "label": "Prolog", "frozen_at": "2026-11-12T10:00:00Z",
 "prompt_versions": {"extract": "6", "synth": "6", "state": null},
 "models": {"extract": "deepseek-v4-pro", "deep": "deepseek-v4-pro", "standard": "deepseek-v4-flash"},
 "sessions": [{"session_id": "2025-03-26_RF_ROCKGeeRUFw", "date": "2025-03-26",
               "video_id": "ROCKGeeRUFw", "episode_id": "P-01", "dialogue_sha": "ab12…"}],
 "counts": {"sessions": 55, "bodies": 0, "bodies_missing": 0, "state_sessions": 0},
 "bodies_missing": []}
```

Code for WP2 (write exactly this; the module docstring must explain R1, R3, R5 and name this plan):

```python
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path

from pnp_okf.models import CanonicalEntity, SessionExtraction, SessionTranscript

log = logging.getLogger(__name__)

FROZEN_DIRNAME = "frozen"


class FrozenError(RuntimeError):
    """A freeze that exists but cannot be trusted. Never caught to fall back to a paid call."""


def dialogue_sha(transcript: SessionTranscript) -> str:
    return hashlib.sha256(transcript.render_dialogue().encode("utf-8")).hexdigest()[:16]


def mention_fingerprint(entity: CanonicalEntity) -> str:
    rows = sorted((m.session_id, m.citation_ts, m.note) for m in entity.mentions)
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def safe_name(concept_id: str) -> str:
    return concept_id.replace("/", "__")


def write_json(path: Path, data: dict) -> None:
    """temp + os.replace: a kill mid-freeze must not leave a half-written ground truth."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrozenError(f"Frozen file unreadable: {path} ({exc}). Fix or restore it from git; "
                          "the pipeline will not re-buy a frozen session on its own.") from exc


class FrozenStore:
    def __init__(self, root: Path | None = None, thaw: frozenset[str] = frozenset()) -> None:
        self.root = root
        self.manifests: dict[str, dict] = {}
        self._season_of: dict[str, str] = {}
        self._sha: dict[str, str] = {}
        self._warned: set[str] = set()
        if root is None or not root.is_dir():
            return
        for mpath in sorted(root.glob("*/manifest.json")):
            season = mpath.parent.name
            if "all" in thaw or season in thaw:
                log.warning("[frozen] season %s is thawed for this run", season)
                continue
            manifest = _read(mpath)
            self.manifests[season] = manifest
            for s in manifest.get("sessions", []):
                self._season_of[s["session_id"]] = season
                self._sha[s["session_id"]] = s.get("dialogue_sha", "")

    @classmethod
    def load(cls, knowledge_root: Path, thaw=()) -> FrozenStore:
        return cls(knowledge_root / FROZEN_DIRNAME, frozenset(thaw))

    def season_of(self, session_id: str) -> str | None:
        return self._season_of.get(session_id)

    def extraction(self, transcript: SessionTranscript) -> SessionExtraction | None:
        season = self._season_of.get(transcript.session_id)
        if season is None:
            return None
        blob = _read(self.root / season / "extract" / f"{transcript.session_id}.json")
        sid = transcript.session_id
        if sid not in self._warned and self._sha.get(sid) and self._sha[sid] != dialogue_sha(transcript):
            self._warned.add(sid)
            log.warning("[frozen] transcript of %s changed since season %s was frozen; "
                        "still using the frozen extraction (--thaw %s to re-read)", sid, season, season)
        return SessionExtraction.model_validate(blob)

    def body(self, entity: CanonicalEntity) -> str | None:
        seasons = {self._season_of.get(m.session_id) for m in entity.mentions}
        if len(seasons) != 1 or None in seasons:
            return None
        path = self.root / next(iter(seasons)) / "synth" / f"{safe_name(entity.concept_id)}.json"
        if not path.is_file():
            return None
        blob = _read(path)
        return blob["body"] if blob.get("fingerprint") == mention_fingerprint(entity) else None

    def state_blob(self, session_id: str) -> dict | None:
        season = self._season_of.get(session_id)
        if season is None:
            return None
        path = self.root / season / "state" / f"{session_id}.json"
        return _read(path) if path.is_file() else None
```

Notes for the worker: `FrozenStore()` with no args is the empty store; every method returns
`None` on it. `state_blob` returns a dict on purpose (`state.py` validates it; keeps this module
free of a `state` import).

Tests in `test_frozen_store.py` (build the dir by hand with `write_json` in `tmp_path`; build
`SessionTranscript` like `tests/test_state_runner.py::_transcript`; build `CanonicalEntity` with
`MentionRef` from `pnp_okf.models`):

| Test | Asserts |
|---|---|
| `test_missing_dir_is_an_empty_store` | `FrozenStore.load(tmp_path)`: `extraction`, `body`, `state_blob`, `season_of` all return `None`. |
| `test_extraction_round_trip` | written `SessionExtraction` comes back equal; `season_of` returns `"P"`. |
| `test_unlisted_session_is_not_frozen` | session not in manifest → `None`. |
| `test_thaw_hides_the_season` | `load(root, thaw={"P"})` → `None`; `thaw={"all"}` → `None`. |
| `test_listed_session_without_file_raises` | manifest lists session, no extract file → `pytest.raises(FrozenError)`. |
| `test_corrupt_manifest_raises` | manifest containing `{not json` → `pytest.raises(FrozenError)` on `load`. |
| `test_changed_transcript_warns_once_and_still_returns` | different dialogue → result returned, exactly one WARNING across two calls (`caplog`). |
| `test_body_needs_all_mentions_in_one_frozen_season` | entity with one mention in an unfrozen session → `None`. |
| `test_body_fingerprint_mismatch_falls_through` | stored fingerprint `"x"` → `None`; correct fingerprint → body. |

Checks: `cd $WT/services/kb && $KBPY -m pytest -q tests/test_frozen_store.py` (9 passed), then
the full suite, then `$KBPY -m ruff check .` from `$WT`.
Commit: `feat(kb): add FrozenStore, the read side of season freeze`.

---

## WP3 — extraction and state read through the store

Files: `extract.py`, `state.py`, `cli.py`, `config.py`. Tests: `tests/test_frozen_wiring.py`.

**`extract.py`** — change only `load_cached_extraction`. Do **not** touch `extract_session`
(`tests/test_cli.py::_capture_extract_model` monkeypatches it with a fixed signature).

```python
def load_cached_extraction(
    cache_dir: Path, transcript: SessionTranscript, cfg: DeepSeekConfig, *, frozen=None
) -> SessionExtraction | None:
    ...existing docstring, plus one sentence: a frozen season wins over the cache...
    if frozen is not None:
        hit = frozen.extraction(transcript)
        if hit is not None:
            return hit
    key = _cache_key(transcript, cfg)
    return _load_cached(_cache_path(cache_dir, transcript, key), key)
```

**`state.py`** — `class StateRun`: add `states: dict[str, SessionState] = field(default_factory=dict)`
(import `field` from `dataclasses`). `def run_state`: add keyword `frozen=None`. First lines of
the loop body:

```python
        blob = frozen.state_blob(t.session_id) if frozen is not None else None
        if blob is not None:
            state = SessionState.model_validate(blob)
            run.cached += 1
            run.states[t.session_id] = state
            run.ledger.apply(t.session_id, t.date, t.url, state)
            continue
```

and before the existing final `run.ledger.apply(...)` add `run.states[t.session_id] = state`.

**`config.py`** — in `class Paths` add next to `episodes_path`:

```python
    @property
    def frozen_dir(self) -> Path:
        """Per-season ground truth (see :mod:`pnp_okf.frozen`). Sibling of the registry."""
        return self._knowledge_root / "frozen"
```

In `Paths.resolve`, replace `or "./transcript"` with `or default_transcript_dir()` (defined
below the class; resolved at call time). This is why `pnp check` could not find transcripts.

**`cli.py`**

1. Import: `from pnp_okf.frozen import FrozenError, FrozenStore`.
2. Add helper above `_extract_all`:

```python
def _frozen(paths: Paths, args: argparse.Namespace) -> FrozenStore:
    """The frozen seasons minus whatever this run explicitly thaws."""
    raw = getattr(args, "thaw", None) or ""
    return FrozenStore.load(paths.knowledge_root, {s.strip() for s in raw.split(",") if s.strip()})
```

3. `_extract_all`: new last parameter `frozen: FrozenStore | None = None`. `_one` becomes:

```python
    def _one(t: SessionTranscript) -> tuple[str, SessionExtraction]:
        # Frozen wins over force: --reextract must not re-buy a frozen season (R3).
        hit = frozen.extraction(t) if frozen is not None else None
        if hit is not None:
            return t.session_id, hit
        return t.session_id, extract_session(t, cfg, paths.cache_dir, force=force)
```

4. `_run_pipeline`: after `cfg = ...` add `frozen = _frozen(paths, args)`; pass `frozen=frozen`
   to `_extract_all(...)` and to the `run_state(...)` call (anchor: comment `# T6: fold the cached state pass`).
5. `cmd_extract`, `cmd_dedup`: build `frozen = _frozen(paths, args)`, pass to `_extract_all`.
6. `cmd_state`: `run_state(transcripts, cfg, paths.cache_dir, rows, estimate=args.estimate, frozen=_frozen(paths, args))`.
7. `_add_common`: add

```python
    p.add_argument(
        "--thaw", default="",
        help="Comma-separated season keys (or 'all') whose frozen files this run "
        "ignores, e.g. --thaw P. Re-reads those seasons at the current prompt "
        "version -- costs money and can rename concept ids. Frozen files are "
        "not modified; accept the result with `pnp freeze <season> --from-cache`.",
    )
```

8. `main`: add `except FrozenError as exc: log.error("%s", exc); return 2` next to the
   `FileNotFoundError` handler.

Tests in `test_frozen_wiring.py`. Helper to copy: `tests/test_cli.py::_make_transcript` but with
`"video_url": "https://www.youtube.com/watch?v=vid00001"`. Knowledge root in tests =
`tmp_path/"knowledge"`, bundle = `tmp_path/"knowledge"/"bundle"/"camp"`, so
`Paths.resolve(...).knowledge_root == tmp_path/"knowledge"`. Raising client:

```python
class _Boom:
    def __getattr__(self, name):
        raise AssertionError("the model was called for a frozen session")
```

| Test | Asserts |
|---|---|
| `test_load_cached_extraction_prefers_frozen` | empty cache dir + frozen store → returns the frozen extraction. |
| `test_frozen_extraction_survives_a_prompt_bump` | `monkeypatch.setattr("pnp_okf.extract.EXTRACT_PROMPT_VERSION", "99")` → still returned. |
| `test_extract_all_never_calls_the_model_for_frozen` | `monkeypatch.setattr("pnp_okf.cli.extract_session", <fn that raises AssertionError>)`; `_extract_all(..., force=True, frozen=store)` returns the frozen extraction. |
| `test_thaw_reaches_extract_session` | same setup, `FrozenStore.load(root, {"P"})` → the monkeypatched function **is** called (count == 1). |
| `test_run_state_applies_frozen_state_without_a_call` | `run_state(two sessions, …, client=_Boom(), frozen=store with both states)` → `called == 0`, `cached == 2`, `set(run.states) == {both ids}`. |
| `test_run_state_frozen_prefix_then_cached_call` | first session frozen, second not; `_SeqClient` (copy from `test_state_runner.py`) with one payload → `called == 1`, and the second prompt contains the thread minted from the frozen first session. |
| `test_thaw_flag_parses` | `_build_parser().parse_args(["run", "--thaw", "P,1"]).thaw == "P,1"`. |
| `test_paths_default_transcripts_is_the_sibling_checkout` | with `PNP_TRANSCRIPT_DIR` unset, `Paths.resolve().transcript_dir.parts[-2:] == ("pnp-crawl", "transcripts_final")`. |

Checks: new file green, full kb suite green, ruff clean.
Commit: `feat(kb): serve frozen seasons to extraction and the state pass`.

---

## WP4 — synthesis and estimate

Files: `cli.py`. Tests: append to `tests/test_frozen_wiring.py`.

1. `_run_pipeline`, inner `def _synth`: replace `body = synthesize_entity_body(` … `)` with

```python
        # A frozen season's own entities keep their body across SYNTH bumps and
        # --force; a changed mention set misses the fingerprint and falls through.
        body = frozen.body(entity)
        if body is None:
            body = synthesize_entity_body(...same arguments as before...)
```

   The `autolink_prose(...)` return line stays as is (frozen bodies are stored pre-autolink).

2. `_estimate_run`:
   - after `cfg = ...`: `frozen = _frozen(paths, args)`.
   - in the cached/missing loop, first line: `if frozen.season_of(t.session_id): n_frozen += 1; continue`
     (declare `n_frozen = 0` before the loop).
   - the `extractions = {...}` dict: `load_cached_extraction(paths.cache_dir, t, cfg, frozen=frozen)`.
   - in the entity loop after the `brief` check: `if frozen.body(entity) is not None: frozen_bodies += 1; continue`.
   - leave the existing `extract:` / `synth:` / `estimate:` lines byte-identical. Add **one** new
     line, printed right after the `extract:` line and only when `frozen.manifests` is non-empty:
     `print(f"frozen:   {n_frozen} session(s) in season(s) {', '.join(sorted(frozen.manifests))}")`
     and, where `synth:` prints its numbers, a second line only when `frozen_bodies`:
     `print(f"frozen:   {frozen_bodies} entity bod(y/ies)")`.

Tests:

| Test | Asserts |
|---|---|
| `test_estimate_counts_frozen_sessions_as_free` | one transcript, frozen, empty cache → `main(["run","--estimate",…])` output contains `frozen:   1 session(s)` and `0 to call`. Env as in `test_cli.py::test_estimate_makes_no_llm_call`. |
| `test_estimate_with_thaw_prices_the_season_again` | same + `--thaw P` → output contains `1 to call`, no `frozen:` line. |
| `test_frozen_body_skips_synthesis` | unit test on the store + a monkeypatched `pnp_okf.cli.synthesize_entity_body` that raises: follow `tests/test_pipeline_offline.py` to drive `_run_pipeline` offline; frozen body text must appear in the emitted concept file. If that fixture cannot be reused in ≤60 lines, **STOP and report** instead of building a new harness. |

Checks: as WP3. Commit: `feat(kb): frozen bodies skip synthesis; estimate reports frozen seasons`.

---

## WP5 — `pnp freeze`: the write side

Files: `frozen.py` (append), `cli.py`, `apply_important.py`, `apply_merges.py`, `claim_sampler.py`,
`make_gold_stub.py`. Tests: `tests/test_freeze_command.py`.

Append to `frozen.py` (imports go to the top of the file; none of these modules import `frozen`,
so there is no cycle):

```python
from datetime import UTC, datetime

from pnp_okf.config import DeepSeekConfig, Paths
from pnp_okf.context import excerpts_for, load_sources, secondary_sources_for, sources_for
from pnp_okf.episodes import Episodes, video_id
from pnp_okf.extract import _frozen_prompt_version, load_cached_extraction
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import EntityType
from pnp_okf.prompts import STATE_PROMPT_VERSION, SYNTH_PROMPT_VERSION
from pnp_okf.resolve import load_event_concepts, require_rules, resolve_entities
from pnp_okf.state import load_glossary, run_state
from pnp_okf.synthesize import _cache_key as synth_cache_key
from pnp_okf.synthesize import _cache_path as synth_cache_path


def freeze_season(paths: Paths, season: str, cfg: DeepSeekConfig, *, from_cache: bool = False) -> dict:
    """Snapshot one season from the caches into knowledge/frozen/<season>/. No model call."""
    episodes = Episodes.load(paths.episodes_path)
    transcripts = load_transcripts(paths.transcript_dir)
    members = [t for t in transcripts
               if str((episodes.for_url(t.url) or {}).get("season", "")) == season]
    if not members:
        raise FrozenError(f"No transcript belongs to season {season!r} per {paths.episodes_path}.")
    member_ids = {t.session_id for t in members}

    # Default mode reads through the existing freeze, so a re-run only fills gaps.
    # --from-cache thaws this season: the cache is the new truth and overwrites.
    store = FrozenStore.load(paths.knowledge_root, {season} if from_cache else ())
    extract_cfg = cfg.for_tier("extract")
    extractions = {}
    for t in transcripts:
        ex = load_cached_extraction(paths.cache_dir, t, extract_cfg, frozen=store)
        if ex is not None:
            extractions[t.session_id] = ex
    missing = sorted(member_ids - set(extractions))
    if missing:
        raise FrozenError(f"Cannot freeze season {season}: no extraction for {len(missing)} "
                          f"session(s): {', '.join(missing)}. Run `pnp run` first.")

    out = paths.frozen_dir / season
    old = _read(out / "manifest.json") if (out / "manifest.json").is_file() and not from_cache else None

    def put(path: Path, data: dict) -> None:
        if from_cache or not path.exists():
            write_json(path, data)

    for t in members:
        put(out / "extract" / f"{t.session_id}.json", extractions[t.session_id].model_dump(mode="json"))

    require_rules(paths.registry_path)
    tmap = {t.session_id: t for t in transcripts if t.session_id in extractions}
    entities = resolve_entities(extractions, tmap, paths.registry_path)
    event_concepts = load_event_concepts(paths.registry_path)
    sections = load_sources(paths.sources_dir)
    bodies_missing: list[str] = []
    for e in entities:
        if e.tier == "brief" or (e.type == EntityType.EVENT and e.concept_id not in event_concepts):
            continue            # rendered locally / not a concept: nothing to freeze
        if not all(m.session_id in member_ids for m in e.mentions):
            continue
        dest = out / "synth" / f"{safe_name(e.concept_id)}.json"
        if dest.exists() and not from_cache:
            continue
        tier_cfg = cfg.for_tier(e.tier)
        key = synth_cache_key(e, tier_cfg, sources_for(e, sections),
                              excerpts_for(e, tmap) if e.tier == "deep" else "",
                              secondary_sources_for(e, sections))
        src = synth_cache_path(paths.cache_dir, e, key)
        if not src.is_file():
            bodies_missing.append(e.concept_id)
            continue
        write_json(dest, {"fingerprint": mention_fingerprint(e), "body": _read(src)["body"]})

    state_sessions = 0
    rows = load_glossary(paths.knowledge_root)
    if rows:
        run = run_state(transcripts, cfg.for_tier("state"), paths.cache_dir, rows,
                        estimate=True, frozen=store)
        if member_ids <= set(run.states):       # all or nothing: a partial state freeze would fork the ledger
            for sid in sorted(member_ids):
                put(out / "state" / f"{sid}.json", run.states[sid].model_dump(mode="json"))
            state_sessions = len(member_ids)

    def stamp() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    manifest = {
        "schema": 1,
        "season": season,
        "label": episodes.season_label(season),
        # A gap-filling re-run keeps the original provenance: the data is as old as it was.
        "frozen_at": old["frozen_at"] if old else stamp(),
        "prompt_versions": {
            "extract": old["prompt_versions"]["extract"] if old
            else ",".join(sorted({_frozen_prompt_version(t) for t in members})),
            "synth": old["prompt_versions"]["synth"] if old else SYNTH_PROMPT_VERSION,
            "state": STATE_PROMPT_VERSION if state_sessions else None,
        },
        "models": old["models"] if old else
            {"extract": extract_cfg.model, "deep": cfg.model, "standard": cfg.light_model},
        "sessions": [
            {"session_id": t.session_id, "date": t.date, "video_id": video_id(t.url),
             "episode_id": episodes.id_for_url(t.url), "dialogue_sha": dialogue_sha(t)}
            for t in sorted(members, key=lambda t: t.session_id)
        ],
        "counts": {
            "sessions": len(members),
            "bodies": len(list((out / "synth").glob("*.json"))) if (out / "synth").is_dir() else 0,
            "bodies_missing": len(bodies_missing),
            "state_sessions": state_sessions,
        },
        "bodies_missing": sorted(bodies_missing),
    }
    write_json(out / "manifest.json", manifest)     # last: the manifest is what makes it frozen (R1)
    return manifest
```

Worker: if `old` exists and a member's stored `dialogue_sha` differs, keep the **old** sha for
that session (the frozen extraction was made from the old dialogue). Implement by building a
`{session_id: sha}` map from `old["sessions"]` and preferring it.

**`cli.py`**: import `freeze_season`; add

```python
def cmd_freeze(args: argparse.Namespace) -> int:
    """Snapshot a season from the caches into knowledge/frozen/. Never calls the model."""
    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    m = freeze_season(paths, args.season, DeepSeekConfig.from_env(), from_cache=args.from_cache)
    c = m["counts"]
    print(f"frozen {m['season']}: {c['sessions']} session(s), {c['bodies']} bod(y/ies) "
          f"({c['bodies_missing']} without a cached body), state: "
          f"{'yes' if c['state_sessions'] else 'no'} -> {paths.frozen_dir / args.season}")
    return 0
```

Parser (after the `state` block):

```python
    freeze = sub.add_parser("freeze", help="Snapshot a season into knowledge/frozen/ (free, no LLM)")
    freeze.add_argument("season", help='Season key from episodes.yaml, e.g. "P"')
    freeze.add_argument("--from-cache", action="store_true",
                        help="Overwrite the frozen files from the current cache (after a --thaw run)")
    freeze.add_argument("--transcripts", help="Directory of *.json transcripts")
    freeze.add_argument("--bundle", help="Bundle directory")
    freeze.add_argument("--cache", help="Cache directory")
    freeze.set_defaults(func=cmd_freeze)
```

**Four scripts** — each has `load_cached_extraction(<cache>, t, cfg)`. Add
`from pnp_okf.frozen import FrozenStore`, build `frozen = FrozenStore.load(paths.knowledge_root)`
once (in `make_gold_stub.py`, which has no `paths`: `FrozenStore.load(Paths.resolve().knowledge_root)`,
importing `Paths` from `pnp_okf.config`), and pass `frozen=frozen`. Nothing else changes.

Tests in `test_freeze_command.py`. Fixture: two transcripts (video ids `vid00001`, `vid00002`),
`knowledge/episodes.yaml` with `seasons: {"P": {label: Prolog}, "1": {label: Staffel 1}}`, first
video in `"P"`, second in `"1"`; `knowledge/entity_rules.yaml` as `require_rules` needs (read
`resolve.py::require_rules` for the minimum); extract cache seeded like
`tests/test_cli.py::_seed_extract_cache` but with one `EntityMention` each.

| Test | Asserts |
|---|---|
| `test_freeze_writes_manifest_and_extractions` | `main(["freeze","P",…]) == 0`; manifest has 1 session, `prompt_versions.extract == EXTRACT_PROMPT_VERSION`; only the P session has an extract file. |
| `test_freeze_refuses_when_a_session_is_uncached` | empty cache → return code 2, no `manifest.json` on disk. |
| `test_freeze_unknown_season_exits_2` | `main(["freeze","X",…]) == 2`. |
| `test_refreeze_does_not_overwrite` | freeze; hand-edit the extract file's `recap`; freeze again → edit survives; `frozen_at` unchanged. |
| `test_from_cache_overwrites` | same, then `--from-cache` → `recap` is the cache's again. |
| `test_frozen_season_survives_cache_loss` | freeze; delete the cache dir; `main(["run","--estimate",…])` prints `frozen:   1 session(s)` and `1 to call` (the Staffel-1 session). |
| `test_freeze_makes_no_llm_call` | `DEEPSEEK_BASE_URL=https://example.invalid`, `monkeypatch.setattr("pnp_okf.llm_client.build_client", <raises>)` → freeze returns 0. |

Checks: new file green, full kb suite green, ruff clean. Also
`$KBPY -m pnp_okf.cli freeze --help` prints the season argument.
Commit: `feat(kb): add pnp freeze and --thaw`.

---

## WP6 — dashboard backend

Files: new `services/dashboard/seasons.py`, `services/dashboard/app.py`, new
`services/dashboard/test_seasons.py`, `services/dashboard/README.md`.

`seasons.py` (pure functions + one module-level run slot; `app.py` owns the routes):

```python
"""Season status and the one pipeline run the dashboard may start (docs/plans/S1-season-freeze.md)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import merge
from pnp_okf.frozen import FrozenStore
from pnp_okf.prompts import EXTRACT_PROMPT_VERSION, STATE_PROMPT_VERSION, SYNTH_PROMPT_VERSION

KB_DIR = Path(__file__).resolve().parents[1] / "kb"
KINDS = ("run", "state")          # the only two commands the UI may start
_popen = subprocess.Popen          # seams for tests
_run = subprocess.run
_lock = threading.Lock()
_current: dict = {}                # {"proc", "kind", "thaw", "started_at", "log"}


class SeasonError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def status(knowledge_dir: Path, transcript_dir: Path) -> dict:
    episodes = merge.load_episodes(knowledge_dir / "episodes.yaml")
    store = FrozenStore.load(knowledge_dir)
    stems = sorted(p.stem for p in transcript_dir.glob("*.json")) if transcript_dir.is_dir() else []
    by_video = {e["video_id"]: str(e.get("season", "")) for e in episodes["episodes"] if e.get("video_id")}
    # Transcript stems end in "_<video_id>" (pnp-crawl naming); no need to open 75 JSON files.
    season_of_stem = {s: next((sea for vid, sea in by_video.items() if s.endswith("_" + vid)), None) for s in stems}
    rows = []
    for key, spec in episodes["seasons"].items():
        manifest = store.manifests.get(key)
        rows.append({
            "key": key,
            "label": spec.get("label", key),
            "episodes": sum(1 for sea in by_video.values() if sea == key),
            "transcripts": sum(1 for sea in season_of_stem.values() if sea == key),
            "frozen": None if manifest is None else
                {k: manifest.get(k) for k in ("frozen_at", "prompt_versions", "models", "counts")},
        })
    return {
        "current": {"extract": EXTRACT_PROMPT_VERSION, "synth": SYNTH_PROMPT_VERSION, "state": STATE_PROMPT_VERSION},
        "seasons": rows,
        "unlisted_transcripts": [s for s, sea in season_of_stem.items() if sea is None],
        "error": episodes.get("error"),
    }


def _argv(kind: str, thaw: list[str], valid: set[str], estimate: bool) -> list[str]:
    if kind not in KINDS:
        raise SeasonError("Unknown run kind.")
    bad = [s for s in thaw if s not in valid]
    if bad:
        raise SeasonError(f"Unknown season: {', '.join(bad)}")
    argv = [sys.executable, "-m", "pnp_okf.cli", kind]
    if thaw:
        argv += ["--thaw", ",".join(sorted(thaw))]
    if estimate:
        argv.append("--estimate")
    return argv


def running() -> bool:
    proc = _current.get("proc")
    return proc is not None and proc.poll() is None


def estimate(kind: str, thaw: list[str], valid: set[str]) -> dict:
    done = _run(_argv(kind, thaw, valid, True), cwd=KB_DIR, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300)
    return {"ok": done.returncode == 0, "output": (done.stdout + done.stderr).strip()}


def freeze(season: str, from_cache: bool, valid: set[str]) -> dict:
    if season not in valid:
        raise SeasonError("Unknown season.", 404)
    with _lock:
        if running():
            raise SeasonError("A pipeline run is in progress.", 409)
        argv = [sys.executable, "-m", "pnp_okf.cli", "freeze", season] + (["--from-cache"] if from_cache else [])
        done = _run(argv, cwd=KB_DIR, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=600)
    return {"ok": done.returncode == 0, "output": (done.stdout + done.stderr).strip()}


def start(kind: str, thaw: list[str], valid: set[str]) -> dict:
    argv = _argv(kind, thaw, valid, False)
    with _lock:
        if running():
            raise SeasonError("A pipeline run is already in progress.", 409)
        log_path = KB_DIR / "state" / "ui_run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("w", encoding="utf-8")
        proc = _popen(argv, cwd=KB_DIR, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        _current.update(proc=proc, kind=kind, thaw=sorted(thaw), log=log_path,
                        started_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"))
    return current()


def current() -> dict:
    proc = _current.get("proc")
    log_path = _current.get("log")
    tail = ""
    if log_path and Path(log_path).is_file():
        tail = "\n".join(Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()[-40:])
    last_run = None
    last = KB_DIR / "state" / "last_run.json"
    if last.is_file():
        try:
            last_run = json.loads(last.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {
        "running": running(),
        "kind": _current.get("kind"),
        "thaw": _current.get("thaw", []),
        "started_at": _current.get("started_at"),
        "exit_code": None if proc is None else proc.poll(),
        "log_tail": tail,
        "last_run": last_run,
    }
```

`app.py`: `import seasons`; `from fastapi import Depends`; `from workbench_api import local_access`;
`from pnp_okf.config import default_transcript_dir`; `from pydantic import BaseModel, ConfigDict`.
Add before the `StaticFiles` mount:

```python
class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = "run"
    thaw: list[str] = []
    confirm: bool = False


class FreezeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_cache: bool = False


def _season_keys() -> set[str]:
    return set(merge.load_episodes(KNOWLEDGE_DIR / "episodes.yaml")["seasons"])


def _guarded(fn, *args):
    try:
        return fn(*args)
    except seasons.SeasonError as exc:
        raise HTTPException(exc.status, detail=str(exc)) from exc


Local = [Depends(local_access)]


@app.get("/api/seasons", dependencies=Local)
def season_status() -> dict:
    return seasons.status(KNOWLEDGE_DIR, default_transcript_dir())


@app.post("/api/seasons/{key}/freeze", dependencies=Local)
def season_freeze(key: str, payload: FreezeInput) -> dict:
    return _guarded(seasons.freeze, key, payload.from_cache, _season_keys())


@app.post("/api/runs/estimate", dependencies=Local)
def run_estimate(payload: RunInput) -> dict:
    return _guarded(seasons.estimate, payload.kind, payload.thaw, _season_keys())


@app.post("/api/runs", status_code=202, dependencies=Local)
def run_start(payload: RunInput) -> dict:
    """The one place the dashboard spends money: fixed argv, loopback-only, explicit confirm."""
    if not payload.confirm:
        raise HTTPException(400, "Kosten bestätigen, bevor der Lauf startet.")
    return _guarded(seasons.start, payload.kind, payload.thaw, _season_keys())


@app.get("/api/runs/current", dependencies=Local)
def run_current() -> dict:
    return seasons.current()
```

Update the module docstring of `app.py`: a second write path (freeze → `knowledge/frozen/`) and
the run endpoints. Same paragraph in `services/dashboard/README.md`.

Tests in `test_seasons.py` (client fixture as `test_workbench.py::client`:
`TestClient(app.app, client=("127.0.0.1", 45000))`; `monkeypatch.setattr(app, "KNOWLEDGE_DIR", tmp)`,
`monkeypatch.setattr(seasons, "KB_DIR", tmp/"kb")`, reset `seasons._current.clear()` per test;
fake process: object with `poll()` returning a settable value):

| Test | Asserts |
|---|---|
| `test_status_reports_frozen_and_active_seasons` | tmp `episodes.yaml` (P + 1), tmp `frozen/P/manifest.json`, two transcript stems → P row has `frozen.counts`, season 1 row `frozen is None`, counts correct. |
| `test_status_lists_transcripts_without_an_episode` | extra stem with unknown video id → in `unlisted_transcripts`. |
| `test_estimate_uses_fixed_argv` | `seasons._run` replaced by a recorder → argv == `[sys.executable,"-m","pnp_okf.cli","run","--thaw","P","--estimate"]`. |
| `test_unknown_season_is_rejected` | `thaw: ["P; rm -rf"]` → 400, recorder not called. |
| `test_unknown_kind_is_rejected` | `kind: "extract"` → 400. |
| `test_start_requires_confirm` | no `confirm` → 400, `_popen` recorder not called. |
| `test_second_start_is_a_conflict` | fake proc with `poll() -> None` → second POST 409. |
| `test_freeze_is_refused_while_running` | → 409. |
| `test_current_reports_exit_code_and_log_tail` | fake proc `poll() -> 0`, log file with 50 lines → `running False`, `exit_code 0`, 40 lines. |
| `test_remote_client_is_rejected` | `TestClient(app.app, client=("192.0.2.10", 123))` → 403 on `GET /api/seasons` and `POST /api/runs`. |

Checks: `cd $WT/services/dashboard && PYTHONPATH=$WT/services/kb/src $DBPY -m pytest -q` (all
green), ruff clean. Commit: `feat(dashboard): season status, freeze and run endpoints`.

---

## WP7 — dashboard frontend

Files in `services/dashboard/web/src`: `types.ts`, `useStatus.ts`, `components/Episodes.tsx`,
new `components/RunPanel.tsx`, `Dashboard.tsx`, new `components/RunPanel.test.tsx`,
new `components/Episodes.test.tsx`; new `e2e/seasons.spec.ts`. Read `web/AGENTS.md` first.
UI text is German, like the rest of `Dashboard.tsx`. Reuse existing classes (`panel`, `muted`,
`error`, `cell-yes`, `cell-no`, `cell-na`, `cell-mono`, `table-scroll`); no new CSS file.

`types.ts` — add:

```ts
export interface FrozenInfo {
  frozen_at: string;
  prompt_versions: { extract: string; synth: string; state: string | null };
  models: Record<string, string>;
  counts: { sessions: number; bodies: number; bodies_missing: number; state_sessions: number };
}
export interface SeasonStatus {
  key: string;
  label: string;
  episodes: number;
  transcripts: number;
  frozen: FrozenInfo | null;
}
export interface SeasonsResponse {
  current: { extract: string; synth: string; state: string };
  seasons: SeasonStatus[];
  unlisted_transcripts: string[];
  error?: string | null;
}
export interface RunState {
  running: boolean;
  kind: "run" | "state" | null;
  thaw: string[];
  started_at: string | null;
  exit_code: number | null;
  log_tail: string;
  last_run: { ok: boolean; error: string | null; ended_at: string } | null;
}
export interface CommandResult { ok: boolean; output: string }
```

`useStatus.ts` — add `export function useSeasons() { return useOnce<SeasonsResponse>("/api/seasons"); }`
and export a small `postJson<T>(url, body)` helper (fetch POST, JSON headers; on `!res.ok` throw
`Error` with the response's `detail` string or the status text).

`Episodes.tsx` — call `useSeasons()`. In each season `<h3>` after the count render:
- frozen: `<span className="cell-yes">eingefroren seit {frozen_at.slice(0,10)} · extract v{prompt_versions.extract}</span>`;
  if `prompt_versions.extract !== current.extract` add
  `<span className="cell-na"> (aktuell v{current.extract}, wird nicht neu gelesen)</span>`.
- not frozen: `<span className="cell-no">aktiv</span>` and a button **Einfrieren**. On click:
  `window.confirm("Staffel <label> einfrieren? Kostet nichts; die Pipeline liest sie danach nicht mehr neu.")`
  → `postJson("/api/seasons/<key>/freeze", {})` → show `output` in a `<pre>` under the heading,
  then `reload()` seasons. Errors render as `<p className="error">`.
- below the panel title, when `unlisted_transcripts.length > 0`:
  `<p className="cell-no">{n} Transkript(e) ohne Eintrag in episodes.yaml — keiner Staffel zugeordnet.</p>`.

`RunPanel.tsx` — `<section className="panel">` titled **Pipeline**:
1. radio `kind`: "Wissensbasis (pnp run)" / "Status-Pass (pnp state)".
2. one checkbox per **frozen** season: `{label} einmalig neu lesen`.
3. button **Kosten schätzen** → `postJson("/api/runs/estimate", {kind, thaw})` → `<pre>` with
   `output`. Changing kind or a checkbox clears the estimate.
4. peak note, computed from `new Date()` in UTC: Mon–Fri 01:00–04:00 or 06:00–10:00 →
   `<p className="cell-no">Jetzt Peak-Tarif: doppelter Preis.</p>`, else `<p className="muted">Off-Peak.</p>`.
   Export the pure function `isPeak(date: Date): boolean` for the test.
5. checkbox **Kosten gesehen** + button **Lauf starten**, enabled only when an estimate with
   `ok` is shown, the checkbox is ticked and nothing is running →
   `postJson("/api/runs", {kind, thaw, confirm: true})`.
6. run state: fetch `/api/runs/current` on mount; while `running`, poll every 3 s
   (`setInterval` in an effect, cleared on unmount and when `running` turns false). Show
   `läuft seit {started_at}` + `<pre>{log_tail}</pre>`; when finished show
   `fertig (exit {exit_code})` with `cell-yes` for 0, `cell-no` otherwise.

`Dashboard.tsx` — inside the existing `folgenMounted` block render `<RunPanel />` above
`<Episodes funnel={data.funnel} />`.

Vitest (pattern: `src/App.test.tsx`, `vi.stubGlobal("fetch", …)`):

| Test | Asserts |
|---|---|
| `Episodes.test.tsx` › "marks a frozen season and offers freezing for an active one" | Prolog heading contains "eingefroren seit"; Staffel 1 has a button "Einfrieren". |
| › "warns about transcripts without an episode" | text "ohne Eintrag in episodes.yaml" visible. |
| `RunPanel.test.tsx` › "start stays disabled until an estimate is shown and confirmed" | button disabled → after estimate + checkbox enabled. |
| › "sends the thawed seasons with the start request" | fetch called with `/api/runs` and body `{"kind":"run","thaw":["P"],"confirm":true}`. |
| › "changing the selection clears the estimate" | estimate `<pre>` gone, start disabled again. |
| › "isPeak" | `2026-11-11T07:00:00Z` (Wed) true; `2026-11-11T12:00:00Z` false; `2026-11-14T07:00:00Z` (Sat) false. |

Playwright `e2e/seasons.spec.ts`: one test. Start the isolated server (`fixtures.ts`), stub
`**/api/seasons`, `**/api/runs/estimate`, `**/api/runs`, `**/api/runs/current`, `**/api/status`,
`**/api/episodes`, `**/api/history*` with `page.route` (fictional data only; the real
`/api/runs` must never be hit), open Technical dashboard → Folgen, estimate, confirm, start,
assert the log text appears. No fixed sleeps.

Checks (from `$WT/services/dashboard/web`, after `npm ci`): `npm run lint`, `npm run typecheck`,
`npm test`, `PNP_TEST_PYTHON=$DBPY npm run test:e2e -- seasons`. Visual baselines are not
regenerated: report "Linux visual check pending" as `web/AGENTS.md` allows.
Commit: `feat(dashboard): manage seasons and start runs from the Folgen tab`.

---

## WP8 — docs

Files: `docs/architecture/PIPELINE.md`, `.env.example`, `AGENTS.md`, `docs/RELEASING.md`,
`services/kb/README.md` (only if it lists subcommands).

- `PIPELINE.md`: new `## 6a. Season freeze` after §6: R1–R9 in prose, the dir layout, the
  precedence line (R14), the two-step thaw (`run --thaw P`, then `freeze P --from-cache`), and
  "transcripts of frozen seasons are still read from disk, never sent to the model". Add
  `freeze` to the subcommand list in §3, one row to §13 ("re-read an old season" → §6a), and a
  note in §6 that `PNP_EXTRACT_FREEZE_*` is superseded by §6a for whole seasons.
- `.env.example`: one comment line above `PNP_EXTRACT_FREEZE_BEFORE` pointing to §6a.
- `AGENTS.md` "Guards" bullet: add "A run started from the dashboard's Folgen tab is a human
  run; agents never click it and never call `POST /api/runs`."
- `docs/RELEASING.md`: after a freeze, in `knowledge/`: branch, commit `frozen/<season>/`, PR,
  tag `season-<key>-v<extract version>`.

Check: `ruff check .` (docs only, sanity) and links resolve. Commit: `docs: document season freeze`.

---

## 6. HUMAN RUN (after merge; none of this is done by an agent)

1. Warm `pnp run` on the real tree. Clears the stale 2026-10-18 marker, unblocks the `s68` tag.
2. Optional, ~$2–4: `pnp state --refresh-glossary`, then `pnp state`, so the snapshot gets state.
   Can be done later; `pnp freeze P` again then only adds the state files.
3. `pnp freeze P` (or the Einfrieren button). Expect `55 session(s)`.
4. `pnp run --estimate` → `frozen:   55 session(s) in season(s) P`.
5. Warm `pnp run`; `git -C knowledge status --short` must show only `frozen/P/` as new.
6. In `knowledge/`: branch, commit, PR, tag `season-P-v6`.
7. Separate, in `pnp-crawl`: `python sync_episodes.py --write`. `episodes.yaml` lists 5 Staffel-1
   episodes against ~20 Staffel-1 transcripts; the UI will show the rest as "ohne Eintrag".

## 7. Done when

- [ ] kb suite, dashboard suite, vitest, typecheck, lint, the seasons e2e spec: green.
- [ ] No diff in `prompts.py`, `knowledge/`, `graph/`, `.claude/hooks/`.
- [ ] `tests/test_prompt_pins.py` green (no version moved).
- [ ] The raising-client tests prove R3 for extraction, synthesis and state.
- [ ] HUMAN RUN 3–5 done: Prolog frozen, estimate prices only Staffel 1, warm run changes nothing.

```bash
cd $WT && git diff origin/main...HEAD --stat -- services/kb/src/pnp_okf/prompts.py knowledge graph .claude/hooks   # empty
cd $WT/services/kb && $KBPY -m pytest -q
cd $WT/services/kb && $KBPY -m pytest -q tests/test_prompt_pins.py tests/test_frozen_store.py tests/test_frozen_wiring.py tests/test_freeze_command.py
cd $WT/services/dashboard && PYTHONPATH=$WT/services/kb/src $DBPY -m pytest -q
cd $WT/services/dashboard/web && npm run lint && npm run typecheck && npm test
cd $WT && $KBPY -m ruff check .
```

## 8. Risks

- **UI-started paid runs** bypass the agent guard by design. Mitigated by loopback-only routes,
  a two-command whitelist, season keys validated against `episodes.yaml`, estimate-then-confirm,
  one run at a time.
- **Frozen body goes stale against new rules** (new alias, renamed canonical name). Accepted;
  mention changes are caught by the fingerprint, everything else needs `--thaw`.
- **State cascade**: thawing a season re-runs the state pass for every later session (existing T5 behaviour).
- **Dashboard restart during a run** loses the process handle; the run keeps going and
  `last_run.json` still reports it. Upgrade path if it bites: persist the pid next to `ui_run.log`.
- **Repo size**: 55 extractions plus several hundred bodies as JSON in `knowledge/`. A few MB.
