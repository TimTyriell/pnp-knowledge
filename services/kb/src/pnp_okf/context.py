"""Extra grounding handed to synthesis on top of the per-mention notes.

The notes are a lossy compression of a session, and some campaign knowledge
never appears in a transcript at all. Two supplements close those gaps:

* **Source material** (``knowledge/sources/``) — rulebooks, the pantheon
  scripture, campaign handouts. The bundle is *generated*, so hand-written
  prose added directly to a concept file is overwritten on the next run;
  keeping that material in ``sources/`` and re-injecting it here survives
  every regeneration. The same mechanism carries imported wiki prose later.
* **Transcript windows** — for deep-tier entities we go back to the original
  dialogue around each citation, so the entry can carry concrete detail and
  the occasional verbatim quote instead of only re-phrased notes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pnp_okf.models import CanonicalEntity, SessionTranscript
from pnp_okf.okf import slugify

log = logging.getLogger(__name__)

# Seconds of dialogue to pull either side of a citation timestamp.
EXCERPT_WINDOW_S = 90.0

# Upper bound on the transcript dialogue handed to one synthesis call.
EXCERPT_BUDGET_CHARS = 60_000

_HEADING_RE = re.compile(r"^(#{2,4})[ \t]+(.+?)[ \t]*$", re.MULTILINE)


class SourceSection:
    """One ``##``-delimited section of a file in ``knowledge/sources/``."""

    __slots__ = ("origin", "heading", "slug", "text")

    def __init__(self, origin: str, heading: str, text: str) -> None:
        self.origin = origin
        self.heading = heading
        self.slug = slugify(heading)
        self.text = text


def load_sources(sources_dir: Path) -> list[SourceSection]:
    """Parse every markdown file in ``sources_dir`` into headed sections."""

    if not sources_dir.is_dir():
        return []
    sections: list[SourceSection] = []
    for path in sorted(sources_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        matches = list(_HEADING_RE.finditer(content))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[m.end():end].strip()
            if body:
                sections.append(SourceSection(path.name, m.group(2), body))
    log.info("[context] loaded %d source sections from %s", len(sections), sources_dir)
    return sections


def sources_for(entity: CanonicalEntity, sections: list[SourceSection]) -> str:
    """Source sections whose heading names this entity, as markdown.

    Matching is on slugs so punctuation drift between a transcript spelling
    and the written lore ("Vhar'Zul" vs "Vhar Zul") still lines up.
    """

    if not sections:
        return ""
    names = {slugify(n) for n in [entity.canonical_name, *entity.aliases] if n}
    names = {n for n in names if len(n) >= 4}  # avoid matching on stubs
    if not names:
        return ""

    hits = [
        s
        for s in sections
        if any(n in s.slug or s.slug in n for n in names)
    ]
    if not hits:
        return ""
    return "\n\n".join(
        f"### {s.heading}  (aus {s.origin})\n{s.text}" for s in hits
    )


def _parse_ts(ts: str) -> float | None:
    parts = (ts or "").strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        h, m, s = nums
    elif len(nums) == 2:
        h, m, s = 0, nums[0], nums[1]
    else:
        return None
    return h * 3600 + m * 60 + s


def _merge_windows(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Collapse overlapping ``(start, end)`` spans so dialogue isn't repeated."""

    merged: list[tuple[float, float]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def excerpts_for(
    entity: CanonicalEntity,
    transcripts: dict[str, SessionTranscript],
    *,
    window_s: float = EXCERPT_WINDOW_S,
    budget_chars: int = EXCERPT_BUDGET_CHARS,
) -> str:
    """Original dialogue around each of this entity's citations.

    The per-session budget is divided evenly rather than filled first-come:
    a character appearing in 38 sessions needs coverage *across* the campaign
    for its chronology section, so every session keeps a slice instead of the
    earliest ones consuming the whole budget.
    """

    by_session: dict[str, list[tuple[float, float]]] = {}
    for m in entity.mentions:
        t = _parse_ts(m.citation_ts)
        if t is None or m.session_id not in transcripts:
            continue
        by_session.setdefault(m.session_id, []).append(
            (max(0.0, t - window_s), t + window_s)
        )
    if not by_session:
        return ""

    per_session = max(600, budget_chars // len(by_session))
    blocks: list[str] = []
    for session_id in sorted(by_session):
        transcript = transcripts[session_id]
        spans = _merge_windows(by_session[session_id])
        lines = [
            f"[{seg.timestamp}] {seg.speaker}: {seg.text.strip()}"
            for seg in transcript.segments
            if seg.text.strip()
            and any(start <= seg.start <= end for start, end in spans)
        ]
        if not lines:
            continue
        body = "\n".join(lines)
        if len(body) > per_session:
            body = body[:per_session].rsplit("\n", 1)[0] + "\n[… gekürzt …]"
        blocks.append(f"--- Session {transcript.date} ---\n{body}")

    return "\n\n".join(blocks)
