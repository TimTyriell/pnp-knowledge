"""The claim sampler's privacy scrub and stratified draw (B3).

Claim files are committed to git, so the speaker scrub is load-bearing: a
player's first name in a speaker label must never reach the repo. These tests
pin that behaviour; the sampler's output is checked by hand as well.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from claim_sampler import (  # noqa: E402
    assert_no_player_names,
    pick_stratified,
    scrub_names,
    scrub_speaker,
    scrub_window,
)


def test_scrub_keeps_the_character_in_parentheses_and_drops_the_player():
    assert scrub_speaker("Marco (Dodo)") == "Spieler (Dodo)"
    assert scrub_speaker("Tim (Lindo Laut)") == "Spieler (Lindo Laut)"
    assert scrub_speaker("Deniz (GM)") == "Spieler (GM)"
    assert scrub_speaker("Spieler 3 (Dante)") == "Spieler (Dante)"


def test_scrub_replaces_an_unparenthesised_label_with_spieler():
    assert scrub_speaker("SPEAKER_03") == "Spieler"


def test_scrub_window_rewrites_every_line_and_leaks_no_first_name():
    window = (
        "--- Session 2025-06-10 ---\n"
        "[01:12:31] Marco (Dodo): dann ist es ein Hitpoint\n"
        "[01:12:40] Deniz (GM): ok, weiter\n"
        "[01:12:44] SPEAKER_03: hm"
    )
    out = scrub_window(window)

    assert "[01:12:31] Spieler (Dodo): dann ist es ein Hitpoint" in out
    assert "[01:12:40] Spieler (GM): ok, weiter" in out
    assert "[01:12:44] Spieler: hm" in out
    assert "Marco" not in out and "Deniz" not in out
    assert out.startswith("--- Session 2025-06-10 ---")


def test_scrub_also_covers_names_spoken_in_dialogue_and_claim_text():
    # Players introduce themselves in dialogue; a bundle sentence can name one.
    # Labels alone (the first scrub) would let these into git.
    names = {"Christian", "Marco", "Celin"}
    window = "[00:02:28] Marco (Tibbet): Ja, ich bin Christian, ich spiele Tibbet."
    assert scrub_window(window, names) == (
        "[00:02:28] Spieler (Tibbet): Ja, ich bin Spieler, ich spiele Tibbet."
    )
    assert scrub_names("Celin erkennt die Statuen.", names) == "Spieler erkennt die Statuen."
    assert scrub_names("Der Marcoline wartet.", names) == "Der Marcoline wartet."


def test_the_output_gate_refuses_a_surviving_first_name():
    # Fail closed: one leaked player name blocks the whole file. Whole words
    # only, so "Tina" does not trip on "Tinas" in an unrelated name.
    with pytest.raises(SystemExit, match="Marco"):
        assert_no_player_names("[01:00:00] Marco (Dodo): hallo", {"Marco", "Tim"})
    assert_no_player_names("[01:00:00] Spieler (Dodo): hallo", {"Marco", "Tim"})


def _claim(i, typ, tier):
    return {"concept": f"x/{i}", "type": typ, "tier": tier, "claim": f"c{i}"}


def test_stratified_draw_guarantees_five_per_type_then_fills_to_n():
    pool = [_claim(i, "NPC", ["brief", "standard", "deep"][i % 3]) for i in range(20)]
    pool += [_claim(100 + i, "Event", "deep") for i in range(9)]
    pool += [_claim(200 + i, "Item", "brief") for i in range(3)]

    picked = pick_stratified(pool, n=20, seed=1234, min_per_type=5)

    assert len(picked) == 20
    kinds = [c["type"] for c in picked]
    assert kinds.count("NPC") >= 5 and kinds.count("Event") >= 5
    assert kinds.count("Item") == 3  # fewer than the floor: take them all


def test_stratified_draw_is_reproducible_for_a_seed():
    pool = [_claim(i, "NPC", "brief") for i in range(30)]
    a = pick_stratified(pool, n=10, seed=7)
    b = pick_stratified(pool, n=10, seed=7)
    c = pick_stratified(pool, n=10, seed=8)

    assert [x["claim"] for x in a] == [x["claim"] for x in b]
    assert [x["claim"] for x in a] != [x["claim"] for x in c]
