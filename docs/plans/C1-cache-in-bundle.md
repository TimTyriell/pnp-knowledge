# C1 — Track the LLM cache in the bundle repo, with tag-based garbage collection

Repo: `pnp-knowledge` (code + docs) and `knowledge/` = private `pnp-knowledge-bundle` (data).
Branch `feat/cache-in-bundle`, cut from `origin/main` **after PR #40 (season freeze) is merged**.
This plan is written so Haiku workers can implement each work package (WP) without making design
decisions, and a Sonnet reviewer checks each one. Anchors (`def …`) are authoritative. Line
numbers are from `main` @ `ada3750` (2026-11-11) and will have shifted after #40.

## 1. Context

The DeepSeek caches (`services/kb/.cache/extract/` + `synth/`; 6.8 MB, 1,254 files, 71 sessions,
1,150 entities) are gitignored (`services/kb/.gitignore:5`) and exist on one disk only. They are
paid (~$6.50 for a rebuild) and can't be reproduced: re-extraction resamples names and moves
concept ids (PIPELINE.md §4.2: 432 of 868 ids in one run). Every worktree, and every other
person, starts cold.

`pnp-knowledge` is **public** and the cache contains transcript text and player names, so the
cache moves into the **private bundle repo** as `knowledge/cache/`, next to `knowledge/frozen/`
(PR #40). Bundle tag `s<NN>` then pins the bundle and the cache that built it.

Lifecycle: an entry is **stale** when the current config no longer reaches its key. That covers a
prompt or model change, an edited transcript, an entity that was renamed, merged or anchored
away, or a session now served from `knowledge/frozen/`. A stale entry is deleted automatically
once it has stayed stale through **2 session tags**. Git history keeps every deleted file.

Decisions (user, 2026-11-11): location = bundle repo; condition X = stale for N session tags.

## 2. Requirements

| # | Requirement |
|---|---|
| R1 | Default cache dir = `<knowledge_root>/cache` when `<knowledge_root>/entity_registry.yaml` exists. Precedence: `--cache` > `PNP_CACHE_DIR` > `<knowledge_root>/cache` > `./.cache`. |
| R2 | Paid/cache commands (`run`, `extract`, `state`, `dedup`, `cache gc`) **exit 2** when the default cache has no extract entries but the legacy `services/kb/.cache` has some. The message names `pnp cache migrate`. This never applies when `--cache`/`PNP_CACHE_DIR` is set. |
| R3 | `pnp cache migrate [--from DIR] [--dry-run]` copies the legacy cache into the default cache. It skips identical files, never overwrites a differing file (it reports it and exits 1), and never deletes the source. |
| R4 | GC only ever touches files matching `^(extract\|synth)/[^/]+/[0-9a-f]{16}\.json$` relative to the cache dir. `state/`, `gc_ledger.json` and anything else are never deleted. |
| R5 | Live set = exactly the extract + synth cache paths the current config would read for the **full** transcript set. A live file is never deleted. |
| R6 | The live set is **unknown (sweep aborts, deletes nothing, ledger untouched)** if: any transcript has no cached extraction under the current config; any `extract/<session_id>/` dir has no matching transcript (and no frozen file); or there are zero transcripts. |
| R7 | Ledger `cache/gc_ledger.json` = `{"schema": 1, "stale_since": {"<rel path>": "<tag>" \| null}}`, sorted keys, LF line endings, written only when changed. |
| R8 | A newly stale entry is stamped with the latest `s<NN>` tag (or `null` if there is none). An entry stamped `s<k>` is deleted when `latest_seq - k >= keep` (default `keep=2`). `null` stamps get the current tag on the first tagged sweep. **No tag → nothing is ever deleted.** |
| R9 | An entry that becomes live again leaves the ledger, so its grace restarts if it goes stale again later. |
| R10 | Mass guard: if the due deletions of one kind (extract or synth) exceed 50% of that kind's entries, delete nothing of that kind and report it as `blocked`. `pnp cache gc --allow-mass` overrides; the automatic sweep never does. |
| R11 | The automatic sweep runs at the end of a successful `pnp run` that is not partial (no `--limit`/`--session`) and not `--estimate`, using the run's own post-filter `entities`. It never changes the run's exit code: errors are logged as warnings. |
| R12 | `pnp cache gc [--dry-run] [--keep N] [--allow-mass]` costs $0, makes no model call, and prints counts plus the paths it deleted or would delete. |
| R13 | `pnp check` counts extract/synth entries with the post-2026-09-07 layout (`*/*.json`). Today it globs `*.json` and always prints 0. |
| R14 | No prompt-version change, no model call, no agent edit under `knowledge/`, no change to `.claude/hooks/`. |

Out of scope: state-cache GC (no `state/` on disk yet; add it when it exists). Git LFS or a history
rewrite (7 MB of immutable blobs). Age-in-days conditions (mtime doesn't survive `git checkout`).
Refactoring `_estimate_run` onto the live set (the parity test guards drift instead).

## 3. How to execute (orchestrator = main session)

```bash
cd c:/dev/lindo-lauts-notebook/pnp-knowledge
git fetch origin
git worktree add ../.wt/pnp-knowledge-cache-gc -b feat/cache-in-bundle origin/main
```
`$WT = c:/dev/lindo-lauts-notebook/.wt/pnp-knowledge-cache-gc`. Never work in the shared checkout,
because other sessions branch-switch it. The worktree has no venv, so use the main checkout's:
```bash
KBPY=c:/dev/lindo-lauts-notebook/pnp-knowledge/services/kb/.venv/Scripts/python.exe
cd $WT/services/kb && $KBPY -m pytest -q          # pyproject pythonpath=src → worktree source wins
cd $WT && $KBPY -m ruff check .
```
Loop over WP1…WP6 **in order**, one at a time:
1. Worker: `Agent(subagent_type="general-purpose", model="haiku")`. Prompt = §4 rules + full WP text + the commands above.
2. Reviewer: `Agent(subagent_type="general-purpose", model="sonnet")`. Prompt = §2 + WP text + §5 + "review `git -C $WT show HEAD`; do not edit".
3. `CHANGES` → `SendMessage` the findings to the same worker, who fixes them in a new commit. At most 2 rounds, then the orchestrator decides.
4. After WP6: full suite + ruff, push, `gh pr create --base main`, `/review-pr <n>`. WP7 is HUMAN RUN.

**WP0 (orchestrator, before WP1).** Read merged #40 (`services/kb/src/pnp_okf/frozen.py`, its
wiring in `cli.py`). Then write into this plan's WP3 code the two names marked `WP0:`:
- the function that returns frozen extractions for a list of transcripts (thaw = none)
- the predicate for "this entity's body comes from a frozen file"

Also re-check that the hard-coded `.cache` call sites in WP5 still exist. If #40 is not merged,
stop.

## 4. Rules for every worker (paste verbatim)

1. Work only in `$WT`. Never `git switch`. Never touch `graph/`, `knowledge/`, `.claude/hooks/`, `prompts.py`, any `*_PROMPT_VERSION`.
2. **Never call DeepSeek.** Never run `pnp run|extract|state|dedup` without `--estimate`. Never run `pnp cache gc`/`migrate` against the real repo, only against `tmp_path`. Real-data steps are HUMAN RUN.
3. Tests first: write the WP's tests, run them, see them fail, then implement.
4. Use Write/Edit for source, never bash heredocs.
5. Comments explain *why*, in the surrounding style. No new dependencies. Python 3.11.
6. If the code doesn't match the WP (missing function, different signature, taken test name), **STOP and report**. Don't improvise.
7. Commit per WP: Conventional Commits, subject ≤72 chars, body says why, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Stage only the files the WP names.
8. Final message: files changed, each command run and its last output line, anything skipped.

## 5. Reviewer checklist

Report `VERDICT: OK` or `VERDICT: CHANGES`, with findings as `path:line — problem — fix`.
- The diff touches only the WP's files. None of the forbidden paths from §4.1.
- Every listed test exists and asserts what the WP says (not weaker). Run them and paste the last line.
- No path deletes a file outside R4's regex, or deletes anything when the live set is `None`.
- No `except` widens beyond what the WP specifies. Only `_sweep_after_run` may catch `Exception`.
- Signatures that existing tests monkeypatch are unchanged: `extract_session(transcript, cfg, cache_dir, *, client=None, force=False)`, `synthesize_entity_body(...)`.
- New args are optional, with defaults that keep today's behaviour.

---

## WP1 — default cache dir + legacy constant

Files: `services/kb/src/pnp_okf/config.py`, `services/kb/tests/test_paths.py`.

In `config.py`:
```python
# Where the cache lived before it moved into the bundle repo (C1). Anchored on
# this file: src/pnp_okf/config.py -> parents[2] is services/kb.
LEGACY_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
```
In `Paths.resolve`, replace `cache = cache_dir or os.environ.get("PNP_CACHE_DIR") or "./.cache"` with:
```python
cache = cache_dir or os.environ.get("PNP_CACHE_DIR") or cls._default_cache(Path(bundle).expanduser())
```
and add:
```python
@staticmethod
def _default_cache(bundle: Path) -> str:
    """knowledge/cache when a real knowledge root sits behind the bundle.

    The cache is paid, unreproducible output keyed to this campaign, so it is
    versioned with the bundle (private repo) instead of beside the public code.
    Without a registry the root is not a campaign checkout; keep the old
    cwd-relative default so ad-hoc runs never write into a stranger's tree.
    """
    root = bundle.parent.parent if bundle.parent.name == "bundle" else bundle.parent
    if (root / "entity_registry.yaml").is_file():
        return str(root / "cache")
    return "./.cache"
```
(The root logic mirrors `Paths._knowledge_root`. Keep both and don't refactor the property.)

Tests (append to `test_paths.py`, reuse `_knowledge`):

| ID | Test | Asserts |
|---|---|---|
| T1.1 | `test_default_cache_is_knowledge_cache` | `Paths.resolve(bundle=<k>/bundle/splitter_des_ewigen)` with `PNP_CACHE_DIR` unset → `cache_dir == k/"cache"` |
| T1.2 | `test_env_cache_beats_default` | `PNP_CACHE_DIR=X` → `cache_dir == X` |
| T1.3 | `test_explicit_cache_beats_env` | arg beats env |
| T1.4 | `test_no_registry_falls_back_to_dot_cache` | bundle without a registry beside it → `cache_dir == Path("./.cache")` |
| T1.5 | `test_legacy_cache_dir_points_at_services_kb` | `LEGACY_CACHE_DIR.parent.name == "kb"` and `.parent.parent.name == "services"` |

Use `monkeypatch.delenv("PNP_CACHE_DIR", raising=False)` in every test.
Check: `pytest -q tests/test_paths.py`. Commit: `feat(kb): default the cache to knowledge/cache`.

---

## WP2 — `cache_gc.py`: ledger, tags, sweep (pure; no pipeline imports)

Files: new `services/kb/src/pnp_okf/cache_gc.py`, new `services/kb/tests/test_cache_gc.py`.

Write exactly this. The module docstring states the lifecycle rule (§1), R4, R6, R8, R10 and names
this plan.
```python
from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

KEEP_TAGS = 2
MAX_DUE_RATIO = 0.5
LEDGER_NAME = "gc_ledger.json"
_ENTRY = re.compile(r"^(extract|synth)/[^/]+/[0-9a-f]{16}\.json$")
_TAG = re.compile(r"^s(\d+)$")


def _seq(tag: str | None) -> int | None:
    m = _TAG.match(tag) if tag else None
    return int(m.group(1)) if m else None


def cache_entries(cache_dir: Path) -> set[str]:
    """Every GC-able cache file, as a posix path relative to cache_dir."""
    out: set[str] = set()
    for kind in ("extract", "synth"):
        for p in (cache_dir / kind).glob("*/*.json"):
            rel = p.relative_to(cache_dir).as_posix()
            if _ENTRY.match(rel):
                out.add(rel)
    return out


def latest_session_tag(repo: Path) -> str | None:
    """Highest s<NN> tag in repo, or None (no git, not a repo, no tag)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "tag", "--list", "s*"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    tags = [(n, t) for t in out.split() if (n := _seq(t)) is not None]
    return max(tags)[1] if tags else None


def load_ledger(cache_dir: Path) -> dict[str, str | None]:
    path = cache_dir / LEDGER_NAME
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise ValueError(f"{path}: unknown ledger schema {data.get('schema')!r}")
    return dict(data["stale_since"])


def write_ledger(cache_dir: Path, ledger: dict[str, str | None]) -> None:
    text = json.dumps({"schema": 1, "stale_since": dict(sorted(ledger.items()))},
                      indent=2, ensure_ascii=False) + "\n"
    path = cache_dir / LEDGER_NAME
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8", newline="\n")


@dataclass
class SweepReport:
    tag: str | None
    live: int = 0
    newly_stale: list[str] = field(default_factory=list)
    waiting: int = 0
    deleted: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)

    def summary(self, dry_run: bool = False) -> str:
        verb = "would delete" if dry_run else "deleted"
        return (f"cache gc (tag {self.tag or 'none'}): {self.live} live, "
                f"{len(self.newly_stale)} newly stale, {self.waiting} waiting, "
                f"{verb} {len(self.deleted)}, blocked {len(self.blocked)}")


def sweep(cache_dir: Path, live: set[str], tag: str | None, *, keep: int = KEEP_TAGS,
          dry_run: bool = False, allow_mass: bool = False) -> SweepReport:
    entries = cache_entries(cache_dir)
    old = load_ledger(cache_dir)
    new: dict[str, str | None] = {}
    report = SweepReport(tag=tag)
    cur = _seq(tag)
    due: list[str] = []
    for rel in sorted(entries):
        if rel in live:
            report.live += 1
            continue
        if rel not in old:
            report.newly_stale.append(rel)
            new[rel] = tag
            continue
        stamp = old[rel] if old[rel] is not None else tag
        new[rel] = stamp
        k = _seq(stamp)
        if cur is not None and k is not None and cur - k >= keep:
            due.append(rel)
        else:
            report.waiting += 1
    for kind in ("extract", "synth"):
        mine = [r for r in due if r.startswith(kind + "/")]
        total = sum(1 for e in entries if e.startswith(kind + "/"))
        if mine and not allow_mass and len(mine) > MAX_DUE_RATIO * total:
            report.blocked += mine
    for rel in due:
        if rel in report.blocked:
            continue
        report.deleted.append(rel)
        del new[rel]
        if not dry_run:
            path = cache_dir / rel
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()   # only succeeds when empty
            except OSError:
                pass
    if not dry_run:
        write_ledger(cache_dir, new)
    return report
```

Tests: build a cache in `tmp_path` with a helper `_entry(cache, "extract/s1/" + "a"*16 + ".json")`
that writes `{}`. Pass `live` and `tag` directly. No pipeline involved. Deletion tests need at least
one extra **live** entry of the same kind, because a single-entry cache always trips the R10 mass
guard (1 of 1 > 50%). `sweep(live=None)` raises `ValueError` (test `test_none_live_set_raises`).
T2.15 sets `GIT_CEILING_DIRECTORIES=tmp_path`.

| ID | Test | Given → Then |
|---|---|---|
| T2.1 | `test_live_entry_is_never_touched` | entry in `live`, ledger says stale since `s1`, tag `s9` → file exists, not in ledger |
| T2.2 | `test_new_stale_entry_is_stamped_with_current_tag` | stale, tag `s5` → ledger `{rel: "s5"}`, file exists |
| T2.3 | `test_deleted_only_after_keep_tags` | stamped `s5`: sweep at `s6` → kept (`waiting==1`); at `s7` → deleted, not in ledger |
| T2.4 | `test_keep_is_configurable` | `keep=1`, stamped `s5`, tag `s6` → deleted |
| T2.5 | `test_relive_entry_leaves_ledger` | stamped `s5`, now in `live` → ledger empty, file exists |
| T2.6 | `test_no_tag_never_deletes` | stamped `s1`, tag `None` → file exists |
| T2.7 | `test_null_stamp_gets_first_tag` | ledger `{rel: None}`, tag `s3` → ledger `{rel: "s3"}`, file exists |
| T2.8 | `test_foreign_files_never_touched` | `state/s1/x.json`, `extract/s1/notakey.json`, `ledger_report.md`, `extract/flat.json` → all exist after sweeps at `s1` then `s9` with an empty `live` |
| T2.9 | `test_dry_run_writes_nothing` | due entry, `dry_run=True` → file exists, ledger file content unchanged, `report.deleted == [rel]` |
| T2.10 | `test_empty_entity_dir_removed` | last file of `synth/x/` deleted → `synth/x` gone; sibling with a live file stays |
| T2.11 | `test_mass_guard_blocks_per_kind` | 3 extract entries, 2 due → blocked, none deleted; `allow_mass=True` → 2 deleted |
| T2.12 | `test_mass_guard_is_per_kind` | 1 of 4 synth due and 3 of 4 extract due → synth deleted, extract blocked |
| T2.13 | `test_bad_ledger_schema_raises` | ledger `{"schema": 2}` → `ValueError` |
| T2.14 | `test_ledger_is_sorted_lf_and_stable` | two sweeps with the same state → identical bytes, no `\r` |
| T2.15 | `test_tag_ordering_is_numeric` | `git init` + commit + tags `s9`, `s10`, `s2`, `v1` in tmp → `latest_session_tag == "s10"`; no git dir → `None`. Skip if `shutil.which("git")` is None |

Check: `pytest -q tests/test_cache_gc.py`. Commit: `feat(kb): cache GC ledger and tag-based sweep`.

---

## WP3 — live set (mark)

Files: `services/kb/src/pnp_okf/cache_gc.py` (append), `services/kb/tests/test_cache_gc_live.py` (new).

Append to `cache_gc.py` (imports at top of module):
```python
from pnp_okf.config import DeepSeekConfig, Paths
from pnp_okf.context import excerpts_for, load_sources, secondary_sources_for, sources_for
from pnp_okf.extract import _cache_key as extract_cache_key
from pnp_okf.extract import _cache_path as extract_cache_path
from pnp_okf.extract import load_cached_extraction
from pnp_okf.frozen import FrozenStore
from pnp_okf.models import CanonicalEntity, EntityType, SessionTranscript
from pnp_okf.resolve import load_event_concepts, resolve_entities
from pnp_okf.synthesize import _cache_key as synth_cache_key
from pnp_okf.synthesize import _cache_path as synth_cache_path


def live_entries(paths: Paths, transcripts: list[SessionTranscript],
                 entities: list[CanonicalEntity] | None = None,
                 frozen: FrozenStore | None = None) -> set[str] | None:
    """Cache paths the current config reads for the full transcript set; None = unknown.

    `entities` and `frozen` are the run's own post-filter list and (thaw-aware)
    frozen store when called from `pnp run`. Otherwise resolve here, load the
    frozen store with nothing thawed, and mirror the T4 event filter in
    cli._run_pipeline; test_live_set_matches_what_a_run_writes catches drift.
    """
    if not transcripts:
        log.warning("cache gc: no transcripts; not sweeping")
        return None
    cache = paths.cache_dir
    if frozen is None:
        frozen = FrozenStore.load(paths.knowledge_root)
    known = {t.session_id for t in transcripts}
    orphans = sorted(p.name for p in (cache / "extract").glob("*")
                     if p.is_dir() and p.name not in known and frozen.season_of(p.name) is None)
    if orphans:
        log.warning("cache gc: cache holds sessions with no transcript (%s); not sweeping",
                    ", ".join(orphans[:5]))
        return None
    cfg = DeepSeekConfig.from_env().for_tier("extract")
    live: set[str] = set()
    extractions = {}
    for t in transcripts:
        hit = frozen.extraction(t)
        if hit is not None:
            extractions[t.session_id] = hit
            continue  # served from knowledge/frozen; its cache entries are stale by design
        ex = load_cached_extraction(cache, t, cfg)
        if ex is None:
            log.warning("cache gc: %s has no cached extraction; not sweeping", t.session_id)
            return None
        live.add(extract_cache_path(cache, t, extract_cache_key(t, cfg)).relative_to(cache).as_posix())
        extractions[t.session_id] = ex
    tmap = {t.session_id: t for t in transcripts}
    if entities is None:
        entities = resolve_entities(extractions, tmap, paths.registry_path)
        keep_events = load_event_concepts(paths.registry_path)
        entities = [e for e in entities
                    if e.type != EntityType.EVENT or e.concept_id in keep_events]
    base = DeepSeekConfig.from_env()
    sections = load_sources(paths.sources_dir)
    for e in entities:
        if e.tier == "brief":
            continue  # rendered locally, never cached
        if frozen.body(e) is not None:
            continue  # body served from knowledge/frozen, exactly as _run_pipeline._synth does
        key = synth_cache_key(
            e, base.for_tier(e.tier), sources_for(e, sections),
            excerpts_for(e, tmap) if e.tier == "deep" else "",
            secondary_sources_for(e, sections),
        )
        live.add(synth_cache_path(cache, e, key).relative_to(cache).as_posix())
    return live
```
If any import name doesn't exist (for example `load_event_concepts` moved), STOP.

Tests (reuse `_write_transcript_json` / `_offline_run_args` patterns from `tests/test_pipeline_offline.py`; copy them, don't import across test files). Set `DEEPSEEK_API_KEY=test-key` and `PNP_STATE_DIR=tmp/state`. Seed the extract cache like `tests/test_cli.py::_seed_extract_cache`.

| ID | Test | Asserts |
|---|---|---|
| T3.1 | `test_live_set_matches_what_a_run_writes` | **Parity, the key test.** 2 transcripts, both seeded with an extraction naming the same NPC (so it's above brief tier). Monkeypatch `pnp_okf.synthesize.build_client` → `lambda cfg: object()` and `pnp_okf.synthesize._call_llm` → returns `"Text."`. Run `cli._run_pipeline(args, "2026-11-11T00:00:00Z") == 0`. Then `live_entries(paths, transcripts) == cache_entries(cache_dir)`, and at least one `synth/` path is in the set (if none, the NPC is still brief: add mentions, at most 5, then STOP). |
| T3.2 | `test_missing_extraction_returns_none` | 2 transcripts, only 1 seeded → `None` |
| T3.3 | `test_orphan_session_dir_returns_none` | extra dir `extract/2020-01-01_X_y/` with no transcript → `None` |
| T3.4 | `test_no_transcripts_returns_none` | `[]` → `None` |
| T3.5 | `test_prompt_version_change_makes_old_entry_stale` | seed, then monkeypatch `pnp_okf.extract._frozen_prompt_version` → `"999"`; seed again → live contains only the new key, and the old file is in `cache_entries - live` |
| T3.6 | `test_model_change_makes_old_entry_stale` | the same via `DEEPSEEK_MODEL` env change between seeding and marking. The old key is not live, and the result is `None` because the new key isn't cached. Assert `None` (protects against a wrong env wiping the cache) |
| T3.7 | `test_run_entities_are_used_when_given` | pass `entities=[]` → live contains only extract paths |
| T3.8 | (only if #40 merged) `test_frozen_session_entries_are_stale` | frozen session's extraction → its cache entry is not in live, and the result is not `None` without a cache entry |

Check: `pytest -q tests/test_cache_gc_live.py tests/test_cache_gc.py`. Commit: `feat(kb): compute the live cache set`.

---

## WP4 — CLI: `cache gc`, `cache migrate`, legacy trap, auto-sweep, `check` fix

Files: `services/kb/src/pnp_okf/cli.py`, `services/kb/src/pnp_okf/cache_gc.py` (add `migrate`), `services/kb/tests/test_cache_cli.py` (new).

**4a. `migrate` in `cache_gc.py`:**
```python
@dataclass
class MigrateReport:
    copied: int = 0
    identical: int = 0
    conflicts: list[str] = field(default_factory=list)


def migrate(src: Path, dst: Path, *, dry_run: bool = False) -> MigrateReport:
    """Copy src/{extract,synth,state}/** into dst. Never overwrites, never deletes src."""
    rep = MigrateReport()
    for kind in ("extract", "synth", "state"):
        for p in sorted((src / kind).rglob("*")):
            if not p.is_file():
                continue
            target = dst / p.relative_to(src)
            if target.exists():
                same = target.read_bytes() == p.read_bytes() or (
                    p.suffix == ".json" and json.loads(target.read_text(encoding="utf-8"))
                    == json.loads(p.read_text(encoding="utf-8")))
                if same:
                    rep.identical += 1
                else:
                    rep.conflicts.append(target.relative_to(dst).as_posix())
                continue
            rep.copied += 1
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(p.read_bytes())
    return rep
```
(The JSON-equality fallback exists because CRLF/LF differences between Windows and Linux
writers are not conflicts.)

**4b. Parser.** In `_build_parser`, after `validate`:
```python
cache = sub.add_parser("cache", help="Cache housekeeping (free, no model calls)")
cache_sub = cache.add_subparsers(dest="cache_command", required=True)
gc = cache_sub.add_parser("gc", help="Delete cache entries stale for --keep session tags")
for flag in ("--transcripts", "--bundle", "--cache"):
    gc.add_argument(flag)
gc.add_argument("--keep", type=int, default=KEEP_TAGS)
gc.add_argument("--dry-run", action="store_true")
gc.add_argument("--allow-mass", action="store_true",
                help="Allow deleting more than half of one kind's entries in one sweep")
gc.set_defaults(func=cmd_cache_gc)
mig = cache_sub.add_parser("migrate", help="Copy the legacy services/kb/.cache into the default cache")
mig.add_argument("--from", dest="src", default=str(LEGACY_CACHE_DIR))
for flag in ("--bundle", "--cache"):
    mig.add_argument(flag)
mig.add_argument("--dry-run", action="store_true")
mig.set_defaults(func=cmd_cache_migrate, transcripts=None)
```
**4c. Commands:**
```python
def cmd_cache_gc(args: argparse.Namespace) -> int:
    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    live = live_entries(paths, load_transcripts(paths.transcript_dir))
    if live is None:
        print("cache gc: live set unknown (see warnings); nothing deleted.")
        return 2
    rep = sweep(paths.cache_dir, live, latest_session_tag(paths.knowledge_root),
                keep=args.keep, dry_run=args.dry_run, allow_mass=args.allow_mass)
    for rel in rep.deleted:
        print(("would delete " if args.dry_run else "deleted ") + rel)
    for rel in rep.blocked:
        print("blocked " + rel)
    print(rep.summary(args.dry_run))
    if rep.blocked:
        print("Mass deletion held back. Inspect with --dry-run, then re-run with --allow-mass.")
    return 0


def cmd_cache_migrate(args: argparse.Namespace) -> int:
    paths = Paths.resolve(None, args.bundle, args.cache)
    src = Path(args.src)
    if src.resolve() == paths.cache_dir.resolve():
        print(f"source and target are the same ({src}); nothing to do")
        return 2
    rep = migrate(src, paths.cache_dir, dry_run=args.dry_run)
    print(f"cache migrate {src} -> {paths.cache_dir}: {rep.copied} copied, "
          f"{rep.identical} identical, {len(rep.conflicts)} conflict(s)")
    for rel in rep.conflicts:
        print("conflict (left untouched): " + rel)
    return 1 if rep.conflicts else 0
```
**4d. Legacy trap (R2).** Add `_legacy_cache_trap(args) -> str | None` and call it in `main()` right
before `return args.func(args)`: if it returns a message, `log.error(msg)` and `return 2`.
```python
_CACHE_COMMANDS = {"run", "extract", "state", "dedup"}

def _legacy_cache_trap(args: argparse.Namespace) -> str | None:
    """Refuse to start cold when the warm cache is still at the pre-C1 location."""
    is_gc = args.command == "cache" and getattr(args, "cache_command", None) == "gc"
    if args.command not in _CACHE_COMMANDS and not is_gc:
        return None
    if getattr(args, "cache", None) or os.environ.get("PNP_CACHE_DIR"):
        return None
    paths = Paths.resolve(getattr(args, "transcripts", None), getattr(args, "bundle", None), None)
    has = lambda d: any(d.glob("extract/*/*.json"))  # noqa: E731
    if paths.cache_dir.resolve() != LEGACY_CACHE_DIR and not has(paths.cache_dir) and has(LEGACY_CACHE_DIR):
        return (f"The default cache {paths.cache_dir} is empty but {LEGACY_CACHE_DIR} is warm. "
                "Running now would re-buy every extraction. Run `pnp cache migrate` first, "
                "or pass --cache to choose explicitly.")
    return None
```
**4e. Auto-sweep (R11).** Add:
```python
def _sweep_after_run(paths: Paths, transcripts: list[SessionTranscript],
                     entities: list[CanonicalEntity]) -> None:
    # Housekeeping after the bundle is already written and validated: a GC
    # problem must never turn a good run into a failed one.
    try:
        live = live_entries(paths, transcripts, entities)
        if live is None:
            return
        rep = sweep(paths.cache_dir, live, latest_session_tag(paths.knowledge_root))
        log.info("%s", rep.summary())
        if rep.blocked:
            log.warning("cache gc held back %d deletion(s); run `pnp cache gc --dry-run` "
                        "then `--allow-mass`.", len(rep.blocked))
    except Exception as exc:  # noqa: BLE001
        log.warning("cache gc skipped: %s", exc)
```
In `_run_pipeline`, immediately before the final `_write_run_status(started_at, ok=True, …)`:
```python
if not partial_run:
    _sweep_after_run(paths, transcripts, entities, frozen)
```
(`_sweep_after_run` gets a 4th parameter `frozen: FrozenStore` and passes it as
`live_entries(paths, transcripts, entities, frozen)`, so a `--thaw` run keeps the thawed season's
cache entries live.)
`entities` must be the same variable `_synth` was mapped over (after the T4 event filter). If it
was reassigned in between, STOP.

**4f. `cmd_check` (R13):** change both globs from `"*.json"` to `"*/*.json"`.

Tests (`test_cache_cli.py`, all in `tmp_path`, all through `main([...])`):

| ID | Test | Asserts |
|---|---|---|
| T4.1 | `test_cache_gc_dry_run_deletes_nothing` | seeded run fixture + stale entry stamped `s1`, git tags `s1..s3` → exit 0, stdout has `would delete`, file exists |
| T4.2 | `test_cache_gc_unknown_live_set_exits_2` | missing extraction → exit 2, no ledger written |
| T4.3 | `test_cache_gc_blocked_exits_0_and_says_allow_mass` | mass case → stdout contains `--allow-mass`, files exist |
| T4.4 | `test_legacy_trap_refuses_cold_default` | monkeypatch `cli.LEGACY_CACHE_DIR` to a seeded tmp dir, default cache empty → `main(["run","--estimate", "--bundle", …])` exits 2, message contains `pnp cache migrate` |
| T4.5 | `test_legacy_trap_ignored_with_explicit_cache` | same, with `--cache` → not 2 for that reason |
| T4.6 | `test_legacy_trap_ignored_when_default_warm` | both warm → no trap |
| T4.7 | `test_migrate_copies_and_never_deletes_source` | → copied count, source still intact |
| T4.8 | `test_migrate_skips_identical_and_crlf_equal` | identical bytes and a CRLF-vs-LF JSON twin → `identical == 2`, `conflicts == []` |
| T4.9 | `test_migrate_reports_conflict_exit_1` | differing JSON → exit 1, target unchanged |
| T4.10 | `test_migrate_same_dir_exits_2` | `--from` = target → 2 |
| T4.11 | `test_run_sweeps_after_success` | offline run (T3.1 fixture) plus an extra stale file → caplog contains `cache gc (tag`, ledger has the stale file |
| T4.12 | `test_partial_run_does_not_sweep` | same with `--limit 1` → no ledger file |
| T4.13 | `test_sweep_error_does_not_fail_run` | monkeypatch `cli.live_entries` to raise → run returns 0, warning logged |
| T4.14 | `test_check_counts_nested_cache` | `extract/s/k.json` + `synth/c/k.json` → `check` prints `extract entries: 1` and `synth entries: 1` |
| T4.15 | `test_cache_command_is_not_paid` | `_build_parser().parse_args(["cache","gc"])` works; document in a comment that the guard regex doesn't match `cache` |

Check: full `pytest -q` + `ruff check .`. Commit: `feat(kb): pnp cache gc/migrate and post-run sweep`.

---

## WP5 — hard-coded `.cache` callers

Files (re-confirmed in WP0 after #40): `services/kb/make_gold_stub.py:33`, `eval_matching.py:32`,
`rules_doctor.py:29`, `claim_sampler.py:228`, `tests/test_identity_churn.py:32`,
`tests/test_extraction_quality.py:50`. (`apply_merges.py`/`apply_important.py` no longer hard-code it.)

Pattern: replace each `HERE / ".cache"` / `ROOT / ".cache"` fallback with `Paths.resolve().cache_dir`,
keeping any `PNP_CACHE_DIR` check that comes first (`Paths.resolve` already honours it, so drop the
duplicate). Keep `/ "extract"` suffixes where they exist. Change nothing else in those files. If a
file already resolves through `Paths` after #40, leave it alone.

Tests: existing `test_rules_doctor.py`, `test_eval_matching.py`, `test_claim_sampler.py`,
`test_identity_churn.py` still pass (or skip with "no bundle checked out", as before).
Commit: `refactor(kb): resolve the cache dir through Paths everywhere`.

---

## WP6 — docs and setup

Files: `docs/architecture/PIPELINE.md` (§6), `docs/RELEASING.md`, `services/kb/README.md`, `AGENTS.md`, `.env.example`.

- **PIPELINE.md §6:** replace "⚠ `.cache/` is gitignored …" with: the cache lives in `knowledge/cache/` (private bundle repo). Add the lifecycle rule (R8, R10). Restore command: `git -C knowledge restore --source=<tag> -- cache/<path>`.
- **RELEASING.md:** an ingest PR carries `cache/**` and `gc_ledger.json`. Deletions start only after the first `s<NN>` tag, so set the baseline tag. A blocked sweep means running `pnp cache gc --dry-run`, reviewing, then `--allow-mass`. To intentionally drop a session, delete its transcript **and** `cache/extract/<session>/` in the same PR (otherwise R6 aborts every sweep).
- **README.md "Setup" — new subsection "Cache":**
  1. **Fresh machine:** clone the bundle into `knowledge/` (`git clone git@github.com:TimTyriell/pnp-knowledge-bundle.git knowledge`). The cache comes with it. `pnp check` should show non-zero extract/synth entries, and `pnp run --estimate` should show `0 to call`.
  2. **Existing machine (cache still in `services/kb/.cache`):** run `pnp cache migrate`, then `pnp run --estimate` (expect 0 to call), then commit `knowledge/cache` on a branch. Delete `services/kb/.cache` only after that.
  3. **Worktree / CI / no bundle:** set `PNP_CACHE_DIR` to an absolute `knowledge/cache` path, or accept a cold `./.cache`. CI has no bundle, and tests use `tmp_path`.
  4. **Your env must match the run's:** `DEEPSEEK_MODEL`, tier models and `PNP_EXTRACT_FREEZE_*` are part of the keys. A mismatched env makes `pnp cache gc` exit 2 instead of deleting.
- **AGENTS.md:** one line under `knowledge/`: "`cache/` = paid LLM cache (C1), swept by `pnp cache gc`; never hand-edit."
- **.env.example:** comment above `#PNP_CACHE_DIR=` with the R1 precedence.

Check: links resolve (`grep -n "cache" docs/RELEASING.md`). Commit: `docs: cache lives in the bundle repo; lifecycle and setup`.

---

## WP7 — HUMAN RUN (real data, after the PR is merged)

```bash
cd c:/dev/lindo-lauts-notebook/pnp-knowledge
git -C knowledge switch -c chore/track-cache
printf 'cache/** -diff -text linguist-generated=true\n' >> knowledge/.gitattributes
cd services/kb
pnp cache migrate --dry-run            # expect ~1254 to copy, 0 conflicts
pnp cache migrate
pnp check                              # extract/synth entries > 0, directory = knowledge/cache
pnp run --estimate                     # expect "0 to call" for extract and synth
pnp cache gc --dry-run                 # read the stale list; no tags yet → nothing deleted, ledger untouched
git -C ../../knowledge add .gitattributes cache
git -C ../../knowledge commit -m "chore(cache): track the LLM cache (C1)"
git -C ../../knowledge push -u origin chore/track-cache   # PR, merge, then the baseline tag (RELEASING.md)
```
`-text` stops git line-ending conversion on cache blobs, so Windows and Linux checkouts hold the
same bytes. Delete `services/kb/.cache` only after the estimate shows 0 to call from the new
location.

## 6. Edge cases (and where each is covered)

| Edge case | Behaviour | Test |
|---|---|---|
| No `s<NN>` tag exists (today: 0 tags) | record only, never delete | T2.6, T2.7 |
| Wrong `DEEPSEEK_MODEL` / freeze env during manual gc | extraction miss → live unknown → exit 2 | T3.6, T4.2 |
| Only some transcripts on disk (new collaborator) | orphan extract dir → abort | T3.3 |
| Zero transcripts / missing dir | abort / exit 2 | T3.4 |
| Prompt bump, then reverted within 2 tags | old entry returns to live and leaves the ledger | T2.5, T3.5 |
| Prompt bump kept | old entries deleted at the 2nd tag; if more than 50%, held for `--allow-mass` | T2.3, T2.11 |
| Synth-tier model change | all synth stale → mass guard holds | T2.11, T2.12 |
| Event entity anchored by T4 | not live, either automatically or manually (filter mirrored) | T3.1 |
| Season frozen by #40 | its extract entries stale → swept (likely held by the mass guard: 55/71) | T3.8 |
| Partial `--limit`/`--session` run | no sweep | T4.12 |
| GC crashes during a run | warning, run still exits 0 | T4.13 |
| Legacy warm cache, new location empty | refuse with a migrate hint | T4.4 |
| CRLF vs LF writers | not a conflict; `-text` in `.gitattributes` | T4.8, WP7 |
| Hand-deleted cache file still in the ledger | dropped from the ledger on the next sweep | T2 (implicit: ledger rebuilt from disk) |
| Corrupt ledger | raise. Auto: warning only. Manual: traceback, exit ≠ 0 | T2.13 |
| `state/`, reports, foreign files | never touched | T2.8 |
| Worktree without `knowledge/` | falls back to `./.cache` unless `PNP_CACHE_DIR` is set | T1.4, README |

## 7. Verification (end to end)

1. `cd $WT/services/kb && $KBPY -m pytest -q`: all green, including T1–T4. Then `ruff check .` from `$WT`: clean.
2. `/review-pr <n>` on the code PR.
3. WP7 on real data: `pnp run --estimate` shows **0 to call** from `knowledge/cache`, and `pnp cache gc --dry-run` lists only plausible stale keys (old synth keys of renamed or merged entities; Prolog extractions if P is frozen).
4. After the 1st and 3rd session tag, the next full `pnp run` logs `cache gc (tag sNN): … deleted K`, and `git -C knowledge show --stat` shows only `cache/` deletions plus the ledger.
