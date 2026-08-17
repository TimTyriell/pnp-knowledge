"""The frontmatter description summarises the entry, not the first mention.

Taking it from the first mention note meant it ignored every later session and
every canon ruling: Huludan stayed described as "the entity Holodarn serves"
after the GM ruled that Holodarn is not a name at all. The description is what
the indexes and the wiki export show, so it has to reflect the finished entry.
"""

from pathlib import Path

from pnp_okf.emit import _lead_text, emit_entity
from pnp_okf.models import CanonicalEntity, EntityType, MentionRef


def _entity():
    return CanonicalEntity(
        concept_id="deities/huludan", type=EntityType.DEITY, canonical_name="Huludan",
        mentions=[MentionRef(session_id="s", date="2026-05-13", url="u",
                             citation_ts="00:10:00",
                             note="Eine Entität, der Holodarn dient.")],
    )


def test_description_comes_from_the_body(tmp_path: Path):
    body = "## Überblick\n\n**Huludan** ist ein Titan.\n\n# Belege\n\n1. Session"
    emit_entity(tmp_path / "b", _entity(), body)
    doc = (tmp_path / "b" / "deities" / "huludan.md").read_text(encoding="utf-8")
    assert "Huludan ist ein Titan." in doc
    assert "Holodarn dient" not in doc


def test_falls_back_to_the_note_when_the_body_has_no_prose(tmp_path: Path):
    emit_entity(tmp_path / "b", _entity(), "# Belege\n\n1. Session")
    doc = (tmp_path / "b" / "deities" / "huludan.md").read_text(encoding="utf-8")
    assert "Holodarn dient" in doc


def test_markup_is_stripped():
    body = "Sie übergibt [Lindo Laut](/characters/lindo_laut.md) das **Amulett**."
    assert _lead_text(body) == "Sie übergibt Lindo Laut das Amulett."


def test_headings_and_lists_are_skipped():
    assert _lead_text("# Titel\n\n- Punkt\n\nEchter Text.") == "Echter Text."
