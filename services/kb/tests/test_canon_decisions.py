"""Every GM ruling in knowledge/sources/*.md must actually reach synthesis.

knowledge/conflicts/README.md documents the intended fix for a genuine canon
question: add an ``ENTSCHEIDUNG:`` paragraph under a ``### <Entity name>``
heading in Kanon_Entscheidungen.md, then re-run — synthesis is supposed to
treat that as overriding the session evidence. If the heading's name never
matches any entity (context.sources_for finds nothing), the ruling is
grounding nobody. A human can add and re-add it forever with no effect, and
the conflict it was meant to settle keeps reappearing — this was confirmed
for "Nox" and "Jen" (fixed by the context.py change on this branch) before
this test existed to catch the next one.

Not every heading names an entity — a handful are campaign-wide policy
("Was ein Gegenstand ist", "Benennung von Orten") that is deliberately never
meant to match anything — so unreachable-heading count is a ratchet against a
measured baseline, same as test_rules_applied.py, rather than a hard zero.
Each baseline entry is named below so raising it requires looking at what was
added, not just bumping a number.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from pnp_okf.context import _matches, load_sources
from pnp_okf.models import TYPE_DIR
from pnp_okf.okf import slugify

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
SOURCES_DIR = KNOWLEDGE / "sources"
CANON_FILE = SOURCES_DIR / "Kanon_Entscheidungen.md"
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"

pytestmark = pytest.mark.skipif(not CANON_FILE.exists(), reason="no bundle checked out")

_HEADING_RE = re.compile(r"^###[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Headings with an ENTSCHEIDUNG: that match no entity, measured on this
# branch. Two causes so far, both real: policy headings never meant to name
# an entity ("Benennung von Orten", "Was ein Gegenstand ist",
# "Was eine Fraktion ist", "Gott und Erscheinung"), and headings that used to
# name an entity but the entity was since renamed without the heading
# following ("Ring der Teleportation" -> title is now "Teleportationsring";
# "Lenra" -> title is now "Landra, die Hag"; "Sythraal" was never split into
# its own concept at all; "Die Hags" names a group, not the "Lenra" concept
# it rules on). Ratchet, not a target — new entries here should be looked at,
# not waved through by raising the number.
UNREACHED_RULING_BASELINE = 9

# Person-type entities (Character/NPC) grounded by the same heading, measured
# on this branch: Dodo (PC vs. an NPC alias of the same name), Hendrik vs.
# Hendrik Heinrich, the two Haralds, the two Hans, the two Adeligas. This is
# the I-002 gap (docs/architecture/IMPROVEMENTS.md) — a heading grounds every
# entity whose slug it touches, with no session/identity disambiguation.
# Ratchet, not a fix: I-002 is out of scope here (it invalidates the synth
# cache broadly).
AMBIGUOUS_PERSON_RULING_BASELINE = 6

# Non-empty "### <Name>" headings repeated within Kanon_Entscheidungen.md,
# measured on this branch: Ezhura, Nyrella, Silberkerne. Both copies get
# injected for any matching entity, which is at best redundant and at worst
# two different rulings quietly merged into one prompt. Fixing the source
# file is data curation, not a code change, so this is a ratchet: it may
# only go down.
DUPLICATE_HEADING_BASELINE = 3


def _canon_text() -> str:
    return _COMMENT_RE.sub("", CANON_FILE.read_text(encoding="utf-8"))


def _rulings() -> list[str]:
    """Headings whose section contains an ENTSCHEIDUNG: paragraph."""

    text = _canon_text()
    matches = list(_HEADING_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if "ENTSCHEIDUNG:" in text[m.end():end]:
            out.append(m.group(1))
    return out


def _bundle_entities() -> list[tuple[str, str, list[str]]]:
    """(concept_id, canonical_name, aliases) for every non-session concept."""

    out = []
    for etype_dir in TYPE_DIR.values():
        for path in sorted((BUNDLE / etype_dir).glob("*.md")):
            if path.name == "index.md":
                continue
            text = path.read_text(encoding="utf-8")
            fm = (text.split("---\n", 2)[1:2] or [""])[0]
            data = yaml.safe_load(fm) or {}
            name = str(data.get("title") or "").strip()
            if not name:
                continue
            aliases = [str(a).strip() for a in (data.get("aliases") or [])]
            out.append((f"{etype_dir}/{path.stem}", name, aliases))
    return out


def test_no_duplicate_headings():
    # Scoped to headings load_sources() actually turns into a section (i.e.
    # non-empty body) — an empty heading with nothing under it, like the
    # second stray "### Die Prinzessin" in the file today, is dead weight in
    # the markdown but not a functional duplicate: it never becomes a
    # SourceSection, so it can never shadow or double up a ruling. Also
    # scoped to this one file: load_sources() reads every file under
    # sources/, and a generic heading like "Überblick" legitimately repeats
    # once per source document — that is not the same failure mode.
    sections = [s for s in load_sources(SOURCES_DIR) if s.origin == CANON_FILE.name]
    dupes = sorted(h for h, n in Counter(s.heading for s in sections).items() if n > 1)
    assert len(dupes) <= DUPLICATE_HEADING_BASELINE, (
        f"{len(dupes)} duplicate non-empty '### ' headings in {CANON_FILE.name} "
        f"— both copies get injected into synthesis for any matching entity, "
        f"which is easy to miss reading the file top to bottom "
        f"(baseline {DUPLICATE_HEADING_BASELINE}): {dupes}"
    )


def test_every_ruling_reaches_at_least_one_entity():
    sections = load_sources(SOURCES_DIR)
    entities = _bundle_entities()
    names = {slugify(n) for _cid, canonical, aliases in entities for n in [canonical, *aliases] if n}
    ruled = set(_rulings())

    unreached = sorted(
        s.heading for s in sections if s.heading in ruled and not any(_matches(n, s.slug) for n in names)
    )
    assert len(unreached) <= UNREACHED_RULING_BASELINE, (
        f"{len(unreached)} ENTSCHEIDUNG: rulings match zero entities, so "
        f"they never reach synthesis and can never resolve a conflict "
        f"(baseline {UNREACHED_RULING_BASELINE}): {unreached}"
    )


def test_rulings_do_not_ground_more_than_one_person():
    person_dirs = {"characters", "npcs"}
    persons = [(cid, name, aliases) for cid, name, aliases in _bundle_entities() if cid.split("/", 1)[0] in person_dirs]

    sections = load_sources(SOURCES_DIR)
    ruled = set(_rulings())
    ambiguous = {}
    for section in sections:
        if section.heading not in ruled:
            continue
        hits = [
            cid
            for cid, canonical, aliases in persons
            if any(_matches(slugify(n), section.slug) for n in [canonical, *aliases] if n)
        ]
        if len(hits) > 1:
            ambiguous[section.heading] = hits

    assert len(ambiguous) <= AMBIGUOUS_PERSON_RULING_BASELINE, (
        f"{len(ambiguous)} ENTSCHEIDUNG: rulings ground more than one person "
        f"entity, so both receive text meant for only one of them "
        f"(baseline {AMBIGUOUS_PERSON_RULING_BASELINE}): {ambiguous}"
    )
