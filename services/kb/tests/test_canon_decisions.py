"""Every GM ruling in knowledge/sources/*.md must actually reach synthesis.

knowledge/conflicts/README.md documents the intended fix for a genuine canon
question: add an ``ENTSCHEIDUNG:`` paragraph under a ``### <Entity name>``
heading in Kanon_Entscheidungen.md, with an ``<!-- okf: entity=... -->``
directive naming the concept_id(s) it governs, then re-run — synthesis is
supposed to treat that as overriding the session evidence.

PLAN-canon-rulings-routing.md (docs/architecture/) rewrote the routing
mechanism (context.py) and the canon file together: a heading now binds to a
concept_id via an explicit directive, parsed and stripped by
context.load_sources, with the old slug-substring match kept only as the
back-compatible fallback for a heading that carries no directive.

These checks used to be ratchets against a *measured* baseline (the file was
already broken and could only be nudged downward). After the rewrite that
reason is gone: every constant below is a hard 0, not a ceiling — a value
above 0 here means a ruling silently reaches nobody, or reaches more than one
person, or the file regressed to a state the rewrite was meant to fix. See
the plan's "Defect -> test map" for why each one is 0 and not a ratchet.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml
from pnp_okf.context import _matches, load_sources
from pnp_okf.models import (
    ALWAYS_DEEP_TYPES,
    ALWAYS_STANDARD_TYPES,
    DEEP_MENTION_THRESHOLD,
    TYPE_DIR,
)
from pnp_okf.okf import slugify
from pnp_okf.resolve import _load_important

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
SOURCES_DIR = KNOWLEDGE / "sources"
CANON_FILE = SOURCES_DIR / "Kanon_Entscheidungen.md"
REGISTRY_FILE = KNOWLEDGE / "entity_registry.yaml"
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"

pytestmark = pytest.mark.skipif(not CANON_FILE.exists(), reason="no bundle checked out")

_HEADING_RE = re.compile(r"^###[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Must stay 0 — see plan's "Defect -> test map" (#5, duplicate headings
# merged into one prompt). A baseline that can be raised is an invitation to
# raise it; this is a fact about the file, not a ceiling to negotiate.
DUPLICATE_HEADING_BASELINE = 0

# Must stay 0 — see plan's "Defect -> test map" (#2, a ruling that reaches
# nobody can never resolve the conflict it was written for).
UNREACHED_RULING_BASELINE = 0

# Must stay 0 — see plan's "Defect -> test map" (#1, misrouting between
# same-name entities). Only a *fallback*-matched (no directive) section can
# land here; an explicit multi-target directive is a deliberate choice, not
# an accident, and is excluded — see test_rulings_do_not_ground_more_than_one_person.
AMBIGUOUS_PERSON_RULING_BASELINE = 0


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


def _registry_entities() -> list[dict]:
    data = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8")) or {}
    return data.get("entities") or []


def test_no_duplicate_headings():
    # Scoped to headings load_sources() actually turns into a section (i.e.
    # non-empty body) — an empty heading with nothing under it is dead weight
    # in the markdown but not a functional duplicate: it never becomes a
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
        f"(must stay {DUPLICATE_HEADING_BASELINE}): {dupes}"
    )


def _reached(section, live_concept_ids: set[str], names: set[str]) -> bool:
    """Mirrors context._primary_hits' routing: explicit entity= targets only
    when a section carries them (no fallback to slug matching), slug
    matching otherwise."""

    if section.targets:
        return any(t in live_concept_ids for t in section.targets)
    return any(_matches(n, section.slug) for n in names)


def test_every_ruling_reaches_at_least_one_entity():
    sections = load_sources(SOURCES_DIR)
    entities = _bundle_entities()
    concept_ids = {cid for cid, _canonical, _aliases in entities}
    names = {slugify(n) for _cid, canonical, aliases in entities for n in [canonical, *aliases] if n}
    ruled = set(_rulings())

    unreached = sorted(
        s.heading for s in sections
        if s.heading in ruled
        and not _reached(s, concept_ids, names)
        # Same exemption as test_every_ruling_targets_a_live_concept: a
        # directive pointing only at ids that were never extracted is
        # tracked there, by id, and must not be reported twice here.
        and not (s.targets and s.targets <= KNOWN_UNCREATED_TARGETS)
    )
    assert len(unreached) <= UNREACHED_RULING_BASELINE, (
        f"{len(unreached)} ENTSCHEIDUNG: rulings match zero entities, so "
        f"they never reach synthesis and can never resolve a conflict "
        f"(must stay {UNREACHED_RULING_BASELINE}): {unreached}"
    )


def test_rulings_do_not_ground_more_than_one_person():
    person_dirs = {"characters", "npcs"}
    persons = [(cid, name, aliases) for cid, name, aliases in _bundle_entities() if cid.split("/", 1)[0] in person_dirs]

    sections = load_sources(SOURCES_DIR)
    ruled = set(_rulings())
    ambiguous = {}
    for section in sections:
        if section.heading not in ruled or section.targets:
            # An explicit multi-target directive (e.g. "Hans" ->
            # npcs/hans_soldat_aus_breska,npcs/hans_wirt_zum_gruenen_sichelmond)
            # is a deliberate routing choice — both pages are meant to carry
            # the same "these are two different people" ruling. Only the
            # fallback (fuzzy, no directive) path can misroute by accident.
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
        f"(must stay {AMBIGUOUS_PERSON_RULING_BASELINE}): {ambiguous}"
    )


def test_no_superseded_rulings():
    """A superseded ruling must be deleted, not annotated and left beside its
    correction — the model doesn't reliably honor a stated "this one is
    overruled" precedence between two conflicting instructions in the same
    prompt (see the plan's Context section, defect #3)."""

    # Scoped to heading lines and marker lines ("### Dodo (veraltet)",
    # "ENTSCHEIDUNG (überholt):") — a file-wide substring scan also fires on
    # in-world prose, where "die Karte ist veraltet" is a world fact and not
    # a note about the ruling that carries it.
    labels = "\n".join(
        line for line in _canon_text().splitlines()
        if re.match(r"^(###|[A-ZÄÖÜß]{3,}\b)", line.strip())
    )
    bad = [
        term for term in ("überholt", "veraltet", "KORREKTUR")
        if re.search(rf"(?<!\w){term}(?!\w)", labels, re.IGNORECASE)
    ]
    if re.search(r"siehe\b.{0,40}darunter", labels, re.IGNORECASE):
        bad.append("siehe ... darunter")
    assert not bad, (
        f"{CANON_FILE.name} still contains a superseded-ruling marker "
        f"({bad}) — the outdated ENTSCHEIDUNG must be deleted, with its "
        f"correction promoted to stand alone, not left injected alongside it"
    )


def test_only_known_markers():
    """A paragraph opening with an invented ALL-CAPS marker word has no
    prompt support (prompts.py only special-cases ENTSCHEIDUNG: and
    DARSTELLUNG:) and is silently treated as ordinary lore — defect #4."""

    text = _canon_text()
    known = {"ENTSCHEIDUNG", "DARSTELLUNG"}
    bad = sorted({
        m.group(1)
        for m in re.finditer(r"^([A-ZÄÖÜß]{3,})(?:\s*\([^)]*\))?:", text, re.MULTILINE)
        if m.group(1) not in known
    })
    assert not bad, (
        f"{CANON_FILE.name} uses marker word(s) with no prompt support: "
        f"{bad} — prompts.py only special-cases {sorted(known)}, so these "
        f"paragraphs are read as reference lore, not an instruction"
    )


# Directives that deliberately point at a concept_id with no live entity yet
# — the underlying content is real (a soul-fragment god, a second Hag, a
# never-merged NPC), but no session has given it its own extraction, so
# there is nothing in entity_registry.yaml to point at. Each id here is
# either reserved by entity_rules.yaml's never_merge: (npcs/der_jen,
# npcs/kraeuterhexe_von_lady_kalen, npcs/adeliga_vom_haus_des_loewen) or a
# plausible id following the type-dir convention (npcs/die_prinzessin,
# deities/sythraal, deities/ezhura) — see PLAN-canon-rulings-routing.md,
# Context section, "genuinely dead". Not a ratchet: an id leaves this set
# only when a human confirms the entity now exists (or the ruling is
# deleted) — never by loosening the check below to tolerate more misses.
KNOWN_UNCREATED_TARGETS = {
    "npcs/die_prinzessin",
    "npcs/der_jen",
    "deities/sythraal",
    "deities/ezhura",
    "npcs/adeliga_vom_haus_des_loewen",
    "npcs/kraeuterhexe_von_lady_kalen",
}


def test_every_ruling_targets_a_live_concept():
    """A rename that leaves a directive pointing at a dead concept_id must
    fail loudly, not just silently stop grounding anyone — defect #2, the
    plan's highest-priority case after the leaked directive itself. Exempt:
    KNOWN_UNCREATED_TARGETS — ids never extracted at all, not a rename."""

    sections = load_sources(SOURCES_DIR)
    live_ids = {str(e.get("concept_id", "")).strip() for e in _registry_entities()}

    problems = [
        f"{s.heading}: {target} does not exist in entity_registry.yaml"
        for s in sections
        for target in sorted(s.targets)
        if target not in live_ids and target not in KNOWN_UNCREATED_TARGETS
    ]
    assert not problems, (
        f"directive(s) in {CANON_FILE.name} target a concept_id that isn't "
        f"live and isn't in KNOWN_UNCREATED_TARGETS (likely a rename that "
        f"left the directive stale): {problems}"
    )


def test_ruling_targets_are_not_brief_tier():
    """A ruling written for an entity that never clears the brief tier is a
    guaranteed no-op — cli.py returns render_brief_body() before synthesis
    is ever reached, so sources_for()/secondary_sources_for() are never
    called for it. The fix is `important: true` in entity_rules.yaml —
    defect #10."""

    # `important` comes from _load_important, not from the entities[] flag:
    # that is what resolve_entities() itself calls, so a pin added to
    # entity_rules.yaml counts immediately, without waiting for the run that
    # bakes it into the generated registry.
    important = _load_important(REGISTRY_FILE)
    mention_count = {}
    etype_by_id = {}
    for e in _registry_entities():
        cid = str(e.get("concept_id", "")).strip()
        mention_count[cid] = int(e.get("mention_count") or 0)
        etype_by_id[cid] = str(e.get("type") or "")

    def _tier(cid: str) -> str:
        n = mention_count.get(cid, 0)
        etype = etype_by_id.get(cid, "")
        if cid in important or n >= DEEP_MENTION_THRESHOLD:
            return "deep"
        if etype in {t.value for t in ALWAYS_DEEP_TYPES} and n >= 2:
            return "deep"
        if n >= 2 or etype in {t.value for t in ALWAYS_DEEP_TYPES | ALWAYS_STANDARD_TYPES}:
            return "standard"
        return "brief"

    sections = load_sources(SOURCES_DIR)
    ruled = set(_rulings())
    briefs = sorted({
        (s.heading, target)
        for s in sections
        if s.heading in ruled
        for target in s.targets
        if target in mention_count and _tier(target) == "brief"
    })
    assert not briefs, (
        f"ruling(s) target an entity that never clears the brief tier, so "
        f"they never reach synthesis (cli.py renders brief entries locally, "
        f"no LLM call): {briefs} — fix with `important: true` in "
        f"entity_rules.yaml for the target concept"
    )


# Sections that reach nobody on purpose, each for a reason a human checked.
# Like KNOWN_UNCREATED_TARGETS this is not a ratchet: an entry leaves it when
# the underlying question is answered, never by adding a new one to quiet a
# failure.
#
# "Blutschalen-Statuen" is a DARSTELLUNG: ruling about how cautiously to
# describe any statue holding a blood bowl. Every statue concept in the
# registry sits at exactly one mention, i.e. the brief tier, which never
# reaches synthesis at all — so no target exists that would make the ruling
# fire. It needs a GM decision (`important: true` on the statue the ruling is
# really about), not a directive.
KNOWN_UNROUTABLE_SECTIONS = {
    "Blutschalen-Statuen",
    # 2026-09-05 v6 identity cleanup: "Nicht in dieser Schrift verzeichnet"
    # (Bekannte_Pantheon_der_Goetter.md) is a bookkeeping note, not a ruling
    # about one entity -- it names deities that appear in sessions but have
    # no pantheon-list entry (Kol Meref, Nerash, Korn, all already linked
    # inline in its own body) plus the genuinely-uncreated ones tracked in
    # KNOWN_UNCREATED_TARGETS. No single concept_id fits a directive; the
    # heading text itself is prose, not an entity name, so the fallback
    # slug match can never fire either.
    "Nicht in dieser Schrift verzeichnet",
}


def test_no_source_section_reaches_nobody():
    """A section matching no entity is never injected anywhere.

    test_every_ruling_reaches_at_least_one_entity is scoped to `_rulings()` —
    headings whose body contains ENTSCHEIDUNG: — which left two blind spots a
    2026-09 audit found the hard way: a DARSTELLUNG:-only ruling was never
    examined, and reference lore in the other source files was not examined at
    all. 70 of 137 sections (~60% of the folder by size) reached nobody, among
    them every word of the harvested wiki prose about the four player
    characters.

    Hard 0, matching this module's other baselines. Prose with no entity to
    attach to does not belong in sources/ — knowledge/narrative/ is where
    uncitable material lives.
    """

    sections = load_sources(SOURCES_DIR)
    entities = _bundle_entities()
    concept_ids = {cid for cid, _canonical, _aliases in entities}
    names = {slugify(n) for _cid, canonical, aliases in entities for n in [canonical, *aliases] if n}

    dead = sorted(
        f"{s.origin} :: {s.heading}" for s in sections
        if not _reached(s, concept_ids, names)
        and s.heading not in KNOWN_UNROUTABLE_SECTIONS
        and not (s.targets and s.targets <= KNOWN_UNCREATED_TARGETS)
    )
    assert not dead, (
        f"{len(dead)} source section(s) match zero entities, so synthesis "
        f"never sees them — add an `<!-- okf: entity=... -->` directive, or "
        f"move the text to knowledge/narrative/ if it has no entity: {dead}"
    )


def test_harvested_wiki_sections_are_directive_routed():
    """Harvested wiki prose must never route on a name collision.

    services/kb/sync_harvest.py recovers the concept_id from the harvest
    filename and writes it out as an explicit directive. Doing that step by
    hand is what broke before: four harvest files were concatenated under
    plain "## <name>" headings, and an ## heading whose body is empty (a ###
    follows it directly) is dropped by load_sources, orphaning every
    subsection under a generic slug like "uberblick". All four player
    characters lost their grounding silently.
    """

    live_ids = {str(e.get("concept_id", "")).strip() for e in _registry_entities()}
    wiki_dir = SOURCES_DIR / "wiki"
    sections = [s for s in load_sources(SOURCES_DIR) if (wiki_dir / s.origin).exists()]
    assert sections, "no harvested wiki sections found — run sync_harvest.py"

    problems = sorted(
        f"{s.origin} :: {s.heading} -> {sorted(s.targets) or 'no directive'}"
        for s in sections
        if not s.targets or not (s.targets <= live_ids)
    )
    assert not problems, (
        f"harvested wiki section(s) carry no usable okf directive, so they "
        f"fall back to name matching: {problems} — re-run sync_harvest.py"
    )
