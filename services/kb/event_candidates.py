"""Candidate list for ``event_concepts:`` (T4): which Events stay concepts.

Read-only. Every Event concept in the bundle is scored on what other pages
show about it: inbound links from non-session concepts, whether it is
must-keep (``important:`` or a GM ruling's ``entity=`` directive), its
subtype and its source count. The output is a markdown table plus a
ready-to-paste ``event_concepts:`` block proposing the rows that have a
must-keep flag, an inbound link or the subtype ``Tod``. A human approves the
block (docs/plans/T4-event-anchors.md, step 3) before it enters
entity_rules.yaml.

    python event_candidates.py > ../../docs/audits/<date>-event-candidates.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pnp_okf.okf import split_document
from pnp_okf.resolve import _registry_data

ROOT = Path(__file__).resolve().parent  # services/kb
KNOWLEDGE = ROOT.parent.parent / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"
SOURCES = KNOWLEDGE / "sources"

_DIRECTIVE_RE = re.compile(r"<!--\s*okf:\s*entity=([^;>]+)")


def _ruling_event_targets() -> set[str]:
    """Event ids named by an ``<!-- okf: entity=... -->`` directive in sources/."""

    out: set[str] = set()
    for path in SOURCES.glob("*.md"):
        for match in _DIRECTIVE_RE.finditer(path.read_text(encoding="utf-8")):
            for target in match.group(1).split(","):
                target = target.strip()
                if target.startswith("events/"):
                    out.add(target)
    return out


def _inbound_counts(slugs: list[str]) -> dict[str, int]:
    """Occurrences of ``/events/<slug>.md`` in pages outside sessions/ and events/."""

    counts = dict.fromkeys(slugs, 0)
    for path in BUNDLE.rglob("*.md"):
        rel = path.relative_to(BUNDLE)
        if rel.parts[0] in ("sessions", "events") or path.name in ("index.md", "log.md"):
            continue
        text = path.read_text(encoding="utf-8")
        for slug in slugs:
            counts[slug] += text.count(f"/events/{slug}.md")
    return counts


def _rows() -> list[dict]:
    data = _registry_data(REGISTRY)
    important = {str(c) for c in (data.get("important") or [])}
    ruled = _ruling_event_targets()
    event_files = sorted(p for p in (BUNDLE / "events").glob("*.md") if p.name != "index.md")
    slugs = [p.stem for p in event_files]
    inbound = _inbound_counts(slugs)

    rows = []
    for path in event_files:
        cid = f"events/{path.stem}"
        fm, _body = split_document(path.read_text(encoding="utf-8"))
        rows.append({
            "concept_id": cid,
            "title": str(fm.get("title", path.stem)),
            "subtype": str(fm.get("subtype", "")),
            "inbound": inbound[path.stem],
            "must_keep": cid in important or cid in ruled,
            "sources": len(fm.get("sources") or []),
        })
    rows.sort(key=lambda r: (
        not r["must_keep"], -r["inbound"], r["subtype"] != "Tod", r["title"]
    ))
    return rows


def _proposed(rows: list[dict]) -> list[str]:
    return [
        r["concept_id"] for r in rows
        if r["must_keep"] or r["inbound"] >= 1 or r["subtype"] == "Tod"
    ]


def main() -> int:
    # The report is redirected to a file; Windows' default codepage would turn
    # "Zerstörung" into a replacement character.
    sys.stdout.reconfigure(encoding="utf-8")
    rows = _rows()
    print("# Event candidates for `event_concepts:` (T4)\n")
    print(f"{len(rows)} Event concepts in the bundle.\n")
    print("| concept_id | title | subtype | inbound | must_keep | sources |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['concept_id']} | {r['title']} | {r['subtype']} | {r['inbound']} "
            f"| {'yes' if r['must_keep'] else ''} | {r['sources']} |"
        )
    print("\n## Proposed `event_concepts:` block (pending GM approval)\n")
    print("```yaml")
    print("event_concepts:")
    for cid in _proposed(rows):
        print(f"- {cid}")
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
