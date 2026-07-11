"""Orchestrator: process sessions oldest -> newest, one atomic transaction each."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .chunking import load_session, ordered_sessions, session_id_from_path
from .config import STATE_DIR, TRANSCRIPT_DIR
from .embed import embed_entities
from .extract import build_extractor, extract_session
from .resolve import Resolver, resolve_graph
from .srd import SrdIndex, preload
from .store import connect, run_qa, write_session

log = logging.getLogger("pnp_graph.ingest")

_LOG_FILE = STATE_DIR / "ingest_log.jsonl"


def _log_result(record: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def ingest(transcript_dir: Path = TRANSCRIPT_DIR, only: str | None = None) -> None:
    sessions = ordered_sessions(transcript_dir)
    if only:
        sessions = [p for p in sessions if session_id_from_path(p) == only]
    if not sessions:
        log.error("No transcripts matched in %s", transcript_dir)
        return

    extractor = build_extractor()
    resolver = Resolver()
    srd_index = SrdIndex()
    driver = connect()
    preload(driver, srd_index)  # shared RuleEntity library, session-independent
    try:
        for seq, path in enumerate(sessions, start=1):
            sid = session_id_from_path(path)
            log.info("=== Session %s (seq %d) ===", sid, seq)
            try:
                chunks, cast = load_session(path)
                cast_info = resolver.bootstrap_cast(cast)
                cast_names = [p["name"] for p in cast_info["characters"].values()]
                graph, evidence = extract_session(extractor, chunks, cast_names,
                                                  srd_index.gazetteer(),
                                                  fail_dir=STATE_DIR / "failures" / sid)
                log.info(
                    "Session %s merged total: %d characters, %d locations, %d items, "
                    "%d quests, %d events, %d factions, %d traits, %d relationships",
                    sid,
                    len(graph.characters), len(graph.locations), len(graph.items),
                    len(graph.quests), len(graph.events), len(graph.factions),
                    len(graph.traits), len(graph.relationships),
                )
                resolved = resolve_graph(resolver, graph, sid, cast_info, seq,
                                         evidence=evidence, srd_index=srd_index)
                write_session(driver, resolved)
                embed_entities(driver, [e["id"] for e in resolved["entities"]])
                qa = run_qa(driver)
                _log_result({
                    "session_id": sid, "seq": seq, "status": "ok",
                    "file": path.name, "chunks": len(chunks),
                    "entities": len(resolved["entities"]), "edges": len(resolved["edges"]),
                    "dropped_edges": len(resolved["dropped"]), "qa": qa,
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
                log.info("Session %s written: %d entities, %d edges (%d dropped).",
                         sid, len(resolved["entities"]), len(resolved["edges"]),
                         len(resolved["dropped"]))
            except Exception as exc:  # one bad session must not block the rest
                log.exception("Session %s FAILED", sid)
                _log_result({
                    "session_id": sid, "seq": seq, "status": "failed",
                    "file": path.name, "error": repr(exc),
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
    finally:
        driver.close()
    log.info("Ingest complete. View: MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100")
