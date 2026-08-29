"""Minimal, self-contained Open Knowledge Format (OKF) writer.

Emits concept documents and ``index.md`` files that conform to okf/SPEC.md
v0.1. The output bundle is data-compatible with the ``okf`` reference
package, so its ``visualize`` CLI can render ``viz.html`` directly.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Frontmatter key order preferred by the OKF spec (type is required first).
_FRONTMATTER_ORDER = ["type", "title", "description", "resource", "tags", "timestamp"]


def slugify(value: str) -> str:
    """Turn a display name into a filesystem/concept-id-safe slug.

    Transliterates German umlauts (ä->ae, ö->oe, ü->ue, ß->ss) before
    stripping remaining non-alphanumerics.
    """

    lowered = value.strip().lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        lowered = lowered.replace(src, dst)
    normalized = unicodedata.normalize("NFKD", lowered)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("_", ascii_only).strip("_")
    return slug or "unnamed"


def _order_frontmatter(frontmatter: dict[str, object]) -> dict[str, object]:
    ordered: dict[str, object] = {}
    for key in _FRONTMATTER_ORDER:
        if key in frontmatter and frontmatter[key] not in (None, ""):
            ordered[key] = frontmatter[key]
    for key, value in frontmatter.items():
        if key not in ordered and value not in (None, ""):
            ordered[key] = value
    return ordered


def render_document(frontmatter: dict[str, object], body: str) -> str:
    """Serialize a concept document: YAML frontmatter block + markdown body."""

    if not frontmatter.get("type"):
        raise ValueError("OKF concept documents require a non-empty 'type'.")
    fm = _order_frontmatter(frontmatter)
    yaml_block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    return f"---\n{yaml_block}\n---\n\n{body.strip()}\n"


def write_if_changed(path: Path, content: str) -> bool:
    """Write ``content`` to ``path`` only if it differs. Returns whether it wrote.

    A run that touches nothing still overwrites every file with byte-identical
    content, which erases mtimes as a signal of what a run actually changed
    and makes an accidental mass-rewrite indistinguishable from a real one in
    ``git status``. Skipping identical writes makes both observable again.
    """

    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def write_concept(
    bundle_dir: Path, concept_id: str, frontmatter: dict[str, object], body: str
) -> Path:
    """Write ``<bundle_dir>/<concept_id>.md`` (skipping an unchanged write) and return its path."""

    path = bundle_dir / f"{concept_id}.md"
    write_if_changed(path, render_document(frontmatter, body))
    return path


def split_document(text: str) -> tuple[dict, str]:
    """Inverse of :func:`render_document`: ``(frontmatter, body)``.

    Tolerant by design — a concept file with no or broken frontmatter comes
    back as ``({}, text)`` rather than raising, so one bad file cannot stop a
    read over the whole bundle.
    """

    if not text.startswith("---"):
        return {}, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}, parts[2]
    return (fm if isinstance(fm, dict) else {}), parts[2].strip()


def link(concept_id: str, title: str) -> str:
    """Bundle-relative markdown link to another concept (SPEC 5.1)."""

    return f"[{title}](/{concept_id}.md)"


def write_index(
    directory: Path,
    sections: list[tuple[str, list[tuple[str, str, str]]]],
    *,
    sub_level: int | None = None,
) -> Path:
    """Write an ``index.md`` (no frontmatter) with grouped bullet lists.

    ``sections`` is a list of ``(heading, entries)`` where each entry is
    ``(title, relative_url, description)``.

    With ``sub_level`` set, every section after the first is written at that
    heading depth — used to nest subtype groups under the type's own heading
    instead of listing them as siblings.
    """

    lines: list[str] = []
    for i, (heading, entries) in enumerate(sections):
        depth = 1 if (sub_level is None or i == 0) else sub_level
        lines.append(f"{'#' * depth} {heading}")
        lines.append("")
        for title, url, description in entries:
            suffix = f" - {description}" if description else ""
            lines.append(f"* [{title}]({url}){suffix}")
        lines.append("")
    path = directory / "index.md"
    write_if_changed(path, "\n".join(lines).strip() + "\n")
    return path
