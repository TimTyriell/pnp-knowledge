"""The campaign's episode list, and citation labels derived from it.

``knowledge/episodes.yaml`` is hand-maintained (see the header in that file and
``pnp-crawl/sync_episodes.py``); this module only reads it. It gives the
pipeline two things:

* the episode identity a Session concept is emitted with (``P-17``, ``S1-01-B``),
  which is also what the wiki uses as a page title; and
* the citation labels: a body cites ``[S1-01-B]`` instead of ``[3]``.

Why relabel rather than ask the model for episode markers directly: the markers
the model writes come from the numbered evidence list in the synthesis prompt,
and every cached body was written against that list. Changing the prompt means
re-synthesising ~1000 entries at real cost, for a rename that is a pure
function of the mention order. So the numbering stays the model's business and
the label substitution happens on the finished body — cached entries included.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# "https://www.youtube.com/watch?v=<id>" — the only form episodes.yaml uses.
_VIDEO_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{6,})")
# Inline references "[3]" / "[3, 5]". The lookahead keeps markdown links with a
# numeric label ("[3](/x.md)") out — rewriting one would break the link.
_REF_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\](?!\()")
# Both citation-list styles the KB emits: "[1] Session …" and "1. Session …".
_CITE_LINE_RE = re.compile(r"^(?:\[(\d+)\]|(\d+)\.)(\s+)(.*)$")


def video_id(url: str) -> str | None:
    m = _VIDEO_ID_RE.search(url or "")
    return m.group(1) if m else None


class Episodes:
    """Episode metadata, keyed by video id."""

    def __init__(
        self,
        entries: list[dict[str, Any]] | None = None,
        seasons: dict[str, Any] | None = None,
    ) -> None:
        self._by_video = {e["video_id"]: e for e in (entries or []) if e.get("video_id")}
        self._seasons = {str(k): v for k, v in (seasons or {}).items()}

    def __len__(self) -> int:
        return len(self._by_video)

    def for_url(self, url: str) -> dict[str, Any] | None:
        vid = video_id(url)
        return self._by_video.get(vid) if vid else None

    def season_label(self, season: str | None) -> str | None:
        """Display name of a season ("Prolog", "Staffel 1").

        Emitted onto the Session concept so consumers — the wiki agent above
        all — get the grouping without reading episodes.yaml themselves.
        """
        spec = self._seasons.get(str(season)) if season is not None else None
        return (spec or {}).get("label")

    def id_for_url(self, url: str) -> str | None:
        entry = self.for_url(url)
        return entry.get("id") if entry else None

    @classmethod
    def load(cls, path: Path) -> "Episodes":
        """Read *path*; an absent or broken file yields an empty list.

        Missing episode data must not stop a run: the pipeline then emits what
        it always emitted (YouTube titles, numeric citations), just without the
        episode identity. A hard failure here would block ingest on a file that
        only ever adds labels.
        """
        if not path.is_file():
            log.warning("No episode list at %s — sessions keep their YouTube titles.", path)
            return cls()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            log.warning("Could not read %s (%s) — continuing without episode ids.", path, exc)
            return cls()
        return cls(data.get("episodes"), data.get("seasons"))


def citation_labels(urls: list[str], episodes: Episodes) -> list[str] | None:
    """Label per mention, index-aligned with *urls*. None if any is unknown.

    An entity cites a session more than once in 16 of ~930 entries, so repeats
    get a letter suffix (``P-08a``, ``P-08b``) — two evidence lines that both
    said ``[P-08]`` would be indistinguishable in the Belege list.

    All-or-nothing on purpose: a body where some markers are episode ids and
    others are leftover numbers reads as if the numbers meant something else.
    """
    ids = [episodes.id_for_url(u) for u in urls]
    if not ids or any(not i for i in ids):
        return None

    counts: dict[str, int] = {}
    for i in ids:
        counts[i] = counts.get(i, 0) + 1
    seen: dict[str, int] = {}
    labels: list[str] = []
    for i in ids:
        if counts[i] == 1:
            labels.append(i)
            continue
        seen[i] = seen.get(i, 0) + 1
        labels.append(f"{i}{chr(ord('a') + seen[i] - 1)}")
    return labels


def relabel_citations(body: str, labels: list[str]) -> str:
    """Replace numeric citation markers in *body* with *labels* (1-based).

    Touches the inline ``[n]`` references and the ``# Belege`` list lines. A
    number with no label — the model occasionally invents one past the end of
    the evidence list — is left as it is rather than silently dropped.
    """
    if not labels:
        return body

    def label(n: str) -> str | None:
        idx = int(n) - 1
        return labels[idx] if 0 <= idx < len(labels) else None

    def ref(match: re.Match) -> str:
        parts = [label(n.strip()) for n in match.group(1).split(",")]
        if any(p is None for p in parts):
            return match.group(0)
        return "[" + ", ".join(parts) + "]"

    out: list[str] = []
    for line in body.splitlines():
        m = _CITE_LINE_RE.match(line.strip())
        if m:
            lab = label(m.group(1) or m.group(2))
            if lab:
                out.append(f"[{lab}]{m.group(3)}{m.group(4)}")
                continue
        out.append(_REF_RE.sub(ref, line))
    return "\n".join(out)
