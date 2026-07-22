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


def write_concept(
    bundle_dir: Path, concept_id: str, frontmatter: dict[str, object], body: str
) -> Path:
    """Write ``<bundle_dir>/<concept_id>.md`` and return its path."""

    path = bundle_dir / f"{concept_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_document(frontmatter, body), encoding="utf-8")
    return path


def link(concept_id: str, title: str) -> str:
    """Bundle-relative markdown link to another concept (SPEC 5.1)."""

    return f"[{title}](/{concept_id}.md)"


def write_index(
    directory: Path,
    sections: list[tuple[str, list[tuple[str, str, str]]]],
) -> Path:
    """Write an ``index.md`` (no frontmatter) with grouped bullet lists.

    ``sections`` is a list of ``(heading, entries)`` where each entry is
    ``(title, relative_url, description)``.
    """

    lines: list[str] = []
    for heading, entries in sections:
        lines.append(f"# {heading}")
        lines.append("")
        for title, url, description in entries:
            suffix = f" - {description}" if description else ""
            lines.append(f"* [{title}]({url}){suffix}")
        lines.append("")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "index.md"
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path
