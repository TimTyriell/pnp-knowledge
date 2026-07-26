"""Checks for the depth machinery: tiering, source matching, excerpt windows."""

from __future__ import annotations

from pathlib import Path

from pnp_okf.context import excerpts_for, load_sources, sources_for
from pnp_okf.models import (
    CanonicalEntity,
    EntityType,
    MentionRef,
    Segment,
    SessionTranscript,
)


def _entity(concept_id, etype, name, n_mentions=1, important=False, aliases=None):
    return CanonicalEntity(
        concept_id=concept_id,
        type=etype,
        canonical_name=name,
        aliases=aliases or [],
        important=important,
        mentions=[
            MentionRef(
                session_id=f"s{i}",
                date=f"2025-01-{i + 1:02d}",
                url="http://x",
                citation_ts="00:10:00",
                note="n",
            )
            for i in range(n_mentions)
        ],
    )


def test_tiers():
    # Player characters and deities go deep once corroborated...
    assert _entity("characters/dodo", EntityType.CHARACTER, "Dodo", 2).tier == "deep"
    assert _entity("deities/vharzul", EntityType.DEITY, "Vhar'Zul", 2).tier == "deep"
    # ...but a single passing mention cannot carry a long entry, so it drops to
    # standard rather than being padded out to 1500 words.
    assert _entity("characters/finn", EntityType.CHARACTER, "Finn", 1).tier == "standard"
    assert _entity("deities/gruul", EntityType.DEITY, "Gruul", 1).tier == "standard"
    # The hand-set flag is the escape hatch for the rules' blind spot: a
    # pivotal NPC fragmented across spellings shows only one mention.
    assert _entity("npcs/voras", EntityType.NPC, "Voras").tier == "brief"
    assert _entity("npcs/voras", EntityType.NPC, "Voras", important=True).tier == "deep"
    # High mention count promotes on its own.
    assert _entity("locations/breska", EntityType.LOCATION, "Breska", 8).tier == "deep"
    assert _entity("locations/breska", EntityType.LOCATION, "Breska", 7).tier == "standard"
    # Small closed sets clear the stub tier even on one mention.
    assert _entity("factions/gilde", EntityType.FACTION, "Gilde").tier == "standard"
    # One-off props stay brief so they don't get padded.
    assert _entity("items/dolch", EntityType.ITEM, "Dolch").tier == "brief"


def test_sources_match_across_punctuation_drift(tmp_path: Path):
    (tmp_path / "pantheon.md").write_text(
        "# Pantheon\n\n"
        "### Vhar Zul, der Gerissene\n\nGott der List.\n\n"
        "### Nerithis, Mutter der Fluten\n\nGöttin der Ozeane.\n",
        encoding="utf-8",
    )
    sections = load_sources(tmp_path)
    # The h1 document title is not a section; only the two h3 entries are.
    assert [s.heading for s in sections] == [
        "Vhar Zul, der Gerissene",
        "Nerithis, Mutter der Fluten",
    ]

    # The bundle spells it Vhar'Zul, the scripture Vhar Zul — slugs align.
    ent = _entity("deities/vharzul", EntityType.DEITY, "Vhar'Zul, der Gerissene")
    matched = sources_for(ent, sections)
    assert "Gott der List" in matched
    assert "Göttin der Ozeane" not in matched

    # An unrelated entity pulls nothing in.
    assert sources_for(_entity("items/dolch", EntityType.ITEM, "Dolch"), sections) == ""


def test_excerpt_window_and_overlap_merge():
    segments = [
        Segment(start=float(t), end=float(t) + 5, speaker="GM", text=f"line{t}")
        for t in range(0, 1200, 60)
    ]
    transcript = SessionTranscript(
        session_id="s0", date="2025-01-01", url="http://x", segments=segments
    )
    ent = CanonicalEntity(
        concept_id="characters/dodo",
        type=EntityType.CHARACTER,
        canonical_name="Dodo",
        mentions=[
            MentionRef(
                session_id="s0", date="2025-01-01", url="http://x",
                citation_ts="00:10:00", note="n",
            ),
            # Overlapping window: must not duplicate the shared dialogue.
            MentionRef(
                session_id="s0", date="2025-01-01", url="http://x",
                citation_ts="00:10:30", note="n",
            ),
        ],
    )
    out = excerpts_for(ent, {"s0": transcript}, window_s=90)
    assert "line600" in out                       # at the citation
    assert out.count("line600") == 1              # overlap merged, not repeated
    assert "line540" in out and "line660" in out  # inside the window
    assert "line0" not in out                     # far outside it


def test_excerpts_skip_entities_without_transcripts():
    ent = _entity("npcs/x", EntityType.NPC, "X")
    assert excerpts_for(ent, {}) == ""


if __name__ == "__main__":
    test_tiers()
    test_sources_match_across_punctuation_drift(Path(__import__("tempfile").mkdtemp()))
    test_excerpt_window_and_overlap_merge()
    test_excerpts_skip_entities_without_transcripts()
    print("all checks passed")
