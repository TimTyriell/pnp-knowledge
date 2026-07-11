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
_SPEAKER_RE = re.compile(r"^\s*(?P<player>[^()]+?)\s*\(\s*(?P<character>[^()]+?)\s*\)\s*$")


def session_id_from_path(path: Path) -> str:
    """Date string from the filename, or the stem if no date is present."""
    m = _DATE_RE.search(path.name)
    return m.group(1) if m else path.stem


def parse_speaker(label: str) -> tuple[str, str | None, bool]:
    """Split a transcript speaker label 'Player (Character)' -> (player, character, is_gm).

    'Deniz (GM)' is a role, not a PC: -> ('Deniz', None, True).
    A label without parentheses is returned as (label, None, False).
    """
    m = _SPEAKER_RE.match(label)
    if not m:
        return label.strip(), None, False
    player, character = m.group("player"), m.group("character")
    if character.upper() == "GM":
        return player, None, True
    return player, character, False


def session_cast(segments: list[dict]) -> list[tuple[str, str | None, bool]]:
    """Distinct (player, character, is_gm) triples for one session, in first-seen order."""
    seen: dict[str, tuple[str, str | None, bool]] = {}
    for seg in segments:
        label = seg["speaker"]
        if label not in seen:
            seen[label] = parse_speaker(label)
    return list(seen.values())


def format_turn(seg: dict) -> str:
    # Emit the acting character (or 'GM') as the speaker, never the composite
    # 'Player (Character)' label — the composite string is what made the model
    # coin Tim / Lindo Laut / 'Tim (Lindo Laut)' as three separate entities.
    player, character, is_gm = parse_speaker(seg["speaker"])
    who = "GM" if is_gm else (character or player)
    mins, secs = divmod(int(seg["start"]), 60)
    return f"[{mins:02d}:{secs:02d}] {who}:\n  {seg['text'].strip()}\n\n"


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
            # Only consider a gap a break candidate once the chunk has reached
            # half of CHUNK_SIZE — anchored to absolute size, not window
            # position: a window-relative halfway (previous version) lets the
            # same small early gap re-qualify as "past halfway" once overlap
            # has shrunk the window, cutting there again and again in a
            # cascade of ever-smaller chunks instead of accumulating toward budget.
            if end + 1 < n and size > CHUNK_SIZE // 2:
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


def load_session(path: Path) -> tuple[list[str], list[tuple[str, str | None, bool]]]:
    """(chunks, cast) for a single transcript file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = [s for s in data["segments"] if s["text"].strip()]
    return pack_segments(segments), session_cast(segments)


def ordered_sessions(transcript_dir: Path) -> list[Path]:
    """Transcript files sorted oldest -> newest by session_id (date)."""
    return sorted(transcript_dir.glob("*.json"), key=session_id_from_path)
