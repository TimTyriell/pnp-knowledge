"""Unit tests for the claim splitter and scorer behind the claim-level eval (B3).

Pure functions only: no bundle, no transcripts, no LLM. The gated end-to-end
check lives in test_claim_eval.py.
"""

from __future__ import annotations

import pytest
from pnp_okf.claims import score, split_claims


def test_splits_plain_german_sentences():
    body = (
        "Brim ist ein zwergischer Krieger, der die Gruppe seit einiger Zeit begleitet. "
        "Er hat sich bislang keiner Gilde angeschlossen."
    )
    assert split_claims(body) == [
        "Brim ist ein zwergischer Krieger, der die Gruppe seit einiger Zeit begleitet.",
        "Er hat sich bislang keiner Gilde angeschlossen.",
    ]


def test_does_not_split_after_german_abbreviations():
    body = (
        "Er kämpft z. B. mit einer schweren Axt und trägt eine alte Rüstung aus Eisen. "
        "Die Gruppe folgt ihm dann durch den Wald zur alten Burg."
    )
    sentences = split_claims(body)
    assert len(sentences) == 2
    assert sentences[0].startswith("Er kämpft z. B. mit einer")


def test_abbreviations_nr_and_ca_do_not_end_a_sentence():
    body = "Das ist Szene Nr. 3 von ca. zehn Szenen, die die Gruppe in der Stadt gespielt hat."
    assert len(split_claims(body)) == 1


def test_drops_sentences_under_six_words():
    body = "Ja. Er kommt mit der Gruppe zur alten Burg im Norden."
    assert split_claims(body) == ["Er kommt mit der Gruppe zur alten Burg im Norden."]


def test_strips_headings_bullets_and_links_but_keeps_citation_markers():
    body = (
        "## Überblick\n\n"
        "- [Brim](/characters/brim.md) kämpft seit langer Zeit an der Seite der Gruppe [P-40]."
    )
    assert split_claims(body) == [
        "Brim kämpft seit langer Zeit an der Seite der Gruppe [P-40]."
    ]


@pytest.mark.parametrize("heading", ["# Belege", "## Belege"])
def test_stops_at_the_belege_section(heading):
    # The bundle uses both heading levels (1121 vs 61 files); a citation line
    # ("[P-40] Session ...") must never be scored as a claim.
    body = (
        "Brim kämpft seit langer Zeit an der Seite der Gruppe in allen Kämpfen.\n\n"
        f"{heading}\n\n"
        "[P-40] Session 2026-03-10 @ 00:20:50, https://www.youtube.com/watch?v=x\n"
    )
    assert split_claims(body) == [
        "Brim kämpft seit langer Zeit an der Seite der Gruppe in allen Kämpfen."
    ]


def test_score_rates_per_stratum_excluding_unclear_and_unlabelled():
    labels = [
        {"type": "Event", "tier": "deep", "verdict": "supported"},
        {"type": "Event", "tier": "deep", "verdict": "unsupported"},
        {"type": "NPC", "tier": "brief", "verdict": "supported"},
        {"type": "NPC", "tier": "brief", "verdict": "unclear"},
        {"type": "NPC", "tier": "brief", "verdict": ""},
    ]
    result = score(labels)

    assert result["labelled"] == 4  # non-empty verdicts, including unclear
    assert result["n"] == 3  # scored: unclear excluded, unlabelled excluded
    assert result["supported_rate"] == pytest.approx(2 / 3)
    assert result["by_type"]["Event"]["supported_rate"] == pytest.approx(0.5)
    assert result["by_type"]["NPC"]["supported_rate"] == pytest.approx(1.0)
    assert result["by_tier"]["brief"]["n"] == 1


def test_score_refuses_an_unknown_verdict():
    # A typo ("suported") must fail loudly, not silently drop out of the rate.
    with pytest.raises(ValueError, match="unknown verdict"):
        score([{"type": "NPC", "tier": "brief", "verdict": "suported"}])


def test_score_of_nothing_has_no_rate():
    assert score([])["supported_rate"] is None
