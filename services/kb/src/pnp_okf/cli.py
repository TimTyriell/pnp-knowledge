from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from pnp_okf.config import ConfigError, DeepSeekConfig, Paths
from pnp_okf.context import excerpts_for, load_sources, secondary_sources_for, sources_for
from pnp_okf.dedup import load_never_merge, propose, render_report
from pnp_okf.emit import (
    build_concept_index,
    check_rename_safety,
    emit_conflict,
    emit_entity,
    emit_indexes,
    emit_log,
    emit_sessions,
    mention_concept_index,
    prune_conflicts,
    prune_orphans,
)
from pnp_okf.episodes import Episodes, citation_labels, relabel_citations
from pnp_okf.extract import _cache_key, _cache_path, _load_cached, extract_session
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import CanonicalEntity, SessionExtraction, SessionTranscript
from pnp_okf.resolve import load_spellings, require_rules, resolve_entities, write_registry
from pnp_okf.synthesize import (
    _cache_key as synth_cache_key,
    _cache_path as synth_cache_path,
    autolink_prose,
    link_targets,
    render_brief_body,
    synthesize_entity_body,
)
from pnp_okf.usage import LEDGER, _price
from pnp_okf.validate import fix_bundle, validate_bundle

log = logging.getLogger("pnp_okf")


def _select(
    transcripts: list[SessionTranscript], limit: int | None, sessions: list[str] | None
) -> list[SessionTranscript]:
    if sessions:
        wanted = set(sessions)
        picked = [
            t
            for t in transcripts
            if t.session_id in wanted or t.date in wanted or t.session_id[:10] in wanted
        ]
    else:
        picked = transcripts
    if limit is not None:
        picked = picked[:limit]
    return picked


def _extract_all(
    transcripts: list[SessionTranscript],
    cfg: DeepSeekConfig,
    paths: Paths,
    force: bool,
    workers: int = 8,
) -> dict[str, SessionExtraction]:
    """Extract every session, in parallel like synthesis.

    Each session is an independent HTTP round trip, so this was serial for no
    reason. It stayed invisible because extraction is cached per session and
    normally only the one or two new sessions miss. A run that invalidates the
    whole cache -- a PROMPT_VERSION bump or a model change, both of which are
    in the cache key -- turns that into 66 sequential calls: ~4 hours at ~3.9
    min each, against ~30 min at 8 workers.

    pool.map keeps input order, so the returned dict is ordered exactly as the
    sequential loop left it.
    """

    def _one(t: SessionTranscript) -> tuple[str, SessionExtraction]:
        return t.session_id, extract_session(t, cfg, paths.cache_dir, force=force)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(_one, transcripts))


def _state_dir() -> Path:
    return Path(os.environ.get("PNP_STATE_DIR", "./state")).expanduser()


def _duration_s(started_at: str, ended_at: str) -> float | None:
    """Wall-clock seconds between two ISO-8601 stamps, or None if unparseable.

    Both stamps were already written; only their difference was missing, so
    every consumer had to subtract them by hand.
    """

    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((end - start).total_seconds(), 1)


def _begin_run(started_at: str) -> None:
    """Mark a run as in flight, and record the previous one if it never ended.

    _write_run_status only fires at the end of a run, so a SIGKILL, a power
    loss or a laptop sleeping mid-synthesis wrote nothing at all -- the run
    simply left no row. This marker is the trace: it is written before the
    first bundle write and removed on completion, so finding one at startup
    means the previous run died without finishing.

    Deliberately a separate file rather than a status field on last_run.json:
    that file is a cross-repo contract (docs/architecture/status-schema.md,
    services/dashboard, api.py) whose consumers read ``ok`` as a bool.
    """

    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    marker = state_dir / "run_in_progress.json"
    if marker.exists():
        try:
            stale = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stale = {}
        _append_history(
            {
                "started_at": stale.get("started_at"),
                "ended_at": None,
                "duration_s": None,
                "ok": False,
                "error": "killed before finishing (no run status was written)",
                "counts": {},
            }
        )
        log.error(
            "Previous run (%s) never finished -- it was killed mid-flight. Its "
            "bundle writes may be half-applied; check `pnp validate` before "
            "committing anything from that tree.",
            stale.get("started_at", "unknown"),
        )
    marker.write_text(
        json.dumps({"started_at": started_at}, ensure_ascii=False), encoding="utf-8"
    )


def _append_history(record: dict) -> None:
    ts = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    with open(_state_dir() / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, **record}, ensure_ascii=False) + "\n")


def _write_run_status(started_at: str, ok: bool, error: str | None, counts: dict) -> None:
    """Persist last-run metadata for the dashboard's GET /status endpoint.

    No such record existed before this change — a run left only bundle
    diffs and stdout logs behind, nothing a status endpoint could read.

    ``duration_s`` and ``usage`` are additive: services/dashboard reads this
    file and docs/architecture/status-schema.md documents it as a cross-repo
    contract, so existing keys keep their meaning.
    """

    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    ended_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    run_id = started_at.replace(":", "").replace("-", "")
    record = {
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_s": _duration_s(started_at, ended_at),
        "ok": ok,
        "error": error,
        "counts": counts,
        "usage": LEDGER.snapshot(),
    }
    (state_dir / "last_run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with open(state_dir / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ended_at, **record}, ensure_ascii=False) + "\n")
    (state_dir / "run_in_progress.json").unlink(missing_ok=True)


def _avg_tokens_per_call() -> dict[str, tuple[float, float]]:
    """(prompt, completion) per call, by model, from past successful runs.

    Measured history beats a hard-coded guess: the numbers already sit in
    state/history.jsonl, written by every run since usage accounting landed.
    """

    totals: dict[str, list[float]] = {}
    path = _state_dir() / "history.jsonl"
    if not path.exists():
        return {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        for model, u in ((rec.get("usage") or {}).get("by_model") or {}).items():
            calls = u.get("calls") or 0
            if not calls:
                continue
            acc = totals.setdefault(model, [0.0, 0.0, 0.0])
            acc[0] += u.get("prompt_tokens") or 0
            acc[1] += u.get("completion_tokens") or 0
            acc[2] += calls
    return {m: (p / c, q / c) for m, (p, q, c) in totals.items() if c}


def _estimate_run(args: argparse.Namespace) -> int:
    """Report what a run would cost, then exit without calling the model.

    Every input already exists: which sessions are cached is decidable from
    the cache alone, the tier split falls out of a resolve (a pure function),
    and per-call token averages come from history.jsonl. The ~$6.50 rebuild
    figure was originally learned by paying it; this is so the next one is
    known in advance.
    """

    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    cfg = DeepSeekConfig.from_env().for_tier("extract")
    transcripts = _select(
        load_transcripts(paths.transcript_dir), args.limit, args.session
    )

    cached, missing = [], []
    for t in transcripts:
        key = _cache_key(t, cfg)
        (cached if _load_cached(_cache_path(paths.cache_dir, t, key), key) is not None
         else missing).append(t)

    print(f"extract:  {len(cached)} cached, {len(missing)} to call  [{cfg.model}]")

    synth_calls: Counter[str] = Counter()
    if missing:
        print("synth:    unknown until those sessions are extracted")
    else:
        extractions = {
            t.session_id: _load_cached(
                _cache_path(paths.cache_dir, t, _cache_key(t, cfg)), _cache_key(t, cfg)
            )
            for t in transcripts
        }
        tmap = {t.session_id: t for t in transcripts}
        entities = resolve_entities(extractions, tmap, paths.registry_path)
        base = DeepSeekConfig.from_env()
        # The synth cache has to be consulted or the number is useless: a warm
        # re-emit is ~$0.05 against a ~$6.50 cold rebuild, and an estimate that
        # overshoots by two orders of magnitude just teaches you to ignore it.
        # Every input here is a pure function -- no model call.
        source_sections = load_sources(paths.sources_dir)
        warm = 0
        for entity in entities:
            if entity.tier == "brief":
                continue           # rendered locally, no call ever
            tier_cfg = base.for_tier(entity.tier)
            key = synth_cache_key(
                entity,
                tier_cfg,
                sources_for(entity, source_sections),
                excerpts_for(entity, tmap) if entity.tier == "deep" else "",
                secondary_sources_for(entity, source_sections),
            )
            path = synth_cache_path(paths.cache_dir, entity, key)
            if path.exists():
                warm += 1
            else:
                synth_calls[tier_cfg.model] += 1
        total = sum(synth_calls.values())
        detail = ", ".join(f"{m} {n}" for m, n in sorted(synth_calls.items()))
        print(f"synth:    {warm} cached, {total} to call"
              + (f" ({detail})" if detail else ""))

    per_call = _avg_tokens_per_call()
    calls: Counter[str] = Counter(synth_calls)
    calls[cfg.model] += len(missing)

    prompt = completion = 0.0
    cost, priced = 0.0, True
    for model, n in calls.items():
        avg_p, avg_c = per_call.get(model, (0.0, 0.0))
        if not (avg_p or avg_c):
            priced = False
            continue
        prompt += avg_p * n
        completion += avg_c * n
        p_in, p_out = _price("IN", model), _price("OUT", model)
        if p_in is None or p_out is None:
            priced = False
        else:
            cost += (avg_p * n * p_in + avg_c * n * p_out) / 1_000_000

    tokens = prompt + completion
    if not calls.total():
        print("estimate: no model calls needed -- this run is free")
        return 0
    line = f"estimate: ~{tokens / 1_000_000:.2f}M tokens"
    if priced and cost:
        cur = os.environ.get("PNP_PRICE_CURRENCY", "USD")
        line += f", ~{cost:.2f} {cur} at off-peak rates (double at peak)"
    else:
        line += " (unpriced: set PNP_PRICE_IN_/OUT_<MODEL>, or no history yet)"
    print(line)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline: ingest -> extract -> resolve -> synthesize -> emit."""

    if getattr(args, "estimate", False):
        return _estimate_run(args)

    started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    _begin_run(started_at)
    try:
        return _run_pipeline(args, started_at)
    except Exception as exc:
        _write_run_status(started_at, ok=False, error=str(exc), counts={})
        raise


def _run_pipeline(args: argparse.Namespace, started_at: str) -> int:
    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    cfg = DeepSeekConfig.from_env()

    transcripts = _select(
        load_transcripts(paths.transcript_dir), args.limit, args.session
    )
    tmap = {t.session_id: t for t in transcripts}
    log.info("Processing %d session(s)", len(transcripts))
    partial_run = args.limit is not None or bool(args.session)

    if args.reextract:
        log.warning(
            "--reextract: ignoring the extract cache. The LLM will resample "
            "entity names, which can change their concept id and rename "
            "files that carry no new knowledge (see docs/architecture for "
            "the 2026-08 incident this guards against)."
        )
    extractions = _extract_all(
        transcripts, cfg.for_tier("extract"), paths, args.reextract,
        workers=args.workers,
    )

    registry_path = paths.registry_path
    require_rules(registry_path)
    entities = resolve_entities(extractions, tmap, registry_path)

    if not partial_run and not check_rename_safety(
        registry_path, entities, allow=args.allow_rename
    ):
        _write_run_status(
            started_at,
            ok=False,
            error="refusing to proceed: mass rename detected (see log)",
            counts={},
        )
        return 2

    if args.clean and paths.bundle_dir.exists():
        shutil.rmtree(paths.bundle_dir)

    # Extra grounding for synthesis: world material that never appears in a
    # transcript, plus original dialogue for the entries that warrant depth.
    source_sections = load_sources(paths.sources_dir)

    episodes = Episodes.load(paths.episodes_path)
    log.info("Episode list: %d entr(y/ies) from %s", len(episodes), paths.episodes_path)

    # Snapshot every concept file's mtime before emitting, so the run summary
    # below can report what actually changed on disk (write_if_changed keeps
    # an unchanged file's mtime untouched) instead of just what was attempted.
    before_mtimes = {
        p: p.stat().st_mtime_ns for p in paths.bundle_dir.rglob("*.md")
    } if paths.bundle_dir.exists() else {}

    index = build_concept_index(entities, tmap, load_spellings(registry_path))
    unresolved_total = 0
    conflict_count = 0
    open_conflicts: set[str] = set()
    tier_counts: Counter[str] = Counter(e.tier for e in entities)
    log.info(
        "Synthesis tiers: %s (brief is rendered locally, no LLM call)",
        ", ".join(f"{t}={tier_counts[t]}" for t in ("deep", "standard", "brief")),
    )
    targets = link_targets(entities)
    # Synthesis is one independent network call per entity; run them
    # concurrently or a full rebuild takes hours. Emit stays sequential so
    # file writes and the conflict queue keep a deterministic order.
    def _synth(entity: CanonicalEntity) -> tuple[str, str]:
        if entity.tier == "brief":
            return entity.concept_id, render_brief_body(entity, targets)
        body = synthesize_entity_body(
            entity,
            cfg.for_tier(entity.tier),
            paths.cache_dir,
            force=args.force,
            sources=sources_for(entity, source_sections),
            secondary=secondary_sources_for(entity, source_sections),
            excerpts=(
                excerpts_for(entity, tmap) if entity.tier == "deep" else ""
            ),
        )
        # The cache stores this body pre-autolink (see synthesize_entity_body),
        # so linking here runs on every cache hit too — a rebuild after only
        # entity_rules.yaml or DEEP_MENTION_THRESHOLD changed relinks every
        # standard/deep entry without a single new model call.
        return entity.concept_id, autolink_prose(body, targets, skip=entity.concept_id)

    bodies: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(_synth, e) for e in entities]):
            concept_id, body = future.result()
            bodies[concept_id] = body

    unlabelled = 0
    for entity in entities:
        body = bodies[entity.concept_id]
        # "[3]" -> "[S1-01-A]". The model numbers its evidence list; which
        # episode each number stands for is known here, not there.
        labels = citation_labels([m.url for m in entity.mentions], episodes)
        if labels:
            body = relabel_citations(body, labels)
        elif entity.mentions:
            unlabelled += 1
        unresolved, conflicts = emit_entity(paths.bundle_dir, entity, body, index)
        unresolved_total += len(unresolved)
        if conflicts:
            conflict_path = emit_conflict(paths.conflicts_dir, entity, conflicts)
            conflict_count += 1
            open_conflicts.add(entity.concept_id)
            log.warning(
                "[conflict] %s has contradicting evidence -> %s",
                entity.concept_id,
                conflict_path,
            )
    if unlabelled:
        log.warning(
            "%d entr(y/ies) kept numeric citations — a cited session is missing "
            "from %s. Run pnp-crawl/sync_episodes.py --write.",
            unlabelled,
            paths.episodes_path,
        )

    # Sessions link to entity concept pages ("Auftretende Entitäten"), so they
    # must not be written until the pages they link to actually exist on
    # disk. Emitting them only now -- after every entity file above -- means
    # a kill during the (25-95 min) synthesis window above leaves no new
    # session file at all, instead of one that links to entities that were
    # never written (PIPELINE.md section 7; 54 dangling links on 2026-09-05).
    session_entries = emit_sessions(
        paths.bundle_dir, tmap, extractions, index, episodes,
        mention_concept_ids=mention_concept_index(entities),
    )

    settled = prune_conflicts(paths.conflicts_dir, open_conflicts)
    if settled:
        log.info("Cleared %d resolved conflict(s) from the queue.", settled)

    if partial_run:
        pruned = 0
        log.info(
            "Skipped orphan pruning: this run only covers part of the bundle "
            "(--limit/--session), so concepts outside it are not orphans."
        )
    else:
        pruned = prune_orphans(paths.bundle_dir, entities, allow=args.allow_prune)
        if pruned:
            log.info(
                "Pruned %d concept file(s) with no entity behind them any more.", pruned
            )

    # Written here, next to the bundle's own indexes/log rather than at the
    # top of the run: nothing between the old resolve() call and here reads
    # the freshly-written file back (the only downstream reader is
    # load_spellings, and write_registry never touches the `spelling:`
    # family -- see PIPELINE.md section 7 / Task 2's investigation notes).
    # Writing it first used to mean a kill during synthesis left an
    # entity_registry.yaml naming concept ids whose files were never written.
    write_registry(entities, registry_path)
    emit_indexes(paths.bundle_dir, entities, session_entries, load_spellings(registry_path))
    emit_log(paths.bundle_dir, tmap)

    after_paths = set(paths.bundle_dir.rglob("*.md")) if paths.bundle_dir.exists() else set()
    new_files = len(after_paths - before_mtimes.keys())
    changed_files = sum(
        1 for p in after_paths & before_mtimes.keys()
        if p.stat().st_mtime_ns != before_mtimes[p]
    )
    unchanged_files = len(after_paths) - new_files - changed_files
    log.info(
        "Run summary: %d new, %d changed, %d unchanged concept file(s), %d pruned.",
        new_files, changed_files, unchanged_files, pruned,
    )

    if unresolved_total:
        log.info(
            "Dropped %d unresolved cross-link(s) during emit.", unresolved_total
        )
    if conflict_count:
        log.warning(
            "%d open conflict(s) queued in %s — resolve before merging the "
            "ingest branch.",
            conflict_count,
            paths.conflicts_dir,
        )

    log.info("Bundle written to %s", paths.bundle_dir)
    log.info("Registry: %s", registry_path)

    report = validate_bundle(paths.bundle_dir)
    log.info("Validation:\n%s", report.summary())
    if not report.integrity_ok:
        log.error(
            "Validation found %d broken and %d dangling link(s), %d concept(s) "
            "without a type and %d duplicate id(s). Refusing to report success "
            "-- this bundle must not be committed.",
            len(report.broken_links),
            len(report.dangling_links),
            len(report.missing_type),
            len(report.duplicate_ids),
        )
        _write_run_status(
            started_at,
            ok=False,
            error="bundle failed post-emit validation (see log)",
            counts={},
        )
        return 3

    log.info(
        "Visualize with the okf package:\n"
        "  python -m reference_agent visualize --bundle %s",
        paths.bundle_dir,
    )

    entities_by_type = dict(Counter(e.type for e in entities))
    _write_run_status(
        started_at,
        ok=True,
        error=None,
        counts={
            "entities_by_type": entities_by_type,
            "conflicts_open": conflict_count,
            "sessions_ingested": len(transcripts),
            "dropped_links": unresolved_total,
        },
    )
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Run only the extraction stage (populates the cache)."""

    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    cfg = DeepSeekConfig.from_env()
    transcripts = _select(
        load_transcripts(paths.transcript_dir), args.limit, args.session
    )
    extractions = _extract_all(transcripts, cfg, paths, args.force, workers=args.workers)
    for sid, ex in extractions.items():
        log.info("%s: %d entities", sid, len(ex.entities))
    return 0


def cmd_dedup(args: argparse.Namespace) -> int:
    """Propose entity merges for human review. Writes a report, not the registry.

    Runs on cached extractions, so it costs one small call per identity space
    and never re-reads transcripts.
    """

    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    cfg = DeepSeekConfig.from_env()
    transcripts = _select(
        load_transcripts(paths.transcript_dir), args.limit, args.session
    )
    tmap = {t.session_id: t for t in transcripts}
    extractions = _extract_all(transcripts, cfg, paths, force=False, workers=args.workers)

    registry_path = paths.registry_path
    require_rules(registry_path)
    entities = resolve_entities(extractions, tmap, registry_path)

    # Screening runs on the fast model: it only narrows ~840 entities down to
    # candidate groups, and a human confirms every one before it is written.
    groups = propose(
        entities,
        cfg.for_tier("standard"),
        never_merge=load_never_merge(registry_path),
    )
    report = render_report(groups, entities)
    out = Path(args.out) if args.out else paths.conflicts_dir / "merge_proposals.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    by_conf = Counter(g.confidence for g in groups)
    log.info(
        "%d merge group(s) proposed over %d entities (%s). Report: %s",
        len(groups),
        len(entities),
        ", ".join(f"{k}={v}" for k, v in by_conf.most_common()),
        out,
    )
    log.info("Nothing was written to the registry — confirm the groups first.")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Verify configuration and count transcripts without calling DeepSeek."""

    ok = True

    # Config.
    print("--- DeepSeek config ---")
    try:
        cfg = DeepSeekConfig.from_env()
        print(f"  base_url: {cfg.base_url}")
        print(f"  model:    {cfg.model}")
        print("  auth:     API key")
    except ConfigError as exc:
        print(f"  ERROR: {exc}")
        print("  -> Copy .env.example to .env and fill in your DeepSeek settings.")
        ok = False

    # Transcripts.
    print("\n--- Transcripts ---")
    paths = Paths.resolve(args.transcripts, None, args.cache)
    try:
        transcripts = load_transcripts(paths.transcript_dir)
        print(f"  directory: {paths.transcript_dir}")
        print(f"  sessions:  {len(transcripts)}")
        words = sum(t.word_count for t in transcripts)
        print(f"  total words: {words:,}")
        if transcripts:
            print(f"  date range: {transcripts[0].date} – {transcripts[-1].date}")
    except FileNotFoundError as exc:
        print(f"  ERROR: {exc}")
        ok = False

    # Cache.
    print("\n--- Cache ---")
    cache_dir = paths.cache_dir
    if cache_dir.exists():
        extract_cached = list((cache_dir / "extract").glob("*.json")) if (cache_dir / "extract").exists() else []
        synth_cached = list((cache_dir / "synth").glob("*.json")) if (cache_dir / "synth").exists() else []
        print(f"  directory:       {cache_dir}")
        print(f"  extract entries: {len(extract_cached)}")
        print(f"  synth entries:   {len(synth_cached)}")
    else:
        print(f"  (empty — will be created at {cache_dir})")

    # okf visualize.
    print("\n--- okf reference-agent (for viz.html) ---")
    if shutil.which("reference-agent"):
        print("  reference-agent: found on PATH")
    else:
        try:
            import reference_agent  # noqa: F401
            print("  reference_agent: importable as Python module (-m reference_agent)")
        except ImportError:
            print("  reference-agent: NOT found (optional — needed for pnp visualize)")

    print("\n" + ("OK — ready to run." if ok else "FAILED — fix the errors above."))
    return 0 if ok else 2


def cmd_visualize(args: argparse.Namespace) -> int:
    """Generate viz.html by delegating to the okf reference package CLI."""

    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    if shutil.which("reference-agent") is None and not args.python_module:
        log.error(
            "The okf 'reference-agent' CLI was not found. Install the okf "
            "package or pass --python-module to invoke it via python -m."
        )
        return 1
    cmd = (
        [sys.executable, "-m", "reference_agent"]
        if args.python_module
        else ["reference-agent"]
    )
    cmd += ["visualize", "--bundle", str(paths.bundle_dir)]
    log.info("Running: %s", " ".join(cmd))
    return subprocess.call(cmd)


def cmd_validate(args: argparse.Namespace) -> int:
    """Audit an emitted bundle for broken links and duplicate concepts."""

    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    if not paths.bundle_dir.exists():
        log.error("Bundle directory not found: %s", paths.bundle_dir)
        return 2
    if args.fix:
        changed, dropped = fix_bundle(paths.bundle_dir, paths.registry_path)
        print(
            f"Normalized links in {changed} file(s); "
            f"dropped {dropped} unresolvable link(s) to plain text.\n"
        )
    report = validate_bundle(paths.bundle_dir)
    print(report.summary())
    if report.ok:
        return 0
    return 0 if args.non_strict else 1


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--transcripts", help="Directory of *.json transcripts")
    p.add_argument("--bundle", help="Output bundle directory")
    p.add_argument("--cache", help="Cache directory")
    p.add_argument(
        "--session",
        action="append",
        help="Restrict to session id/date (repeatable)",
    )
    p.add_argument(
        "--limit", type=int, default=None, help="Process at most N sessions"
    )
    p.add_argument(
        "--force", action="store_true",
        help="Ignore the synthesis cache and re-call the LLM for entity "
        "prose (extraction is untouched — see --reextract). For "
        "'extract', this ignores the extraction cache instead, since "
        "that is the only thing that command does.",
    )
    p.add_argument(
        "--reextract", action="store_true",
        help="Ignore the extraction cache and re-call the LLM for entity "
        "mentions. Resamples the model, which can reword an entity's name "
        "and change its concept id — prefer editing entity_rules.yaml over "
        "this unless the transcript itself changed.",
    )
    p.add_argument(
        "--workers", type=int, default=8,
        help="Parallel synthesis calls (default 8)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pnp",
        description="Distill Pen & Paper transcripts into an OKF campaign bundle.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Full pipeline end to end")
    _add_common(run)
    run.add_argument(
        "--clean", action="store_true", help="Delete the bundle dir before writing"
    )
    run.add_argument(
        "--allow-prune", action="store_true",
        help="Allow pruning more than 10%% of existing concept files in one "
        "run. Orphan pruning is skipped entirely on a --limit/--session run.",
    )
    run.add_argument(
        "--estimate",
        action="store_true",
        help="Report what this run would cost and exit without calling the model",
    )
    run.add_argument(
        "--allow-rename", action="store_true",
        help="Allow more than 10%% of the previous registry's concept ids to "
        "go missing from a resolved run (e.g. after a deliberate registry "
        "cleanup). The check is skipped entirely on a --limit/--session run.",
    )
    run.set_defaults(func=cmd_run)

    extract = sub.add_parser("extract", help="Extraction stage only (fills cache)")
    _add_common(extract)
    extract.set_defaults(func=cmd_extract)

    dedup = sub.add_parser(
        "dedup", help="Propose entity merges for review (writes a report only)"
    )
    _add_common(dedup)
    dedup.add_argument("--out", help="Report path (default: conflicts/merge_proposals.md)")
    dedup.set_defaults(func=cmd_dedup)

    check = sub.add_parser("check", help="Verify config + count transcripts (no LLM calls)")
    check.add_argument("--transcripts", help="Directory of *.json transcripts")
    check.add_argument("--cache", help="Cache directory")
    check.set_defaults(func=cmd_check)

    viz = sub.add_parser("visualize", help="Generate viz.html via the okf CLI")
    viz.add_argument("--bundle", help="Output bundle directory")
    viz.add_argument("--transcripts", help=argparse.SUPPRESS)
    viz.add_argument("--cache", help=argparse.SUPPRESS)
    viz.add_argument(
        "--python-module",
        action="store_true",
        help="Invoke okf via 'python -m reference_agent'",
    )
    viz.set_defaults(func=cmd_visualize)

    validate = sub.add_parser(
        "validate", help="Audit an emitted bundle (broken links, duplicates)"
    )
    validate.add_argument("--bundle", help="Bundle directory to validate")
    validate.add_argument("--transcripts", help=argparse.SUPPRESS)
    validate.add_argument("--cache", help=argparse.SUPPRESS)
    validate.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite cross-links in place before validating (no LLM calls)",
    )
    validate.add_argument(
        "--non-strict",
        action="store_true",
        help="Always exit 0, even when issues are found",
    )
    validate.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.func(args)
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        log.error("Copy .env.example to .env and fill in your DeepSeek settings.")
        return 2
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
