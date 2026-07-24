from __future__ import annotations

import logging
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from pnp_okf.models import (
    CanonicalEntity,
    EntityType,
    MentionRef,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.models import DIR_TO_TYPE, PERSON_TYPES, TYPE_DIR
from pnp_okf.okf import slugify

log = logging.getLogger(__name__)

# Same bar as pnp_graph.resolve: stdlib difflib, no extra dependency.
FUZZY_RATIO = 0.9


def _default_concept_id(entity_type: EntityType, name: str) -> str:
    return f"{TYPE_DIR[entity_type]}/{slugify(name)}"


def _same_space(a: CanonicalEntity, b: CanonicalEntity) -> bool:
    if a.type in PERSON_TYPES and b.type in PERSON_TYPES:
        return True
    return a.type == b.type


def _tokens(entity: CanonicalEntity) -> set[str]:
    return set(slugify(entity.canonical_name).split("_"))


def _fuzzy_match(a: CanonicalEntity, b: CanonicalEntity) -> bool:
    slug_a = a.concept_id.rsplit("/", 1)[-1]
    slug_b = b.concept_id.rsplit("/", 1)[-1]
    return SequenceMatcher(None, slug_a, slug_b).ratio() >= FUZZY_RATIO


def merge_near_duplicates(
    entities: list[CanonicalEntity],
) -> list[CanonicalEntity]:
    """Second resolution pass: fold near-duplicate entities together.

    Two rules, both within the same identity space (Character+NPC form one
    person space, other types match only their own kind):

    1. **Fuzzy**: concept slugs with a difflib ratio >= ``FUZZY_RATIO``
       (Whisper spelling drift: "Esterosa" vs "Esterossa").
    2. **Token subset** (person space only): all name tokens of one entity
       appear in the other's, and that superset is *unique* among the
       candidates ("Esterossa" -> "Esterossa Torbhalm"). A name with several
       supersets stays unmerged — ambiguity is for the registry/human.

    The entity with more mentions survives; the other's name and aliases
    become aliases. Every auto-merge is logged so review can catch misfolds;
    hand-maintained registry merges always run first and win.
    """

    survivors: list[CanonicalEntity] = list(entities)
    merged_away: dict[str, str] = {}

    def _merge(loser: CanonicalEntity, winner: CanonicalEntity, rule: str) -> None:
        for name in [loser.canonical_name, *loser.aliases]:
            if (
                name.lower() != winner.canonical_name.lower()
                and name not in winner.aliases
            ):
                winner.aliases.append(name)
        winner.mentions.extend(loser.mentions)
        winner.mentions.sort(key=lambda m: (m.date, m.citation_ts))
        # Importance is a property of the person/place, not of the spelling
        # that happened to win, so it survives the fold.
        winner.important = winner.important or loser.important
        survivors.remove(loser)
        merged_away[loser.concept_id] = winner.concept_id
        log.info(
            "[resolve] auto-merged %s -> %s (%s)",
            loser.concept_id,
            winner.concept_id,
            rule,
        )

    # Fuzzy pass.
    changed = True
    while changed:
        changed = False
        for a in list(survivors):
            for b in list(survivors):
                if a is b or not _same_space(a, b):
                    continue
                if _fuzzy_match(a, b):
                    loser, winner = sorted(
                        (a, b), key=lambda e: (len(e.mentions), e.concept_id)
                    )
                    _merge(loser, winner, "fuzzy")
                    changed = True
                    break
            if changed:
                break

    # Token-subset pass (person space only, unique superset required).
    for a in list(survivors):
        if a.type not in PERSON_TYPES or a not in survivors:
            continue
        supersets = [
            b
            for b in survivors
            if b is not a
            and b.type in PERSON_TYPES
            and _tokens(a) < _tokens(b)
        ]
        if len(supersets) == 1:
            _merge(a, supersets[0], "token-subset")
        elif len(supersets) > 1:
            log.warning(
                "[resolve] %s has %d possible supersets (%s) — left unmerged, "
                "add a registry merge to resolve",
                a.concept_id,
                len(supersets),
                ", ".join(s.concept_id for s in supersets),
            )

    if merged_away:
        log.info("[resolve] merge pass folded %d entities", len(merged_away))
    return sorted(survivors, key=lambda e: e.concept_id)


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


def _load_important(registry_path: Path) -> set[str]:
    """Concept ids flagged ``important: true`` in the registry.

    These force the deep synthesis tier regardless of mention count — the
    escape hatch for entities the automatic rules underrate.
    """

    if not registry_path.exists():
        return set()
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return {
        str(entry.get("concept_id", "")).strip()
        for entry in data.get("entities") or []
        if entry.get("important")
    } - {""}


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
    important = _load_important(registry_path)
    # Also match registry keys after slugification, so "Lindo  Laut" folds
    # into a registry entry written as "lindo laut".
    slug_overrides = {slugify(k): v for k, v in overrides.items()}
    entities: dict[str, CanonicalEntity] = {}

    for session_id in sorted(extractions):
        extraction = extractions[session_id]
        transcript = transcripts[session_id]
        for mention in extraction.entities:
            name_key = mention.name.strip().lower()
            concept_id = (
                overrides.get(name_key)
                or slug_overrides.get(slugify(mention.name))
                or _default_concept_id(mention.type, mention.name)
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
                    important=concept_id in important,
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
                    quality=transcript.quality,
                )
            )

    resolved = merge_near_duplicates(list(entities.values()))
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
    preserved_important: set[str] = set()
    if registry_path.exists():
        existing = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        merge = existing.get("merge") or {}
        # Keep the hand-maintained aliases on each concept.
        for entry in existing.get("entities") or []:
            cid = str(entry.get("concept_id", "")).strip()
            if cid and entry.get("aliases"):
                preserved_aliases[cid] = [str(a).strip() for a in entry["aliases"]]
            if cid and entry.get("important"):
                preserved_important.add(cid)

    inventory = []
    for e in entities:
        # Start from the hand-maintained aliases, then append discovered ones.
        aliases: list[str] = []
        for alias in preserved_aliases.get(e.concept_id, []) + list(e.aliases):
            if alias not in aliases and alias.lower() != e.canonical_name.lower():
                aliases.append(alias)
        entry = {
            "concept_id": e.concept_id,
            "type": e.type.value,
            "canonical_name": e.canonical_name,
            "aliases": aliases,
            "mention_count": len(e.mentions),
        }
        # Only write the flag when set, so the file stays uncluttered.
        if e.important or e.concept_id in preserved_important:
            entry["important"] = True
        inventory.append(entry)
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
        "#\n"
        "# 'important: true' on a concept forces the deep synthesis tier for\n"
        "# entities the automatic rules underrate (a pivotal NPC or city whose\n"
        "# mention count stays low). Characters and Deities are always deep.\n"
    )
    registry_path.write_text(
        header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    log.info("[resolve] wrote registry: %s", registry_path)
