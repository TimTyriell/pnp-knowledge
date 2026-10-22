"""RULES_GLOSSARY stays a short, mechanics-only cheat sheet (T3)."""

from __future__ import annotations

from pnp_okf.prompts import EXTRACT_SYSTEM, RULES_GLOSSARY, SYNTH_SYSTEM


def test_glossary_is_short():
    # A prompt prefix is paid on every call; past ~25 lines it stops being a
    # cheat sheet and starts competing with the actual instructions.
    assert len(RULES_GLOSSARY.strip().splitlines()) <= 25


def test_glossary_names_the_misreadings_it_exists_for():
    for term in ("markiert", "Hope", "Fear", "Domains", "Tier", "Würfel"):
        assert term in RULES_GLOSSARY, term


def test_glossary_is_not_yet_in_extraction_or_synthesis():
    # Wiring it in changes the prompt text, which is a budgeted re-extraction
    # (B2) or a synthesis version bump -- never a side effect of this plan.
    assert RULES_GLOSSARY not in EXTRACT_SYSTEM
    assert RULES_GLOSSARY not in SYNTH_SYSTEM
