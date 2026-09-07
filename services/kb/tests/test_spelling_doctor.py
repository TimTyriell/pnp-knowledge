"""Unit tests for spelling_doctor's own classification rules over a small
fixture registry/rules/bundle, instead of the real (large) knowledge tree —
see test_spelling_sweep.py for checks against the real bundle.

The doctor's whole design rests on three exclusions (see its module
docstring): only concepts with a canonical_name: pin are checked; a variant
that is simply one of the canonical name's own words used alone is not a
misspelling; and a variant must fuzzy-match a word of the canonical name to
count as a mishearing at all, so an unrelated nickname doesn't get flagged.
Today those exclusions live only in prose comments — this pins them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spelling_doctor import is_shortened_reference, looks_like_mishearing  # noqa: E402


def test_mishearing_is_detected():
    assert looks_like_mishearing("Lanra", "Landra, die Hag")
    assert looks_like_mishearing("Willoch", "Willauch")


def test_shortened_reference_is_not_a_misspelling():
    assert is_shortened_reference("Gilde", "Die Gilde von Ehrenfels")


def test_unrelated_nickname_does_not_look_like_a_mishearing():
    assert not looks_like_mishearing("Moorhexe Hack", "Landra, die Hag")


def test_unpinned_concept_is_not_checked_at_all(tmp_path: Path):
    import yaml
    from spelling_doctor import pinned_concept_ids

    rules = tmp_path / "entity_rules.yaml"
    rules.write_text(yaml.safe_dump({"canonical_name": {"npcs/landra": "Landra, die Hag"}}), encoding="utf-8")

    import spelling_doctor

    original_rules = spelling_doctor.RULES
    spelling_doctor.RULES = rules
    try:
        pinned = pinned_concept_ids()
    finally:
        spelling_doctor.RULES = original_rules

    assert pinned == {"npcs/landra"}
    assert "npcs/some_other_npc" not in pinned
