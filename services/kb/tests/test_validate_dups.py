"""Offline unit test for validate.py::_suspect_title_dups — the near-miss
title check added to catch a one-letter spelling split like
items/zebras_zorn vs items/streitkolben_von_dodo ("Zebras Zorn" / "Zebros
Zorn"), which neither the exact-match duplicate_titles check nor
_suspect_person_dups's slug-fuzzing (characters/npcs only) could see.
"""

from __future__ import annotations

from pnp_okf.validate import _suspect_title_dups


def test_near_miss_titles_are_flagged():
    items = [("items/zebras_zorn", "Zebras Zorn"), ("items/streitkolben_von_dodo", "Zebros Zorn")]
    assert _suspect_title_dups(items) == [("items/zebras_zorn", "items/streitkolben_von_dodo")]


def test_exact_title_match_is_not_flagged():
    # duplicate_titles' job, not this function's.
    items = [("factions/a", "Die Gnolle"), ("factions/b", "Die Gnolle")]
    assert _suspect_title_dups(items) == []


def test_unrelated_titles_are_not_flagged():
    items = [("npcs/a", "Lord Kalidarn"), ("npcs/b", "Voras der Heilige")]
    assert _suspect_title_dups(items) == []
