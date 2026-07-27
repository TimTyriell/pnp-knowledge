"""Links written as the prose name must resolve to the concept id.

The synthesis links to whatever it called a thing — `npcs/vasul.md` for
`deities/vharzul`, `characters/lunara.md` for `characters/lunara_velora`. Those
targets are not concept ids, so they used to be dropped: 161 lost edges on the
v5 run. The directory in such a link is a guess too, so a unique name wins over
the directory hint.
"""

from pnp_okf.links import ConceptIndex

IDS = [
    "deities/vharzul",
    "characters/lunara_velora",
    "npcs/liam_velora",
    "npcs/hal_harl",
    "npcs/nox",
]
NAMES = {"Vhar'Zul": "deities/vharzul", "Vasul": "deities/vharzul",
         "Hal": "npcs/hal_harl", "Nox": "npcs/nox"}


def _index():
    return ConceptIndex(IDS, NAMES)


def test_alias_resolves_across_the_wrong_directory():
    assert _index().resolve("../npcs/vasul.md") == "deities/vharzul"


def test_unique_name_prefix_resolves():
    assert _index().resolve("../characters/lunara.md") == "characters/lunara_velora"
    assert _index().resolve("../npcs/hal.md") == "npcs/hal_harl"


def test_ambiguous_prefix_stays_unresolved():
    # "velora" extends into both Lunara and Liam, so it is a guess, not a link.
    assert _index().resolve("../characters/velora.md") is None


def test_concept_id_still_wins_over_a_name():
    # A real concept id must never be re-routed by the name table.
    index = ConceptIndex(["npcs/nox", "npcs/gildenmeister"],
                         {"Nox": "npcs/gildenmeister"})
    assert index.resolve("npcs/nox.md") == "npcs/nox"


def test_unknown_target_is_still_unresolved():
    assert _index().resolve("../npcs/erfundene_person.md") is None
