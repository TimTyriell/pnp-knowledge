"""Orchestrator: process sessions oldest -> newest, one atomic transaction each."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .chunking import load_session_chunks, ordered_sessions, session_id_from_path
from .config import STATE_DIR, TRANSCRIPT_DIR
from .extract import build_extractor, extract_session
from .store import connect, write_session

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
    driver = connect()
    try:
        for seq, path in enumerate(sessions, start=1):
            sid = session_id_from_path(path)
            log.info("=== Session %s (seq %d) ===", sid, seq)
            try:
                chunks = load_session_chunks(path)
                graph = extract_session(extractor, chunks)
                log.info(
                    "Session %s merged total: %d characters, %d locations, %d items, "
                    "%d quests, %d events, %d factions, %d relationships",
                    sid,
                    len(graph.characters), len(graph.locations), len(graph.items),
                    len(graph.quests), len(graph.events), len(graph.factions),
                    len(graph.relationships),
                )
                write_session(driver, graph, sid, seq)
                _log_result({
                    "session_id": sid, "seq": seq, "status": "ok",
                    "file": path.name, "chunks": len(chunks),
                    "characters": len(graph.characters), "locations": len(graph.locations),
                    "items": len(graph.items), "quests": len(graph.quests),
                    "events": len(graph.events), "factions": len(graph.factions),
                    "relationships": len(graph.relationships),
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
                log.info("Session %s written.", sid)
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
