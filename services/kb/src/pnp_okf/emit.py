from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from pnp_okf.links import ConceptIndex, normalize_body
from pnp_okf.models import (
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
    reviewable and resolvable independently of concept content. Resolution =
    fix the concept (or a registry/alias error), then delete this file.
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

    # per-type index.md (url is the concept id relative to its directory)
    for directory, group in by_dir.items():
        entries = [
            (
                e.canonical_name,
                f"{e.concept_id.split('/', 1)[1]}.md",
                _short_desc(e.mentions[0].note) if e.mentions else "",
            )
            for e in sorted(group, key=lambda e: e.canonical_name.lower())
        ]
        heading = _type_heading(directory)
        write_index(bundle_dir / directory, [(heading, entries)])

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
