"""Post-emit data-quality validation for an OKF campaign bundle.

Scans every concept in a bundle directory and reports the failure classes the
pipeline is prone to: dead cross-links, duplicate concepts (same title, or the
same slug reused across types), and concepts missing the required ``type``.
Used by ``pnp validate`` and as a non-fatal report at the end of ``pnp run``.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from pnp_okf.links import ConceptIndex, _LINK_RE, normalize_body
from pnp_okf.resolve import load_spellings

log = logging.getLogger(__name__)

_RESERVED = {"index.md", "log.md"}


def _iter_concept_files(bundle_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(bundle_dir.rglob("*.md"))
        if p.name not in _RESERVED
    ]


def _split_frontmatter(text: str) -> dict[str, object]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


@dataclass
class ValidationReport:
    """Aggregated data-quality findings for a bundle."""

    concept_count: int = 0
    link_count: int = 0
    broken_links: list[tuple[str, str]] = field(default_factory=list)
    duplicate_titles: dict[str, list[str]] = field(default_factory=dict)
    cross_type_slugs: dict[str, list[str]] = field(default_factory=dict)
    missing_type: list[str] = field(default_factory=list)
    duplicate_ids: dict[str, list[str]] = field(default_factory=dict)
    suspected_person_dups: list[tuple[str, str]] = field(default_factory=list)
    suspected_title_dups: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.broken_links
            or self.duplicate_titles
            or self.cross_type_slugs
            or self.missing_type
            or self.duplicate_ids
            or self.suspected_person_dups
            or self.suspected_title_dups
        )

    def summary(self) -> str:
        lines = [
            f"Concepts:      {self.concept_count}",
            f"Internal links: {self.link_count}"
            + (
                f"  ({self.link_count - len(self.broken_links)} resolved, "
                f"{len(self.broken_links)} broken)"
                if self.link_count
                else ""
            ),
        ]
        if self.broken_links:
            lines.append(f"\nBroken links ({len(self.broken_links)}):")
            for src, target in self.broken_links[:40]:
                lines.append(f"  {src}: {target}")
            if len(self.broken_links) > 40:
                lines.append(f"  … and {len(self.broken_links) - 40} more")
        if self.duplicate_titles:
            lines.append(f"\nDuplicate titles ({len(self.duplicate_titles)}):")
            for title, ids in self.duplicate_titles.items():
                lines.append(f"  {title!r}: {', '.join(ids)}")
        if self.cross_type_slugs:
            lines.append(
                f"\nSame slug across types ({len(self.cross_type_slugs)}):"
            )
            for slug, ids in self.cross_type_slugs.items():
                lines.append(f"  {slug}: {', '.join(ids)}")
        if self.missing_type:
            lines.append(f"\nMissing 'type' ({len(self.missing_type)}):")
            for cid in self.missing_type:
                lines.append(f"  {cid}")
        if self.duplicate_ids:
            lines.append(f"\nDuplicate 'id' ({len(self.duplicate_ids)}):")
            for eid, ids in self.duplicate_ids.items():
                lines.append(f"  {eid}: {', '.join(ids)}")
        if self.suspected_person_dups:
            lines.append(
                f"\nSuspected duplicate persons ({len(self.suspected_person_dups)})"
                " — merge via entity_registry.yaml if same person:"
            )
            for a, b in self.suspected_person_dups:
                lines.append(f"  {a} <-> {b}")
        if self.suspected_title_dups:
            lines.append(
                f"\nSuspected duplicate titles ({len(self.suspected_title_dups)})"
                " — a near-miss spelling split, not an exact match:"
            )
            for a, b in self.suspected_title_dups:
                lines.append(f"  {a} <-> {b}")
        if self.ok:
            lines.append("\nOK — no data-quality issues found.")
        return "\n".join(lines)


def validate_bundle(bundle_dir: Path) -> ValidationReport:
    """Scan ``bundle_dir`` and return a :class:`ValidationReport`."""

    files = _iter_concept_files(bundle_dir)
    concept_ids = [
        str(p.relative_to(bundle_dir).with_suffix("")).replace("\\", "/")
        for p in files
    ]
    index = ConceptIndex(concept_ids)
    report = ValidationReport(concept_count=len(files))

    titles: dict[str, list[str]] = defaultdict(list)
    basenames: dict[str, list[str]] = defaultdict(list)
    entity_ids: dict[str, list[str]] = defaultdict(list)
    person_slugs: list[str] = []
    titles_by_type: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for path, cid in zip(files, concept_ids):
        text = path.read_text(encoding="utf-8")
        for match in _LINK_RE.finditer(text):
            report.link_count += 1
            if index.resolve(match.group(2)) is None:
                report.broken_links.append((cid, match.group(2)))

        fm = _split_frontmatter(text)
        ctype = str(fm.get("type") or "").strip()
        if not ctype:
            report.missing_type.append(cid)
        title = str(fm.get("title") or "").strip()
        # Sessions legitimately share a recurring series title; skip them.
        if title and ctype != "Session":
            titles[f"{ctype}::{title.lower()}"].append(cid)
            titles_by_type[ctype].append((cid, title))
        basenames[cid.rsplit("/", 1)[-1]].append(cid)
        eid = str(fm.get("id") or "").strip()
        if eid:
            entity_ids[eid].append(cid)
        if cid.split("/", 1)[0] in ("characters", "npcs"):
            person_slugs.append(cid)

    report.duplicate_titles = {
        key.split("::", 1)[1]: sorted(ids)
        for key, ids in sorted(titles.items())
        if len(ids) > 1
    }
    report.cross_type_slugs = {
        slug: sorted(ids)
        for slug, ids in sorted(basenames.items())
        if len({i.split("/", 1)[0] for i in ids}) > 1
    }
    report.duplicate_ids = {
        eid: sorted(ids)
        for eid, ids in sorted(entity_ids.items())
        if len(ids) > 1
    }
    report.suspected_person_dups = _suspect_person_dups(person_slugs)
    for items in titles_by_type.values():
        report.suspected_title_dups.extend(_suspect_title_dups(items))
    return report


def _suspect_person_dups(person_cids: list[str]) -> list[tuple[str, str]]:
    """Flag character/NPC concept pairs that look like the same person.

    Mirrors the resolve-stage auto-merge rules (difflib ratio >= 0.9 or a
    token-subset name) so a bundle written by an older pipeline — or edited
    by hand — still surfaces suspected duplicates in ``pnp validate``.
    """

    # ponytail: O(n^2) over persons only; fine for a one-campaign bundle.
    suspects: list[tuple[str, str]] = []
    for i, a in enumerate(person_cids):
        slug_a = a.rsplit("/", 1)[-1]
        tokens_a = set(slug_a.split("_"))
        for b in person_cids[i + 1:]:
            slug_b = b.rsplit("/", 1)[-1]
            tokens_b = set(slug_b.split("_"))
            if (
                SequenceMatcher(None, slug_a, slug_b).ratio() >= 0.9
                or tokens_a < tokens_b
                or tokens_b < tokens_a
            ):
                suspects.append((a, b))
    return suspects


def _suspect_title_dups(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Flag same-type concept pairs whose titles are a near-miss of each
    other but not an exact match (that's ``duplicate_titles``' job).

    Catches a one-letter spelling split -- e.g. ``items/zebras_zorn``
    ("Zebras Zorn") and ``items/streitkolben_von_dodo`` ("Zebros Zorn") are
    the same weapon under titles that dodge exact-match comparison, and their
    slugs share no tokens at all, so ``_suspect_person_dups``'s slug-fuzzing
    can't see it either -- title fuzzing is the only signal left.

    ``items`` is ``(concept_id, title)`` pairs already grouped to one type.
    """

    # ponytail: O(n^2) per type; largest type (npcs) is ~250, fine.
    suspects: list[tuple[str, str]] = []
    for i, (cid_a, title_a) in enumerate(items):
        for cid_b, title_b in items[i + 1 :]:
            if title_a.lower() == title_b.lower():
                continue  # already reported by duplicate_titles
            if SequenceMatcher(None, title_a.lower(), title_b.lower()).ratio() >= 0.9:
                suspects.append((cid_a, cid_b))
    return suspects


def fix_bundle(bundle_dir: Path, registry_path: Path | None = None) -> tuple[int, int]:
    """Normalize cross-links in every concept file in place (no LLM calls).

    Rewrites resolvable links to their canonical ``/dir/slug.md`` form and
    drops unresolvable links to plain text. ``index.md`` / ``log.md`` use
    relative links and are left untouched (they are regenerated by ``run``).

    When ``registry_path`` is given, also applies ``entity_rules.yaml``'s
    ``spelling:`` rules to prose (see ``links.py::apply_spellings``) — so a
    spelling fix added there can be retro-applied to an already-emitted
    bundle without a full ``pnp run``.

    Returns ``(files_changed, links_dropped)`` where ``links_dropped`` is the
    number of unresolvable links converted to plain text.
    """

    files = _iter_concept_files(bundle_dir)
    concept_ids = [
        str(p.relative_to(bundle_dir).with_suffix("")).replace("\\", "/")
        for p in files
    ]
    spellings = load_spellings(registry_path) if registry_path else {}
    index = ConceptIndex(concept_ids, spellings=spellings)

    files_changed = 0
    links_dropped = 0
    for path in files:
        original = path.read_text(encoding="utf-8")
        new_text, unresolved = normalize_body(original, index)
        if new_text != original:
            links_dropped += len(unresolved)
            path.write_text(new_text, encoding="utf-8")
            files_changed += 1
    return files_changed, links_dropped
