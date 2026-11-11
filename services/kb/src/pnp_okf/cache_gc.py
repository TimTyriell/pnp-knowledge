"""Garbage collection for the paid LLM extract/synth cache (plan C1: cache in the bundle repo).

Lifecycle rule: an entry is *stale* when the current config no longer reaches its key (prompt or
model change, edited transcript, entity renamed/merged/anchored away, session now served from
knowledge/frozen/). A stale entry is deleted once it has stayed stale through KEEP_TAGS session
tags. Git history keeps every deleted file, so a reverted change is re-fetched from git, not paid
for again.

R4: only paths matching _ENTRY (extract|synth/<session>/<16 hex>.json) are ever touched. state/,
gc_ledger.json and anything else are never deleted.

R6: the caller passes the live set. None means "unknown" and must never reach sweep(); the caller
aborts instead. An empty live set would mark every entry stale, so it is the caller's job too.

R8: no session tag means nothing is ever deleted. Null ledger stamps take the first tag seen.

R10: per-kind mass guard. If more than MAX_DUE_RATIO of one kind is due, that kind is blocked
and reported, unless allow_mass is passed (CLI only; the automatic sweep never passes it).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

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
    if live is None:
        raise ValueError("live set unknown; refusing to sweep")
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
                # JSON equality too: CRLF/LF differences between Windows and Linux
                # writers are not conflicts.
                same = target.read_bytes() == p.read_bytes() or (
                    p.suffix == ".json"
                    and json.loads(target.read_text(encoding="utf-8"))
                    == json.loads(p.read_text(encoding="utf-8"))
                )
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
