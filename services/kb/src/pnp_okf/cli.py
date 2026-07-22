from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from pnp_okf.config import DeepSeekConfig, ConfigError, Paths
from pnp_okf.emit import (
    build_concept_index,
    emit_conflict,
    emit_entity,
    emit_indexes,
    emit_log,
    emit_sessions,
)
from pnp_okf.extract import extract_session
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import SessionExtraction, SessionTranscript
from pnp_okf.resolve import resolve_entities, write_registry
from pnp_okf.synthesize import synthesize_entity_body
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
) -> dict[str, SessionExtraction]:
    out: dict[str, SessionExtraction] = {}
    for t in transcripts:
        out[t.session_id] = extract_session(
            t, cfg, paths.cache_dir, force=force
        )
    return out


def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline: ingest -> extract -> resolve -> synthesize -> emit."""

    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    cfg = DeepSeekConfig.from_env()

    transcripts = _select(
        load_transcripts(paths.transcript_dir), args.limit, args.session
    )
    tmap = {t.session_id: t for t in transcripts}
    log.info("Processing %d session(s)", len(transcripts))

    extractions = _extract_all(transcripts, cfg, paths, args.force)

    registry_path = paths.bundle_dir.parent / "entity_registry.yaml"
    entities = resolve_entities(extractions, tmap, registry_path)
    write_registry(entities, registry_path)

    if args.clean and paths.bundle_dir.exists():
        shutil.rmtree(paths.bundle_dir)

    index = build_concept_index(entities, tmap)
    session_entries = emit_sessions(paths.bundle_dir, tmap, extractions, index)
    unresolved_total = 0
    conflict_count = 0
    for entity in entities:
        body = synthesize_entity_body(
            entity, cfg, paths.cache_dir, force=args.force
        )
        unresolved, conflicts = emit_entity(paths.bundle_dir, entity, body, index)
        unresolved_total += len(unresolved)
        if conflicts:
            conflict_path = emit_conflict(paths.conflicts_dir, entity, conflicts)
            conflict_count += 1
            log.warning(
                "[conflict] %s has contradicting evidence -> %s",
                entity.concept_id,
                conflict_path,
            )
    emit_indexes(paths.bundle_dir, entities, session_entries)
    emit_log(paths.bundle_dir, tmap)

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

    log.info(
        "Visualize with the okf package:\n"
        "  python -m reference_agent visualize --bundle %s",
        paths.bundle_dir,
    )
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Run only the extraction stage (populates the cache)."""

    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    cfg = DeepSeekConfig.from_env()
    transcripts = _select(
        load_transcripts(paths.transcript_dir), args.limit, args.session
    )
    extractions = _extract_all(transcripts, cfg, paths, args.force)
    for sid, ex in extractions.items():
        log.info("%s: %d entities", sid, len(ex.entities))
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
        print(f"  auth:     API key")
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
        changed, dropped = fix_bundle(paths.bundle_dir)
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
        "--force", action="store_true", help="Ignore cache and re-call the LLM"
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
    run.set_defaults(func=cmd_run)

    extract = sub.add_parser("extract", help="Extraction stage only (fills cache)")
    _add_common(extract)
    extract.set_defaults(func=cmd_extract)

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
