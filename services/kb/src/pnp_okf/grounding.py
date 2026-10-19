"""Is an extracted entity's name actually spoken near the moment it cites?

A cheap, deterministic correctness signal for extraction (docs/plans/A5).
It cannot prove a note is true, but a name that never occurs within the
cited window -- or nowhere in the session -- is a strong hint the model
invented the citation or the entity. Coined event names score low by
nature, so they are reported separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pnp_okf.context import _parse_ts
from pnp_okf.models import SessionExtraction, SessionTranscript

WINDOW_S = 120.0
# Shorter tokens ("Ox", "Ai") occur inside too many ordinary words for a
# substring hit to mean anything, so such names are left unscorable.
MIN_TOKEN = 4
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def name_tokens(name: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(name) if len(t) >= MIN_TOKEN}


@dataclass
class GroundingCounts:
    near: int = 0
    elsewhere: int = 0
    nowhere: int = 0
    unscorable: int = 0   # no token >= MIN_TOKEN, or unparseable timestamp

    @property
    def scored(self) -> int:
        return self.near + self.elsewhere + self.nowhere

    @property
    def near_ratio(self) -> float:
        return self.near / self.scored if self.scored else 0.0


def ground_session(
    transcript: SessionTranscript, extraction: SessionExtraction, window: float = WINDOW_S
) -> dict[str, GroundingCounts]:
    """Counts keyed by "all" and by entity type value (e.g. "Event")."""

    segs = [(s.start, s.text.lower()) for s in transcript.segments]
    # Substring matching, not word matching, is deliberate: German inflects
    # names ("Lindos", "Rotunas'") and Whisper splits compounds.
    whole = " ".join(t for _, t in segs)
    out: dict[str, GroundingCounts] = {"all": GroundingCounts()}
    for m in extraction.entities:
        bucket = out.setdefault(m.type.value, GroundingCounts())
        tokens = name_tokens(m.name)
        ts = _parse_ts(m.citation_ts)
        if not tokens or ts is None:
            out["all"].unscorable += 1
            bucket.unscorable += 1
            continue
        near_text = " ".join(t for start, t in segs if abs(start - ts) <= window)
        if any(tok in near_text for tok in tokens):
            kind = "near"
        elif any(tok in whole for tok in tokens):
            kind = "elsewhere"
        else:
            kind = "nowhere"
        for c in (out["all"], bucket):
            setattr(c, kind, getattr(c, kind) + 1)
    return out
