"""Extra grounding handed to synthesis on top of the per-mention notes.

The notes are a lossy compression of a session, and some campaign knowledge
never appears in a transcript at all. Two supplements close those gaps:

* **Source material** (``knowledge/sources/``) — rulebooks, the pantheon
  scripture, campaign handouts. The bundle is *generated*, so hand-written
  prose added directly to a concept file is overwritten on the next run;
  keeping that material in ``sources/`` and re-injecting it here survives
  every regeneration. The same mechanism carries imported wiki prose later.
* **Transcript windows** — for deep-tier entities we go back to the original
  dialogue around each citation, so the entry can carry concrete detail and
  the occasional verbatim quote instead of only re-phrased notes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pnp_okf.models import CanonicalEntity, SessionTranscript
from pnp_okf.okf import slugify
from pnp_okf.synthesize import _render_mentions

log = logging.getLogger(__name__)

# Seconds of dialogue to pull either side of a citation timestamp.
EXCERPT_WINDOW_S = 90.0

# Upper bound on the transcript dialogue handed to one synthesis call.
EXCERPT_BUDGET_CHARS = 60_000

# Upper bound on the source material (primary + I-002 secondary, each) handed
# to one synthesis call. Sections beyond this are dropped, longest-match-first
# for secondary — see secondary_sources_for.
SOURCE_BUDGET_CHARS = 20_000

# How many I-002 secondary sections one entity may carry. Caps per-entity
# prompt size regardless of how many other rulings its mentions happen to cite.
MAX_SECONDARY_SECTIONS = 6

# The only two paragraph markers prompts.py special-cases (SYNTH_SOURCES_TEMPLATE).
# A section opening with neither is ordinary reference lore. Also the gate for
# I-002 secondary attachment — see secondary_sources_for.
RULING_MARKERS = ("ENTSCHEIDUNG:", "DARSTELLUNG:")

# Section headings that are never grounding, dropped at load. "Belege" is a
# bundle artefact: harvested wiki prose brings its own numbered evidence list,
# and in a synthesis prompt "[n]" means the nth mention of *this* entity.
_SKIP_SLUGS = frozenset({"belege"})

# Files in sources/ that document the folder rather than feed it. Without this
# a README is ingested like any other source: its headings become sections
# that ground nobody, and an `<!-- okf: ... -->` shown as an *example* parses
# as a real directive pointing at a concept that does not exist.
_SKIP_STEMS = frozenset({"readme"})

# Bare numeric citation markers carried in from harvested wiki prose. They
# collide with the prompt's own "[n]" evidence numbering, and
# episodes.relabel_citations then rewrites a copied number into a confidently
# wrong episode label — so they are stripped before a source reaches a prompt.
_STRAY_CITE_RE = re.compile(r"[ \t]*\[\d+\]")

_HEADING_RE = re.compile(r"^(#{2,4})[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# A directive line under a heading: <!-- okf: entity=a,b; mentions=off -->.
# Parsed and stripped by load_sources so it never reaches a prompt.
_DIRECTIVE_RE = re.compile(r"<!--\s*okf:\s*(.*?)\s*-->", re.DOTALL)

# Heading text minus a trailing disambiguating parenthetical, e.g.
# "Harald (Freibeuter)" -> "Harald". Used only for I-002's mention-text scan.
_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")


class SourceSection:
    """One heading-delimited section of a file in ``knowledge/sources/``.

    ``heading`` is the section's *own* heading text; ``slug`` folds in the
    enclosing headings as well. The two differ on purpose — see load_sources.
    """

    __slots__ = ("origin", "heading", "slug", "text", "targets", "mentions_ok")

    def __init__(
        self,
        origin: str,
        heading: str,
        text: str,
        *,
        slug: str | None = None,
        targets: frozenset[str] = frozenset(),
        mentions_ok: bool = True,
    ) -> None:
        self.origin = origin
        self.heading = heading
        self.slug = slug or slugify(heading)
        self.text = text
        self.targets = targets
        self.mentions_ok = mentions_ok

    def is_ruling(self) -> bool:
        """Does this section state a GM ruling rather than reference lore?"""

        return self.text.lstrip().startswith(RULING_MARKERS)


def _parse_directive(body: str, origin: str, heading: str) -> tuple[str, frozenset[str], bool]:
    """Extract and strip an ``<!-- okf: ... -->`` directive from a section body.

    Returns the body with the directive removed, the explicit routing
    targets (empty if none/absent — the caller then falls back to slug
    matching), and whether I-002 secondary attachment is allowed.
    """

    m = _DIRECTIVE_RE.search(body)
    if not m:
        return body, frozenset(), True
    # Strip *every* directive in the section, not only the one parsed: a
    # second one further down (a pasted template, a stray comment) would
    # otherwise survive verbatim into the prompt.
    body = _DIRECTIVE_RE.sub("", body).strip()
    targets: frozenset[str] = frozenset()
    mentions_ok = True
    for pair in m.group(1).split(";"):
        pair = pair.strip()
        if not pair:
            continue
        key, _, value = pair.partition("=")
        key, value = key.strip(), value.strip()
        if key == "entity":
            targets = frozenset(v.strip() for v in value.split(",") if v.strip())
        elif key == "mentions":
            mentions_ok = value.lower() != "off"
        else:
            log.warning(
                "[context] unknown okf directive key %r in %s (%s) — ignored",
                key, origin, heading,
            )
    return body, targets, mentions_ok


def load_sources(sources_dir: Path) -> list[SourceSection]:
    """Parse every markdown file under ``sources_dir`` into headed sections.

    Headings nest. A file that names an entity once and then subdivides it —

        ## Kaya
        ### Überblick
        ### Chronologie

    — used to lose the entity entirely: the levels were treated as peers, so
    "## Kaya" (no body of its own, a "###" follows immediately) was dropped as
    empty and its children became free-floating sections slugged ``uberblick``
    and ``chronologie``, matching nobody. That is the shape harvested wiki
    prose arrives in, so the whole of it reached zero entities.

    Each section therefore carries two names. ``slug`` folds in the enclosing
    headings (``kaya_uberblick``), which is what _matches routes on — the
    entity name "kaya" is a substring of it. ``heading`` stays the section's
    own text, because secondary_sources_for searches mention prose for it as
    a literal name and _render_hits prints it; a folded heading would match
    no mention and read badly in the prompt.

    A directive inherits the same way: "## Kaya"'s ``entity=`` governs every
    subsection under it, and a subsection carrying its own overrides it.
    """

    if not sources_dir.is_dir():
        return []
    sections: list[SourceSection] = []
    for path in sorted(sources_dir.rglob("*.md")):
        if path.stem.lower() in _SKIP_STEMS:
            continue
        content = path.read_text(encoding="utf-8")
        matches = list(_HEADING_RE.finditer(content))
        # Enclosing headings still open at this point: level -> (slug, targets).
        open_headings: dict[int, tuple[str, frozenset[str]]] = {}
        for i, m in enumerate(matches):
            level, heading = len(m.group(1)), m.group(2)
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[m.end():end].strip()
            body, targets, mentions_ok = _parse_directive(body, path.name, heading)

            for closed in [lv for lv in open_headings if lv >= level]:
                del open_headings[closed]
            if not targets:
                for lv in sorted(open_headings, reverse=True):
                    if open_headings[lv][1]:
                        targets = open_headings[lv][1]
                        break
            slug = "_".join(
                [open_headings[lv][0] for lv in sorted(open_headings)] + [slugify(heading)]
            )
            open_headings[level] = (slugify(heading), targets)

            if body and slugify(heading) not in _SKIP_SLUGS:
                sections.append(SourceSection(
                    path.name, heading, body,
                    slug=slug, targets=targets, mentions_ok=mentions_ok,
                ))
    log.info("[context] loaded %d source sections from %s", len(sections), sources_dir)
    return sections


def _matches(name: str, slug: str) -> bool:
    """Does a name (already slugified) name this source-section slug?

    Names of 4+ characters use substring containment either way, so a
    genitive heading like "Dodos heiliger Streitkolben" (slug
    ``dodos_heiliger_streitkolben``) still matches the entity "Dodo".

    Shorter names (``len < 4``) used to be dropped outright, on the theory
    that a short fragment risks matching unrelated headings by accident. That
    filter had a worse cost than the risk it guarded against: it made an
    ``ENTSCHEIDUNG:`` ruling for any entity named "Nox" or "Jen" permanently
    unreachable by synthesis, so the conflict it was meant to settle could
    never actually resolve. A short name is instead required to match one
    whole ``_``-delimited token of the slug — "nox" must equal a token, not
    just appear inside one — which keeps the guard without the blind spot.
    """

    if len(name) >= 4:
        return name in slug or slug in name
    return name in slug.split("_")


def _truncate(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    head = text[:budget].rsplit("\n\n", 1)[0]
    return head + "\n\n[… gekürzt …]"


def _render_hits(hits: list[SourceSection]) -> str:
    text = "\n\n".join(f"### {s.heading}  (aus {s.origin})\n{s.text}" for s in hits)
    return _truncate(_STRAY_CITE_RE.sub("", text), SOURCE_BUDGET_CHARS)


def _primary_hits(entity: CanonicalEntity, sections: list[SourceSection]) -> list[SourceSection]:
    """Sections that ground this entity: explicit ``entity=`` routing when a
    section carries one, slug matching as the back-compatible fallback when
    it doesn't. Explicit beats fuzzy — a directive section never also falls
    back to slug matching, even if the slugs happen to line up too.
    """

    names = {slugify(n) for n in [entity.canonical_name, *entity.aliases] if n}
    hits = []
    for s in sections:
        if s.targets:
            if entity.concept_id in s.targets:
                hits.append(s)
        elif names and any(_matches(n, s.slug) for n in names):
            hits.append(s)
    return hits


def sources_for(entity: CanonicalEntity, sections: list[SourceSection]) -> str:
    """Source sections that ground this entity, as markdown.

    Fallback matching is on slugs so punctuation drift between a transcript
    spelling and the written lore ("Vhar'Zul" vs "Vhar Zul") still lines up;
    a section with an explicit ``<!-- okf: entity=... -->`` directive instead
    matches only the concept id(s) it names.
    """

    if not sections:
        return ""
    hits = _primary_hits(entity, sections)
    if not hits:
        return ""
    return _render_hits(hits)


def secondary_sources_for(
    entity: CanonicalEntity, sections: list[SourceSection]
) -> str:
    """Rulings that concern OTHER entities this entity's own mentions cite.

    I-002: a ruling about Nyruk should also reach Nyrella's entry, since her
    mentions are exactly where the settled Nyruk/Nairuk spelling contradiction
    re-derives itself from the transcripts. Kept in its own prompt block
    (SYNTH_SECONDARY_TEMPLATE), never merged into ``primary`` — pasting a
    ruling about a different entity into the same block as this entity's own
    sources invites the model to write a paragraph about *that* entity here.

    Only a *ruling* attaches here, which is what SYNTH_SECONDARY_TEMPLATE
    already tells the model this block contains ("Festlegungen zu ANDEREN
    Entitäten"). Reference lore is not a Festlegung, and without the gate a
    generic subheading behaved like one: "Fähigkeiten" (a character's ability
    list) matched that word in 27 entities' mention notes, and since ranking
    is by name length it outranked the real rulings "Dodo", "Slix" and "Nox",
    taking their slots under a banner claiming it stated facts about them.

    A section opts out with ``mentions=off`` (rulings only meaningful inside
    their own entry); one already primary for this entity is never repeated
    as secondary. Ranked by longest matched name, capped to
    MAX_SECONDARY_SECTIONS.

    The "already primary" test runs against the primary *hits*, not the
    rendered primary block: a heading is a prefix of another heading often
    enough ("Dodo" inside "Dodos heiliger Streitkolben") that a substring
    test drops a genuinely different ruling, and a section that only fell
    off the end of the primary budget would otherwise re-appear here under
    the "this is about ANOTHER entity" banner.
    """

    if not sections:
        return ""
    mention_text = _render_mentions(entity)
    if not mention_text:
        return ""

    primary_hits = _primary_hits(entity, sections)
    ranked: list[tuple[int, SourceSection]] = []
    for s in sections:
        if not s.mentions_ok or s in primary_hits or not s.is_ruling():
            continue
        name = _PAREN_RE.sub("", s.heading).strip()
        if not name:
            continue
        if not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", mention_text, re.IGNORECASE):
            continue
        ranked.append((len(name), s))

    if not ranked:
        return ""
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    hits = [s for _len, s in ranked[:MAX_SECONDARY_SECTIONS]]
    return _render_hits(hits)


def _parse_ts(ts: str) -> float | None:
    parts = (ts or "").strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        h, m, s = nums
    elif len(nums) == 2:
        h, m, s = 0, nums[0], nums[1]
    else:
        return None
    return h * 3600 + m * 60 + s


def _merge_windows(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Collapse overlapping ``(start, end)`` spans so dialogue isn't repeated."""

    merged: list[tuple[float, float]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def excerpts_for(
    entity: CanonicalEntity,
    transcripts: dict[str, SessionTranscript],
    *,
    window_s: float = EXCERPT_WINDOW_S,
    budget_chars: int = EXCERPT_BUDGET_CHARS,
) -> str:
    """Original dialogue around each of this entity's citations.

    The per-session budget is divided evenly rather than filled first-come:
    a character appearing in 38 sessions needs coverage *across* the campaign
    for its chronology section, so every session keeps a slice instead of the
    earliest ones consuming the whole budget.
    """

    by_session: dict[str, list[tuple[float, float]]] = {}
    for m in entity.mentions:
        t = _parse_ts(m.citation_ts)
        if t is None or m.session_id not in transcripts:
            continue
        by_session.setdefault(m.session_id, []).append(
            (max(0.0, t - window_s), t + window_s)
        )
    if not by_session:
        return ""

    per_session = max(600, budget_chars // len(by_session))
    blocks: list[str] = []
    for session_id in sorted(by_session):
        transcript = transcripts[session_id]
        spans = _merge_windows(by_session[session_id])
        lines = [
            f"[{seg.timestamp}] {seg.speaker}: {seg.text.strip()}"
            for seg in transcript.segments
            if seg.text.strip()
            and any(start <= seg.start <= end for start, end in spans)
        ]
        if not lines:
            continue
        body = "\n".join(lines)
        if len(body) > per_session:
            body = body[:per_session].rsplit("\n", 1)[0] + "\n[… gekürzt …]"
        blocks.append(f"--- Session {transcript.date} ---\n{body}")

    return "\n\n".join(blocks)
