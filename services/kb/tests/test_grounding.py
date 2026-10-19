"""Unit tests for the citation-grounding signal (pnp_okf.grounding).

These pin the four-way classification on a hand-made transcript, so the
corpus ratchet in test_extraction_quality.py can be trusted: if this file is
green, a drop in the measured number means the extractor changed, not the
scorer.
"""

from __future__ import annotations

from pnp_okf.grounding import GroundingCounts, ground_session, name_tokens
from pnp_okf.models import (
    EntityMention,
    EntityType,
    Segment,
    SessionExtraction,
    SessionTranscript,
)


def _transcript() -> SessionTranscript:
    return SessionTranscript(
        session_id="2099-01-01_TEST",
        date="2099-01-01",
        url="",
        segments=[
            Segment(start=0, end=5, speaker="Spieler", text="Wir treffen Rotunas"),
            Segment(start=300, end=305, speaker="Spieler", text="Lange Pause"),
            # "Noxus" rather than "Nox": tokens shorter than MIN_TOKEN (4) are
            # ignored, so a three-letter name is unscorable, not "elsewhere".
            Segment(start=900, end=905, speaker="Spieler", text="Noxus lacht"),
        ],
    )


def _mention(name: str, ts: str, kind: EntityType = EntityType.CHARACTER) -> EntityMention:
    return EntityMention(name=name, type=kind, note="", citation_ts=ts)


def test_name_tokens_drop_short_words_and_fold_case():
    assert name_tokens("Ox") == set()
    assert name_tokens("Der Lindo-Laut") == {"lindo", "laut"}


def test_four_way_classification_on_a_small_session():
    extraction = SessionExtraction(
        recap="",
        entities=[
            _mention("Rotunas", "00:00:30"),        # spoken within the window
            _mention("Noxus", "00:00:30"),          # spoken only at 900s
            _mention("Esterossa", "00:00:30"),      # spoken nowhere
            _mention("Ox", "00:00:30"),             # no token >= 4
            _mention("Rotunas", "kaputt"),          # unparseable timestamp
        ],
    )

    counts = ground_session(_transcript(), extraction)["all"]

    assert counts == GroundingCounts(near=1, elsewhere=1, nowhere=1, unscorable=2)
    assert counts.scored == 3
    assert counts.near_ratio == 1 / 3


def test_event_mentions_are_bucketed_separately():
    extraction = SessionExtraction(
        recap="",
        entities=[
            _mention("Rotunas", "00:00:30"),
            _mention("Rotunas-Fest", "00:00:30", EntityType.EVENT),  # tokens: rotunas, fest
            _mention("Rotunas-Fest", "00:15:00", EntityType.EVENT),  # 900s is outside window
        ],
    )

    out = ground_session(_transcript(), extraction)

    # "rotunas" from the 0s segment still counts as spoken in the session, so
    # the out-of-window Event is "elsewhere", not "nowhere".
    assert out["all"].near == 2
    assert out["all"].elsewhere == 1
    assert out["all"].nowhere == 0
    assert out["Event"].near == 1
    assert out["Event"].elsewhere == 1
    assert out["Character"].near == 1


def test_window_is_inclusive_at_its_edge():
    # Segment at 300s is exactly 120s from a mention at 180s: inside the window.
    t = SessionTranscript(
        session_id="2099-01-01_TEST",
        date="2099-01-01",
        url="",
        segments=[Segment(start=300, end=305, text="Rotunas")],
    )
    extraction = SessionExtraction(recap="", entities=[_mention("Rotunas", "00:03:00")])

    assert ground_session(t, extraction, window=120.0)["all"].near == 1
