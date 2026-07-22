from __future__ import annotations

import json
import logging
from pathlib import Path

from pnp_okf.models import Segment, SessionTranscript

log = logging.getLogger(__name__)


def _session_id_from_name(name: str) -> str:
    """Derive a stable session id from a transcript filename stem."""

    return name.replace(".json", "")


def load_transcript(path: Path) -> SessionTranscript:
    """Load a single diarized transcript JSON into a SessionTranscript."""

    data = json.loads(path.read_text(encoding="utf-8"))
    segments = [
        Segment(
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            speaker=str(seg.get("speaker", "")),
            text=str(seg.get("text", "")),
        )
        for seg in data.get("segments", [])
    ]
    return SessionTranscript(
        session_id=_session_id_from_name(path.stem),
        date=str(data.get("video_date", "")),
        url=str(data.get("video_url", "")),
        title=str(data.get("video_title", "")),
        language=str(data.get("language", "de")),
        segments=segments,
    )


def load_transcripts(transcript_dir: Path) -> list[SessionTranscript]:
    """Load every ``*.json`` transcript in a directory, sorted by filename.

    Filenames start with the session date (``YYYY-MM-DD_...``), so a plain
    lexical sort yields chronological order.
    """

    if not transcript_dir.is_dir():
        raise FileNotFoundError(f"Transcript directory not found: {transcript_dir}")
    paths = sorted(transcript_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No *.json transcripts in {transcript_dir}")
    transcripts = [load_transcript(p) for p in paths]
    log.info("Loaded %d transcripts from %s", len(transcripts), transcript_dir)
    return transcripts
