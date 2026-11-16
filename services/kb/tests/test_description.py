"""The frontmatter description summarises the entry, not the first mention.

Taking it from the first mention note meant it ignored every later session and
every canon ruling: Huludan stayed described as "the entity Holodarn serves"
after the GM ruled that Holodarn is not a name at all. The description is what
the indexes and the wiki export show, so it has to reflect the finished entry.
"""

from pathlib import Path

from pnp_okf.emit import _lead_text, _short_desc, emit_entity
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


def test_short_sentence_is_unchanged():
    assert _short_desc("Kurz.") == "Kurz."


def test_first_sentence_is_taken():
    assert _short_desc("Erster Satz. Zweiter Satz.") == "Erster Satz."


def test_abbreviation_does_not_end_the_sentence():
    assert _short_desc("Er trägt z. B. ein Schwert. Danach mehr.") == "Er trägt z. B. ein Schwert."


def test_common_abbreviations_do_not_end_a_sentence():
    assert _short_desc("Die Hexe von St. Arran lebt dort. Mehr.") == "Die Hexe von St. Arran lebt dort."
    assert _short_desc("Sie traf Nr. Sieben im Turm. Mehr.") == "Sie traf Nr. Sieben im Turm."


def test_whitespace_and_newlines_are_collapsed():
    assert _short_desc("Erster\n\nSatz.   Zweiter") == "Erster Satz."


def test_long_sentence_is_cut_at_a_word_boundary():
    text = "wort " * 40 + "wort"
    out = _short_desc(text)
    assert out.endswith("…")
    assert len(out) <= 140
    core = out[:-1]
    assert core and not core.endswith(" ")
    assert text.startswith(core) and text[len(core)] == " "


def test_first_sentence_longer_than_limit_falls_back_to_word_cut():
    text = "wort " * 40 + "wort. Danach kurz."
    out = _short_desc(text)
    assert out.endswith("…") and len(out) <= 140
    assert text[len(out) - 1] == " "
