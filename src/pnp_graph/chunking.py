"""Transcript loading and gap-aware chunking.

A "session" is one transcript JSON file. `session_id` is the date parsed from the
filename (e.g. 2025-03-26), which sorts chronologically and matches pnp-report's
Session_Report_S<NN>_<date> convention.
"""

import json
import re
from pathlib import Path

from .config import CHUNK_OVERLAP, CHUNK_SIZE

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def session_id_from_path(path: Path) -> str:
    """Date string from the filename, or the stem if no date is present."""
    m = _DATE_RE.search(path.name)
    return m.group(1) if m else path.stem


def format_turn(seg: dict) -> str:
    mins, secs = divmod(int(seg["start"]), 60)
    return f"[{mins:02d}:{secs:02d}] {seg['speaker']}:\n  {seg['text'].strip()}\n\n"


def pack_segments(segments: list[dict]) -> list[str]:
    """Pack whole transcript segments into ~CHUNK_SIZE chunks, never splitting a segment.

    Prefers breaking at the largest silence gap within the size budget (a real
    conversational pause/topic break) over the segment that merely hits the size
    limit first, since gaps are a better signal for chunk boundaries than char count.
    """
    turns = [format_turn(s) for s in segments]
    chunks: list[str] = []
    start = 0
    n = len(turns)
    while start < n:
        end = start
        size = 0
        best_break = None  # (gap, index) candidate end-of-chunk within budget
        while end < n and size + len(turns[end]) <= CHUNK_SIZE:
            size += len(turns[end])
            # Only consider a gap a break candidate once we're past the halfway
            # point of the window — otherwise the global-largest gap can sit near
            # the window start, making `cut` barely advance and the loop stall.
            if end + 1 < n and (end + 1 - start) > (end - start + 1) // 2:
                gap = segments[end + 1]["start"] - segments[end]["end"]
                if best_break is None or gap > best_break[0]:
                    best_break = (gap, end + 1)
            end += 1
        if end >= n:
            chunks.append("".join(turns[start:end]))
            break
        # break at the largest late-window gap, else at the size limit
        cut = best_break[1] if best_break and best_break[1] > start else end
        chunks.append("".join(turns[start:cut]))
        # turn-based overlap: walk back from cut while within CHUNK_OVERLAP budget,
        # but never past `start + 1` — `start` must strictly advance or we loop forever.
        overlap_start = cut
        overlap_len = 0
        while (overlap_start > start + 1
               and overlap_len + len(turns[overlap_start - 1]) <= CHUNK_OVERLAP):
            overlap_start -= 1
            overlap_len += len(turns[overlap_start])
        start = overlap_start if overlap_start < cut else cut
    return chunks


def load_session_chunks(path: Path) -> list[str]:
    """Chunks for a single transcript file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = [s for s in data["segments"] if s["text"].strip()]
    return pack_segments(segments)


def ordered_sessions(transcript_dir: Path) -> list[Path]:
    """Transcript files sorted oldest -> newest by session_id (date)."""
    return sorted(transcript_dir.glob("*.json"), key=session_id_from_path)
