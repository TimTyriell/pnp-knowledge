"""Diagnose knowledge/sources/ — what reaches an entity, and who has no grounding.

Read-only, no LLM calls: everything comes from knowledge/sources/,
entity_registry.yaml and the bundle.

`sources/` is the only channel for world knowledge that never appears in a
transcript, and it routes by *name*: a section reaches an entity because its
heading slug matches the entity's name, or because an `<!-- okf: entity=... -->`
directive names the concept id. Nothing warns when neither happens. A section
that matches nobody is simply never injected — it looks fine in the file and is
invisible in the output. A measurement in 2026-09 found 70 of 137 sections
(106 640 chars, ~60% of the folder) in exactly that state.

Five reports, and the last one matters most:

- dead: reaches zero entities. Either give it a directive or move it out.
- broad: fallback-matched, no directive, and lands on several entities at once.
  Usually a heading that is a common word rather than a name.
- fat: large enough to crowd the per-entity SOURCE_BUDGET_CHARS budget.
- undirected: no directive, so it routes on a name collision holding steady.
- ungrounded: the inverse view — deep-tier entities with no source at all,
  ranked by mention count. This is the writing worklist: the entities the
  campaign talks about most, that the knowledge base knows least about.

    python sources_doctor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent  # services/kb
KNOWLEDGE = ROOT.parent.parent / "knowledge"
SOURCES = KNOWLEDGE / "sources"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"

sys.path.insert(0, str(ROOT / "src"))
from pnp_okf.context import (  # noqa: E402
    SOURCE_BUDGET_CHARS,
    SourceSection,
    _primary_hits,
    load_sources,
)
from pnp_okf.models import (  # noqa: E402
    ALWAYS_DEEP_TYPES,
    DEEP_MENTION_THRESHOLD,
    EntityType,
)

# A fallback-matched section landing on more than this many entities is
# reported: past a handful it is a word collision, not a name.
BROAD_HITS = 3

# Sections at or above this share of the per-entity budget crowd out whatever
# else that entity has.
FAT_CHARS = SOURCE_BUDGET_CHARS // 5


class _Entity:
    """The fields _primary_hits reads, filled from entity_registry.yaml.

    The registry is the same input synthesis routes against, so matching it
    here needs no bundle parsing and no CanonicalEntity construction.
    """

    __slots__ = ("concept_id", "canonical_name", "aliases", "type", "mention_count")

    def __init__(self, raw: dict) -> None:
        self.concept_id = raw["concept_id"]
        self.canonical_name = raw.get("canonical_name") or ""
        self.aliases = raw.get("aliases") or []
        self.type = raw.get("type") or ""
        self.mention_count = int(raw.get("mention_count") or 0)

    def is_deep(self) -> bool:
        """Mirrors CanonicalEntity.tier's 'deep' arm (models.py)."""

        try:
            etype = EntityType(self.type)
        except ValueError:
            return False
        if self.mention_count >= DEEP_MENTION_THRESHOLD:
            return True
        return etype in ALWAYS_DEEP_TYPES and self.mention_count >= 2


def entities() -> list[_Entity]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return [_Entity(e) for e in (data.get("entities") or [])]


def routing(sections: list[SourceSection], ents: list[_Entity]) -> dict[int, list[str]]:
    """section identity -> the concept ids it reaches."""

    reach: dict[int, list[str]] = {id(s): [] for s in sections}
    for e in ents:
        for s in _primary_hits(e, sections):
            reach[id(s)].append(e.concept_id)
    return reach


def _label(s: SourceSection) -> str:
    return f"{s.origin} :: {s.heading}"


def main() -> int:
    sections = load_sources(SOURCES)
    ents = entities()
    reach = routing(sections, ents)
    grounded = {cid for hits in reach.values() for cid in hits}

    print(f"# sources doctor — {len(sections)} sections, {len(ents)} entities\n")
    print(f"grounded: {len(grounded)}/{len(ents)} entities "
          f"({100 * len(grounded) / max(1, len(ents)):.1f}%)")

    dead = [s for s in sections if not reach[id(s)]]
    print(f"\ndead: {len(dead)} section(s), {sum(len(s.text) for s in dead)} chars "
          "— reach zero entities, never injected anywhere")
    for s in sorted(dead, key=lambda s: -len(s.text)):
        print(f"   DEAD  {len(s.text):6d}ch  {_label(s)}")

    broad = [
        (len(reach[id(s)]), s) for s in sections
        if not s.targets and len(reach[id(s)]) > BROAD_HITS
    ]
    print(f"\nbroad: {len(broad)} section(s) — fallback-matched onto many entities")
    for n, s in sorted(broad, reverse=True, key=lambda p: p[0]):
        print(f"   BROAD {n:4d} entities  {_label(s)}")
        print(f"          -> {sorted(reach[id(s)])[:8]}")

    fat = [s for s in sections if len(s.text) >= FAT_CHARS]
    print(f"\nfat: {len(fat)} section(s) >= {FAT_CHARS} chars "
          f"(per-entity budget is {SOURCE_BUDGET_CHARS})")
    for s in sorted(fat, key=lambda s: -len(s.text)):
        print(f"   FAT   {len(s.text):6d}ch  {_label(s)}")

    undirected = [s for s in sections if not s.targets]
    print(f"\nundirected: {len(undirected)} of {len(sections)} section(s) carry no "
          "okf directive — routing rests on a name collision holding")
    for s in sorted(undirected, key=lambda s: s.origin):
        print(f"   NO DIRECTIVE  {_label(s)}  -> {sorted(reach[id(s)]) or 'nobody'}")

    ungrounded = sorted(
        (e for e in ents if e.is_deep() and e.concept_id not in grounded),
        key=lambda e: -e.mention_count,
    )
    print(f"\nungrounded: {len(ungrounded)} deep-tier entities with no source section "
          "— the writing worklist, most-mentioned first")
    for e in ungrounded[:30]:
        print(f"   NEEDS SOURCE  {e.mention_count:4d} mentions  {e.concept_id}")
    if len(ungrounded) > 30:
        print(f"   … and {len(ungrounded) - 30} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
