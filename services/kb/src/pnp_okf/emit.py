from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from pnp_okf.links import ConceptIndex, normalize_body
from pnp_okf.models import (
    DIR_TO_TYPE,
    SUBTYPES,
    TYPE_DIR,
    CanonicalEntity,
    EntityType,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.okf import render_document, slugify, write_concept, write_index

log = logging.getLogger(__name__)


def _session_concept_id(transcript: SessionTranscript) -> str:
    date = transcript.date or transcript.session_id[:10]
    return f"sessions/{date}"


def build_concept_index(
    entities: list[CanonicalEntity],
    transcripts: dict[str, SessionTranscript],
) -> ConceptIndex:
    """Build a :class:`ConceptIndex` covering all entity and session concepts."""

    concept_ids = [e.concept_id for e in entities]
    concept_ids += [_session_concept_id(t) for t in transcripts.values()]
    return ConceptIndex(concept_ids)


_TYPE_LABEL_DE = {
    EntityType.CHARACTER: "Charaktere",
    EntityType.NPC: "NPCs",
    EntityType.LOCATION: "Orte",
    EntityType.FACTION: "Fraktionen",
    EntityType.ITEM: "Gegenstände",
    EntityType.EVENT: "Ereignisse",
    EntityType.DEITY: "Götter",
    EntityType.DOMAIN: "Reiche",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _short_desc(text: str, limit: int = 140) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1].rstrip() + "…"


# --- session concepts -------------------------------------------------------


def emit_sessions(
    bundle_dir: Path,
    transcripts: dict[str, SessionTranscript],
    extractions: dict[str, SessionExtraction],
    index: ConceptIndex | None = None,
) -> list[tuple[str, str, str]]:
    """Write one ``sessions/<date>.md`` concept per session.

    When ``index`` is given, cross-links inside the recap are normalized
    against the concept set. Returns index entries ``(title, url, description)``.
    """

    entries: list[tuple[str, str, str]] = []
    for session_id in sorted(transcripts):
        transcript = transcripts[session_id]
        extraction = extractions[session_id]
        date = transcript.date or session_id[:10]
        concept_id = f"sessions/{date}"
        title = f"Session {date}"

        intro_lines: list[str] = []
        for mention in extraction.entities:
            slug = slugify(mention.name)
            path = f"{TYPE_DIR[mention.type]}/{slug}"
            intro_lines.append(
                f"* [{mention.name}](/{path}.md) — {mention.note} [{mention.citation_ts}]"
            )

        body_parts = [
            "# Zusammenfassung",
            "",
            extraction.recap.strip(),
        ]
        if intro_lines:
            body_parts += ["", "# Auftretende Entitäten", "", *intro_lines]
        body_parts += [
            "",
            "# Belege",
            "",
            f"[1] [Vollständige Session (VOD)]({transcript.url})",
        ]

        body = "\n".join(body_parts)
        if index is not None:
            body, unresolved = normalize_body(body, index)
            if unresolved:
                log.debug(
                    "[emit] %s: dropped %d unresolved link(s): %s",
                    concept_id,
                    len(unresolved),
                    ", ".join(sorted(set(unresolved))),
                )

        frontmatter = {
            "type": "Session",
            "title": transcript.title or title,
            "description": _short_desc(extraction.recap),
            "resource": transcript.url,
            "tags": ["session", date],
            "timestamp": f"{date}T00:00:00Z" if date else _now_iso(),
            "quality": transcript.quality,
            "unsicher_ratio": round(transcript.unsicher_ratio, 3),
        }
        write_concept(bundle_dir, concept_id, frontmatter, body)
        entries.append(
            (title, f"{date}.md", _short_desc(extraction.recap, 100))
        )
    return entries


# --- entity concepts --------------------------------------------------------


_CONFLICT_HEADING = "# Offene Konflikte"


def split_conflicts(body: str) -> tuple[str, str | None]:
    """Return ``(body, conflict_section)``.

    The synthesis prompt appends unresolvable contradictions under a trailing
    ``# Offene Konflikte`` heading. The section stays in the concept body
    (readers should see a fact is disputed) and is *also* returned so the
    caller can queue it under ``conflicts/`` for human resolution.
    """

    idx = body.find(_CONFLICT_HEADING)
    if idx < 0:
        return body, None
    section = body[idx + len(_CONFLICT_HEADING):].strip()
    return body, section or None


def emit_entity(
    bundle_dir: Path,
    entity: CanonicalEntity,
    body: str,
    index: ConceptIndex | None = None,
) -> tuple[list[str], str | None]:
    """Write a single canonical-entity concept document.

    When ``index`` is given, cross-links in ``body`` are normalized against
    the concept set. Returns ``(unresolved_link_targets, conflict_section)``
    — the latter is the ``# Offene Konflikte`` content when the synthesis
    flagged an unresolvable contradiction, else ``None``.
    """

    unresolved: list[str] = []
    if index is not None:
        body, unresolved = normalize_body(body, index)
    body, conflicts = split_conflicts(body)

    first = entity.mentions[0] if entity.mentions else None
    last = entity.mentions[-1] if entity.mentions else None
    description = _short_desc(first.note) if first else entity.canonical_name
    frontmatter = {
        "type": entity.type.value,
        "id": entity.entity_id,
        "title": entity.canonical_name,
        "description": description,
        "tags": [TYPE_DIR[entity.type]],
        **({"subtype": entity.subtype} if entity.subtype else {}),
        "timestamp": f"{last.date}T00:00:00Z" if last and last.date else _now_iso(),
    }
    if entity.aliases:
        frontmatter["aliases"] = entity.aliases
    if conflicts:
        frontmatter["status"] = "disputed"
    write_concept(bundle_dir, entity.concept_id, frontmatter, body)
    return unresolved, conflicts


def emit_conflict(
    conflicts_dir: Path, entity: CanonicalEntity, section: str
) -> Path:
    """Write one open-conflict file for human resolution.

    Lives outside the bundle (``knowledge/conflicts/``) so the queue is
    reviewable and resolvable independently of concept content.

    Resolving one means editing an *input*, never the concept file — the
    bundle is generated and every run overwrites it, so a note written there
    is lost:

    * two things wrongly treated as one (or vice versa) -> fix the merge or
      alias in ``entity_registry.yaml``;
    * a genuine canon call only the GM can make -> record it under an
      ``ENTSCHEIDUNG:`` heading in ``knowledge/sources/``, which synthesis
      treats as overriding the session evidence.

    Then re-run and delete this file.
    """

    conflicts_dir.mkdir(parents=True, exist_ok=True)
    slug = entity.concept_id.replace("/", "__")
    path = conflicts_dir / f"{slug}.md"
    doc = render_document(
        {
            "type": "Conflict",
            "id": f"CONFLICT_{entity.entity_id}",
            "title": f"Offener Konflikt: {entity.canonical_name}",
            "description": "Widersprüchliche Belege — menschliche Entscheidung nötig.",
            "status": "open",
            "concept": entity.concept_id,
            "timestamp": _now_iso(),
        },
        f"Betrifft: `{entity.concept_id}` ({entity.entity_id})\n\n"
        f"{_CONFLICT_HEADING}\n\n{section}\n",
    )
    path.write_text(doc, encoding="utf-8")
    return path


# --- indexes and log --------------------------------------------------------


def prune_conflicts(conflicts_dir: Path, still_open: set[str]) -> int:
    """Delete queued conflicts that the latest run no longer reports.

    Without this the queue only ever grows: a conflict resolved via a
    registry fix or a GM ruling keeps its file forever, so the reviewer
    cannot tell the outstanding ones from the settled ones.

    Only files carrying ``type: Conflict`` are considered, so anything else
    kept alongside them (e.g. a ``merge_proposals.md`` report) is untouched.
    """

    if not conflicts_dir.is_dir():
        return 0
    expected = {f"{cid.replace('/', '__')}.md" for cid in still_open}
    removed = 0
    for path in sorted(conflicts_dir.glob("*.md")):
        if path.name in expected:
            continue
        head = path.read_text(encoding="utf-8")[:400]
        if "type: Conflict" not in head:
            continue
        path.unlink()
        log.info("[emit] conflict resolved, removed from queue: %s", path.name)
        removed += 1
    return removed


def prune_orphans(
    bundle_dir: Path, entities: list[CanonicalEntity]
) -> int:
    """Delete concept files whose entity no longer exists. Returns the count.

    Emit only ever writes; a concept that gets merged away or renamed leaves
    its old file behind for good. Those stale files keep their outdated body
    and links, show up as duplicate titles in validation, and — worse — are
    still served by the read-only API and exported to the wiki as if current.

    Only entity concepts are considered: ``sessions/``, the per-directory
    ``index.md`` files and ``log.md`` are emitted separately and never orphan.
    """

    live = {f"{e.concept_id}.md" for e in entities}
    entity_dirs = set(TYPE_DIR.values())
    removed = 0
    for directory in entity_dirs:
        d = bundle_dir / directory
        if not d.is_dir():
            continue
        for path in d.glob("*.md"):
            if path.name == "index.md":
                continue
            rel = f"{directory}/{path.name}"
            if rel not in live:
                path.unlink()
                log.info("[emit] pruned orphaned concept: %s", rel)
                removed += 1
        # A directory can empty out entirely (e.g. a type that lost all its
        # members); leave it in place only if it still holds something.
        if not any(d.iterdir()):
            d.rmdir()
    return removed


def emit_indexes(
    bundle_dir: Path,
    entities: list[CanonicalEntity],
    session_entries: list[tuple[str, str, str]],
) -> None:
    """Write per-directory ``index.md`` files and the bundle-root index."""

    # Group entities by type/dir.
    by_dir: dict[str, list[CanonicalEntity]] = {}
    for entity in entities:
        by_dir.setdefault(TYPE_DIR[entity.type], []).append(entity)

    # sessions/index.md
    if session_entries:
        write_index(
            bundle_dir / "sessions",
            [("Sessions", sorted(session_entries, key=lambda e: e[1]))],
        )

    # per-type index.md, grouped by subtype where the type has one.
    #
    # This is what replaces "collection" concepts: a page listing every ring
    # would be a node with no referent, and in a property graph it would link
    # unrelated items and invent paths between them. A grouping is a *view* —
    # here a heading, later a query over the subtype label.
    for directory, group in by_dir.items():
        def _entry(e: CanonicalEntity) -> tuple[str, str, str]:
            return (
                e.canonical_name,
                f"{e.concept_id.split('/', 1)[1]}.md",
                _short_desc(e.mentions[0].note) if e.mentions else "",
            )

        ordered = sorted(group, key=lambda e: e.canonical_name.lower())
        etype = DIR_TO_TYPE.get(directory)
        vocabulary = SUBTYPES.get(etype) if etype else None

        if vocabulary and any(e.subtype for e in ordered):
            sections: list[tuple[str, list[tuple[str, str, str]]]] = []
            for label in vocabulary:
                members = [e for e in ordered if e.subtype == label]
                if members:
                    sections.append((label, [_entry(e) for e in members]))
            rest = [e for e in ordered if e.subtype not in vocabulary]
            if rest:
                sections.append(("Ohne Kategorie", [_entry(e) for e in rest]))
            # Keep the type name as the page's first heading.
            sections.insert(0, (_type_heading(directory), []))
            write_index(bundle_dir / directory, sections, sub_level=2)
        else:
            write_index(
                bundle_dir / directory,
                [(_type_heading(directory), [_entry(e) for e in ordered])],
            )

    # root index.md
    root_sections: list[tuple[str, list[tuple[str, str, str]]]] = []
    if session_entries:
        root_sections.append(
            ("Sessions", [("Alle Sessions", "sessions/", "Chronologische Recaps")])
        )
    catalog: list[tuple[str, str, str]] = []
    for directory in sorted(by_dir):
        catalog.append((_type_heading(directory), f"{directory}/", ""))
    if catalog:
        root_sections.append(("Kompendium", catalog))
    write_index(bundle_dir, root_sections)


def _type_heading(directory: str) -> str:
    for etype, d in TYPE_DIR.items():
        if d == directory:
            return _TYPE_LABEL_DE[etype]
    return directory.capitalize()


def emit_log(
    bundle_dir: Path, transcripts: dict[str, SessionTranscript]
) -> None:
    """Write a newest-first ``log.md`` from session dates."""

    lines = ["# Update Log", ""]
    for session_id in sorted(transcripts, reverse=True):
        transcript = transcripts[session_id]
        date = transcript.date or session_id[:10]
        lines.append(f"## {date}")
        lines.append(
            f"* **Session**: [{transcript.title or 'Session'}](/sessions/{date}.md)"
        )
        lines.append("")
    (bundle_dir / "log.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
