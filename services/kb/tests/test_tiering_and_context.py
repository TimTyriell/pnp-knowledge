"""Checks for the depth machinery: tiering, source matching, excerpt windows."""

from __future__ import annotations

import logging
from pathlib import Path

from pnp_okf.context import (
    MAX_SECONDARY_SECTIONS,
    SOURCE_BUDGET_CHARS,
    excerpts_for,
    load_sources,
    secondary_sources_for,
    sources_for,
)
from pnp_okf.models import (
    CanonicalEntity,
    EntityType,
    MentionRef,
    Segment,
    SessionTranscript,
)

# Reproduces the real canon file's hard cases: two same-name persons (one
# explicitly routed, one not), a short name that must not fuzzy-drift, and a
# heading with no directive at all (the back-compat fallback path).
_CANON_FIXTURE = (
    "### Harald (Freibeuter)\n<!-- okf: entity=npcs/harald_freibeuter -->\n\n"
    "ENTSCHEIDUNG: Freibeuter-Kapitän mit Rapier.\n\n"
    "### Harald (Dämon)\n<!-- okf: entity=npcs/harald_daemon -->\n\n"
    "ENTSCHEIDUNG: Magier-Dämon mit Seelenstein.\n\n"
    "### Nox\n<!-- okf: entity=npcs/nox -->\n\nENTSCHEIDUNG: männlich.\n\n"
    "### Nerithis, Mutter der Fluten\n\nGöttin der Ozeane.\n"
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
    assert _entity("locations/breska", EntityType.LOCATION, "Breska", 5).tier == "deep"
    assert _entity("locations/breska", EntityType.LOCATION, "Breska", 4).tier == "standard"
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


def test_directive_is_stripped_from_section_text(tmp_path: Path):
    (tmp_path / "canon.md").write_text(_CANON_FIXTURE, encoding="utf-8")
    sections = load_sources(tmp_path)
    for s in sections:
        assert "<!-- okf:" not in s.text
        assert "okf:" not in s.text
    # The directive-less heading still parses fine, with no targets set.
    nerithis = next(s for s in sections if s.heading.startswith("Nerithis"))
    assert nerithis.targets == frozenset()
    assert nerithis.mentions_ok is True


def test_all_directives_in_a_section_are_stripped(tmp_path: Path):
    # A second directive further down a section (a pasted template, a stray
    # comment) used to survive into the prompt: only the first was removed.
    (tmp_path / "canon.md").write_text(
        "### Hartwacht\n<!-- okf: entity=locations/hartwacht -->\n\n"
        "ENTSCHEIDUNG: Hartwacht ist eine Stadt.\n\n"
        "<!-- okf: entity=<typ>/<concept_id> -->\n",
        encoding="utf-8",
    )
    section = load_sources(tmp_path)[0]
    assert "okf:" not in section.text
    assert section.targets == frozenset({"locations/hartwacht"})


def test_explicit_entity_beats_slug_match(tmp_path: Path):
    (tmp_path / "canon.md").write_text(_CANON_FIXTURE, encoding="utf-8")
    sections = load_sources(tmp_path)

    freibeuter = _entity("npcs/harald_freibeuter", EntityType.NPC, "Harald")
    daemon = _entity("npcs/harald_daemon", EntityType.NPC, "Harald")

    freibeuter_text = sources_for(freibeuter, sections)
    daemon_text = sources_for(daemon, sections)
    assert "Rapier" in freibeuter_text and "Seelenstein" not in freibeuter_text
    assert "Seelenstein" in daemon_text and "Rapier" not in daemon_text

    # A third entity whose name would fuzzy-match the directive-bearing
    # heading's slug, but isn't in its explicit entity= list, gets nothing —
    # explicit routing suppresses the fallback for that section entirely.
    impostor = _entity("npcs/harald_impostor", EntityType.NPC, "Harald Freibeuter")
    assert sources_for(impostor, sections) == ""

    # The one heading with no directive still falls back to slug matching.
    goddess = _entity("deities/nerithis", EntityType.DEITY, "Nerithis")
    assert "Ozeane" in sources_for(goddess, sections)


def test_unknown_directive_key_warns(tmp_path: Path, caplog):
    (tmp_path / "canon.md").write_text(
        "### Bruchstueck\n<!-- okf: entiti=npcs/typo -->\n\nENTSCHEIDUNG: x.\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="pnp_okf.context"):
        sections = load_sources(tmp_path)
    assert sections[0].targets == frozenset()  # the typo'd key parsed to nothing
    assert any("unknown okf directive key" in r.message for r in caplog.records)


def _mentioning_entity(concept_id: str, name: str, note: str) -> CanonicalEntity:
    return CanonicalEntity(
        concept_id=concept_id,
        type=EntityType.CHARACTER,
        canonical_name=name,
        mentions=[
            MentionRef(session_id="s0", date="2025-01-01", url="http://x",
                       citation_ts="00:10:00", note=note),
        ],
    )


def test_secondary_sources_respect_budget(tmp_path: Path):
    # Eight distinct headings, each independently mentioned in the entity's
    # own notes, and each individually smaller than the budget — only the
    # section-count cap should bind here.
    lines = []
    names = [f"Randfigur{i}" for i in range(8)]
    for n in names:
        lines.append(f"### {n}\n\nENTSCHEIDUNG: Kurzer Kanon-Satz zu {n}.\n")
    (tmp_path / "canon.md").write_text("\n".join(lines), encoding="utf-8")
    sections = load_sources(tmp_path)

    note = "Auf der Reise treffen sie " + ", ".join(names) + "."
    ent = _mentioning_entity("characters/held", "Held", note)

    secondary = secondary_sources_for(ent, sections)
    assert secondary
    hit_count = secondary.count("### Randfigur")
    assert hit_count <= MAX_SECONDARY_SECTIONS
    assert len(secondary) <= SOURCE_BUDGET_CHARS


def test_secondary_sections_stay_out_of_primary_block(tmp_path: Path):
    (tmp_path / "canon.md").write_text(
        "### Nyruk\n<!-- okf: entity=npcs/nyruk -->\n\n"
        "ENTSCHEIDUNG: Nyruk ist ein Eisbär.\n\n"
        "### Nyrella\n<!-- okf: entity=characters/nyrella -->\n\n"
        "ENTSCHEIDUNG: Nyrella ist eine Faery.\n",
        encoding="utf-8",
    )
    sections = load_sources(tmp_path)

    nyrella = _mentioning_entity(
        "characters/nyrella", "Nyrella", "Ihr Begleiter ist der Eisbär Nyruk."
    )
    primary = sources_for(nyrella, sections)
    secondary = secondary_sources_for(nyrella, sections)

    assert "Faery" in primary  # Nyrella's own ruling
    assert "Nyruk ist ein Eisbär" not in primary  # Nyruk's ruling, not hers
    assert "Nyruk ist ein Eisbär" in secondary
    assert "Nyrella ist eine Faery" not in secondary  # never repeat the primary


def test_secondary_keeps_a_ruling_whose_heading_prefixes_a_primary_one(tmp_path: Path):
    # "### Dodo" is a substring of "### Dodos heiliger Streitkolben": the old
    # dedupe compared rendered text and dropped Dodo's own ruling as "already
    # primary", though it is a different concept.
    (tmp_path / "canon.md").write_text(
        "### Dodos heiliger Streitkolben\n<!-- okf: entity=items/streitkolben -->\n\n"
        "ENTSCHEIDUNG: Der Streitkolben ist geweiht.\n\n"
        "### Dodo\n<!-- okf: entity=characters/dodo -->\n\n"
        "ENTSCHEIDUNG: Dodo ist ein Zwerg.\n",
        encoding="utf-8",
    )
    sections = load_sources(tmp_path)
    hammer = _mentioning_entity(
        "items/streitkolben", "Streitkolben", "Die Waffe gehoert Dodo."
    )
    assert "Dodo ist ein Zwerg" in secondary_sources_for(hammer, sections)


def test_secondary_sources_respect_mentions_off(tmp_path: Path):
    (tmp_path / "canon.md").write_text(
        "### Randnotiz\n<!-- okf: mentions=off -->\n\n"
        "ENTSCHEIDUNG: Gilt nur fuer den eigenen Eintrag.\n",
        encoding="utf-8",
    )
    sections = load_sources(tmp_path)
    ent = _mentioning_entity("characters/held", "Held", "Erwaehnt wird Randnotiz.")
    assert secondary_sources_for(ent, sections) == ""


def test_subsections_inherit_the_entity_they_sit_under(tmp_path: Path):
    """The harvested-wiki shape: an "## <entity>" anchor with no body of its
    own, subdivided by "###". Before ancestor-aware slugs the anchor was
    dropped as empty and every subsection was orphaned under a generic slug
    ("ueberblick"), so the entity itself got nothing at all."""

    (tmp_path / "wiki.md").write_text(
        "## Kaya\n"
        "### Ueberblick\n\nFaun-Bardin.\n\n"
        "### Chronologie\n\nTritt in Session 1 auf.\n",
        encoding="utf-8",
    )
    sections = load_sources(tmp_path)

    # The heading stays the section's own text; only the slug folds in the anchor.
    assert [s.heading for s in sections] == ["Ueberblick", "Chronologie"]
    assert [s.slug for s in sections] == ["kaya_ueberblick", "kaya_chronologie"]

    matched = sources_for(_entity("characters/kaya", EntityType.CHARACTER, "Kaya"), sections)
    assert "Faun-Bardin" in matched and "Session 1" in matched
    # ...and it does not spill onto an unrelated entity via the generic subheading.
    assert sources_for(_entity("characters/sange", EntityType.CHARACTER, "Sange"), sections) == ""


def test_subsections_inherit_an_ancestor_directive(tmp_path: Path):
    (tmp_path / "wiki.md").write_text(
        "## Lindo Laut\n<!-- okf: entity=characters/lindo_laut -->\n\n"
        "Aus dem Wiki.\n\n"
        "### Faehigkeiten\n\nGestaltwandel.\n\n"
        "### Sonderfall\n<!-- okf: entity=items/amulett -->\n\nGehoert zum Amulett.\n",
        encoding="utf-8",
    )
    by_heading = {s.heading: s for s in load_sources(tmp_path)}

    # Inherited from the anchor...
    assert by_heading["Faehigkeiten"].targets == frozenset({"characters/lindo_laut"})
    # ...but a subsection's own directive wins over it.
    assert by_heading["Sonderfall"].targets == frozenset({"items/amulett"})

    lindo = _entity("characters/lindo_laut", EntityType.CHARACTER, "Lindo Laut")
    matched = sources_for(lindo, list(by_heading.values()))
    assert "Gestaltwandel" in matched
    assert "Gehoert zum Amulett" not in matched


def test_belege_sections_are_dropped(tmp_path: Path):
    """A harvested evidence list is numbered for the wiki page, not for this
    entity's mentions — injecting it invites citing by the wrong number."""

    (tmp_path / "wiki.md").write_text(
        "## Kaya\n<!-- okf: entity=characters/kaya -->\n\nFaun-Bardin.\n\n"
        "### Belege\n\n[1] Session 2026-06-04\n",
        encoding="utf-8",
    )
    assert [s.heading for s in load_sources(tmp_path)] == ["Kaya"]


def test_stray_citation_markers_are_stripped(tmp_path: Path):
    """"[n]" in a prompt means the nth mention of THIS entity, so a number
    carried in from wiki prose would be relabelled into a wrong episode."""

    (tmp_path / "wiki.md").write_text(
        "## Kaya\n<!-- okf: entity=characters/kaya -->\n\n"
        "Sie tritt in der Taverne auf [1] und durchschaut Luegen [2].\n",
        encoding="utf-8",
    )
    sections = load_sources(tmp_path)
    matched = sources_for(_entity("characters/kaya", EntityType.CHARACTER, "Kaya"), sections)
    assert "[1]" not in matched and "[2]" not in matched
    assert "Taverne auf und" in matched  # the space goes with the marker


def test_only_rulings_attach_as_secondary(tmp_path: Path):
    """SYNTH_SECONDARY_TEMPLATE announces the block as "Festlegungen zu
    ANDEREN Entitaeten". Reference lore is not a Festlegung — and a generic
    subheading like "Faehigkeiten" outranks real rulings under the
    longest-name-first cap, taking their slots."""

    (tmp_path / "canon.md").write_text(
        "### Faehigkeiten\n\nEine lange Liste von Faehigkeiten.\n\n"
        "### Nyruk\n\nENTSCHEIDUNG: Nyrellas Eisbaer heisst Nyruk.\n",
        encoding="utf-8",
    )
    sections = load_sources(tmp_path)
    ent = _mentioning_entity("characters/held", "Held", "Zeigt Faehigkeiten und trifft Nyruk.")
    out = secondary_sources_for(ent, sections)
    assert "Eisbaer" in out
    assert "lange Liste" not in out


if __name__ == "__main__":
    test_tiers()
    test_sources_match_across_punctuation_drift(Path(__import__("tempfile").mkdtemp()))
    test_excerpt_window_and_overlap_merge()
    test_excerpts_skip_entities_without_transcripts()
    print("all checks passed")
