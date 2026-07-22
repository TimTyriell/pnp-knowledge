from __future__ import annotations

import logging
from pathlib import Path

import yaml

from pnp_okf.models import (
    CanonicalEntity,
    EntityType,
    MentionRef,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.models import DIR_TO_TYPE, TYPE_DIR
from pnp_okf.okf import slugify

log = logging.getLogger(__name__)


def _default_concept_id(entity_type: EntityType, name: str) -> str:
    return f"{TYPE_DIR[entity_type]}/{slugify(name)}"


def _load_alias_overrides(registry_path: Path) -> dict[str, str]:
    """Load ``alias (lowercased) -> concept_id`` overrides from the registry.

    Aliases are maintained by hand directly on each concept in the
    ``entities:`` section – the alias next to a concept both de-duplicates
    matching mentions and is shown as a display alias. The optional
    ``merge:`` mapping is still honoured for cases where you want to fold a
    name in without listing it under a concept.
    """

    if not registry_path.exists():
        return {}
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    overrides: dict[str, str] = {}
    # Per-concept aliases from 'entities:' (primary, human-maintained source).
    for entry in data.get("entities") or []:
        concept_id = str(entry.get("concept_id", "")).strip()
        if not concept_id:
            continue
        for alias in entry.get("aliases") or []:
            overrides[str(alias).strip().lower()] = concept_id
    # 'merge:' overrides take precedence for any explicit fold-ins.
    for raw_name, concept_id in (data.get("merge") or {}).items():
        overrides[str(raw_name).strip().lower()] = str(concept_id).strip()
    return overrides


def resolve_entities(
    extractions: dict[str, SessionExtraction],
    transcripts: dict[str, SessionTranscript],
    registry_path: Path,
) -> list[CanonicalEntity]:
    """Cluster per-session mentions into canonical entities.

    Clustering is by ``(type, slug(name))``. A mention whose name matches a
    hand-maintained alias (from the registry ``entities:`` section or the
    optional ``merge:`` map) is folded into that concept. Sessions are
    processed in chronological order.
    """

    overrides = _load_alias_overrides(registry_path)
    entities: dict[str, CanonicalEntity] = {}

    for session_id in sorted(extractions):
        extraction = extractions[session_id]
        transcript = transcripts[session_id]
        for mention in extraction.entities:
            name_key = mention.name.strip().lower()
            concept_id = overrides.get(name_key) or _default_concept_id(
                mention.type, mention.name
            )
            # Keep type consistent with the concept-id directory: a merge may
            # fold this mention into a concept of a different type.
            entity_type = DIR_TO_TYPE.get(
                concept_id.split("/", 1)[0], mention.type
            )
            entity = entities.get(concept_id)
            if entity is None:
                entity = CanonicalEntity(
                    concept_id=concept_id,
                    type=entity_type,
                    canonical_name=mention.name.strip(),
                    aliases=[],
                    mentions=[],
                )
                entities[concept_id] = entity
            if (
                mention.name.strip() != entity.canonical_name
                and mention.name.strip() not in entity.aliases
            ):
                entity.aliases.append(mention.name.strip())
            entity.mentions.append(
                MentionRef(
                    session_id=session_id,
                    date=transcript.date,
                    url=transcript.url,
                    citation_ts=mention.citation_ts,
                    note=mention.note,
                )
            )

    resolved = sorted(entities.values(), key=lambda e: e.concept_id)
    log.info(
        "[resolve] %d mentions -> %d canonical entities",
        sum(len(e.entities) for e in extractions.values()),
        len(resolved),
    )
    return resolved


def write_registry(entities: list[CanonicalEntity], registry_path: Path) -> None:
    """Write the entity registry.

    Aliases are maintained by hand on each concept in ``entities:``. This
    function never clobbers them: existing aliases are preserved and any
    newly discovered name variants are appended. The optional ``merge:``
    mapping is carried through untouched.
    """

    merge: dict[str, str] = {}
    preserved_aliases: dict[str, list[str]] = {}
    if registry_path.exists():
        existing = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        merge = existing.get("merge") or {}
        # Keep the hand-maintained aliases on each concept.
        for entry in existing.get("entities") or []:
            cid = str(entry.get("concept_id", "")).strip()
            if cid and entry.get("aliases"):
                preserved_aliases[cid] = [str(a).strip() for a in entry["aliases"]]

    inventory = []
    for e in entities:
        # Start from the hand-maintained aliases, then append discovered ones.
        aliases: list[str] = []
        for alias in preserved_aliases.get(e.concept_id, []) + list(e.aliases):
            if alias not in aliases and alias.lower() != e.canonical_name.lower():
                aliases.append(alias)
        inventory.append(
            {
                "concept_id": e.concept_id,
                "type": e.type.value,
                "canonical_name": e.canonical_name,
                "aliases": aliases,
                "mention_count": len(e.mentions),
            }
        )
    doc = {
        "merge": merge,
        "entities": inventory,
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Entity registry.\n"
        "#\n"
        "# Maintain aliases by hand: add a name under a concept's 'aliases:'\n"
        "# in the 'entities:' list below. Each alias both de-duplicates\n"
        "# matching mentions and is shown as a display alias. Your aliases are\n"
        "# never overwritten - the tool only appends newly discovered variants.\n"
        "#\n"
        "# 'merge:' is optional: map a name (lowercased) to a concept_id to\n"
        "# fold it in without listing it under a concept, e.g.:\n"
        "#   merge:\n"
        "#     \"heck\": factions/hag\n"
    )
    registry_path.write_text(
        header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    log.info("[resolve] wrote registry: %s", registry_path)
