"""Two structural fixes from the 2026-09-05 prompt-v6 migration.

1. `spelling:` now reaches identity, not just prose. It used to be applied
   only in links.py, so a mishearing the GM had already ruled on could still
   mint its own node: the rule said Willau -> Willauch and the bundle grew
   locations/taverne_in_willau anyway. `merge:` did not catch it either --
   merge matches a whole name, and the model had coined a compound.

2. Extraction can be frozen per session, so a PROMPT_VERSION bump only
   re-extracts sessions recorded after a cutoff instead of re-deriving (and
   re-naming) the entire back catalogue.
"""

import os

import pytest
from pnp_okf.extract import _frozen_prompt_version
from pnp_okf.models import EntityType
from pnp_okf.prompts import PROMPT_VERSION
from pnp_okf.resolve import _default_concept_id

SPELLINGS = {"Willau": "Willauch", "Willoch": "Willauch", "Zebras": "Zebros"}


class _T:
    def __init__(self, date):
        self.date = date


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Taverne in Willau", "locations/taverne_in_willauch"),
        ("Heimkehr nach Willoch", "locations/heimkehr_nach_willauch"),
        ("Koenigreich von Zebras", "locations/koenigreich_von_zebros"),
    ],
)
def test_spelling_reaches_the_concept_id(name, expected):
    assert _default_concept_id(EntityType.LOCATION, name, SPELLINGS) == expected


def test_without_spellings_the_id_is_unchanged():
    # The map is optional; callers that pass nothing keep the old behaviour.
    assert (
        _default_concept_id(EntityType.LOCATION, "Taverne in Willau")
        == "locations/taverne_in_willau"
    )


@pytest.fixture
def _freeze(monkeypatch):
    monkeypatch.setenv("PNP_EXTRACT_FREEZE_BEFORE", "2026-09-06")
    monkeypatch.setenv("PNP_EXTRACT_FREEZE_VERSION", "FROZEN")


def test_sessions_before_the_cutoff_are_frozen(_freeze):
    assert _frozen_prompt_version(_T("2025-03-26")) == "FROZEN"
    assert _frozen_prompt_version(_T("2026-09-05")) == "FROZEN"


def test_sessions_from_the_cutoff_onward_use_the_live_version(_freeze):
    # Cutoff is exclusive: a session dated exactly on it is NOT frozen.
    assert _frozen_prompt_version(_T("2026-09-06")) == PROMPT_VERSION
    assert _frozen_prompt_version(_T("2026-10-01")) == PROMPT_VERSION


def test_half_configured_freeze_is_ignored(monkeypatch):
    # Either var alone must not freeze anything -- the safe default is
    # "re-extract", so a typo cannot silently pin the corpus forever.
    monkeypatch.setenv("PNP_EXTRACT_FREEZE_BEFORE", "2026-09-06")
    monkeypatch.delenv("PNP_EXTRACT_FREEZE_VERSION", raising=False)
    assert _frozen_prompt_version(_T("2025-03-26")) == PROMPT_VERSION
    monkeypatch.delenv("PNP_EXTRACT_FREEZE_BEFORE")
    monkeypatch.setenv("PNP_EXTRACT_FREEZE_VERSION", "FROZEN")
    assert _frozen_prompt_version(_T("2025-03-26")) == PROMPT_VERSION
