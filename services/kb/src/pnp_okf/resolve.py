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
from pnp_okf.models import (
    DIR_TO_TYPE,
    PERSON_TYPES,
    MAX_EVENT_SESSION_SPAN,
    SESSION_SCOPED_TYPES,
    TYPE_DIR,
)
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
    """Name tokens for the subset rule, taken from the *concept id*.

    Deliberately not ``canonical_name``: that is a display label a human may
    pin at any time ("Nyruk" for "Nairuk"). Driving merge decisions off it
    meant a pure renaming silently reshuffled which entities folded together,
    so a cosmetic fix could surface unrelated conflicts elsewhere. The
    concept id is the stable identity, and ``_fuzzy_match`` already uses it.
    """

    return set(entity.concept_id.rsplit("/", 1)[-1].split("_"))


def _fuzzy_match(a: CanonicalEntity, b: CanonicalEntity) -> bool:
    slug_a = a.concept_id.rsplit("/", 1)[-1]
    slug_b = b.concept_id.rsplit("/", 1)[-1]
    return SequenceMatcher(None, slug_a, slug_b).ratio() >= FUZZY_RATIO


def merge_near_duplicates(
    entities: list[CanonicalEntity],
    never_merge: list[set[str]] | None = None,
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
    blocked = never_merge or []

    def _forbidden(a: CanonicalEntity, b: CanonicalEntity) -> bool:
        # A human ruling that two things are distinct must also stop the
        # automatic passes, not just the dedup suggestions — otherwise a
        # deliberate split is silently undone on the next run.
        pair = {a.concept_id, b.concept_id}
        return any(len(pair & group) >= 2 for group in blocked)

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
                if a is b or not _same_space(a, b) or _forbidden(a, b):
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
            and not _forbidden(a, b)
            # The longer name only wins if it is at least as well attested.
            # A short name with many mentions next to a longer one with a
            # handful is not a person and their fuller name — it is a person
            # and something *derived* from them: "Die Magier von Belorus",
            # "Geist von Rotunas", "Vampire von Voras". Folding that way round
            # deletes the actual character and keeps the footnote.
            and len(b.mentions) >= len(a.mentions)
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


RULES_FILENAME = "entity_rules.yaml"


def rules_path_for(registry_path: Path) -> Path:
    """The hand-authored rules file that sits next to the registry."""

    return registry_path.with_name(RULES_FILENAME)


def _registry_data(registry_path: Path) -> dict:
    """Registry inventory plus the hand-authored rules beside it.

    ``entity_registry.yaml`` is *generated*: :func:`write_registry` rewrites it
    through a YAML dump on every run, which strips every comment. Keeping the
    rules there meant the tool erased the reasons for its own rules. So they
    live in ``entity_rules.yaml``, which nothing ever writes — the split makes
    the existing invariant real: rules are input, the inventory is output.

    Rules still found in the registry are honoured, so an un-migrated file
    keeps working; the rules file wins where both define the same name.
    """

    data: dict = {}
    if registry_path.exists():
        data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    rules_path = rules_path_for(registry_path)
    if not rules_path.exists():
        return data
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    for key, value in rules.items():
        existing = data.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            data[key] = {**existing, **value}
        elif isinstance(value, list) and isinstance(existing, list):
            data[key] = existing + value
        else:
            data[key] = value
    return data


def _load_alias_overrides(registry_path: Path) -> dict[str, str]:
    """Load ``alias (lowercased) -> concept_id`` overrides from the registry.

    Aliases are maintained by hand directly on each concept in the
    ``entities:`` section – the alias next to a concept both de-duplicates
    matching mentions and is shown as a display alias. The optional
    ``merge:`` mapping is still honoured for cases where you want to fold a
    name in without listing it under a concept.
    """

    data = _registry_data(registry_path)
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


def _load_never_merge_pairs(registry_path: Path) -> list[set[str]]:
    """``never_merge:`` groups, so the automatic passes honour them too."""

    data = _registry_data(registry_path)
    out: list[set[str]] = []
    for group in data.get("never_merge") or []:
        ids = {str(c).strip() for c in group if str(c).strip()}
        if len(ids) >= 2:
            out.append(ids)
    return out


def _load_splits(registry_path: Path) -> dict[tuple[str, str], str]:
    """Route one *session's* mention of a name to its own concept.

    Merging fixes many-names-one-being; this fixes the opposite, which no
    name-based rule can reach: two unrelated beings sharing a name. The
    campaign has two Haralds — a privateer captain and a demon — extracted
    under the identical string, so only the session they appear in tells them
    apart.

    Registry form (``session`` matches the session date or id)::

        split:
          - name: harald
            session: "2026-04-14"
            concept_id: npcs/harald_daemon
    """

    data = _registry_data(registry_path)
    out: dict[tuple[str, str], str] = {}
    for rule in data.get("split") or []:
        name = str(rule.get("name", "")).strip().lower()
        session = str(rule.get("session", "")).strip()
        concept_id = str(rule.get("concept_id", "")).strip()
        if name and session and concept_id:
            out[(name, session)] = concept_id
    return out


def _load_canonical_names(registry_path: Path) -> dict[str, str]:
    """Hand-set display names from the registry, keyed by concept id.

    Without this the title always comes from whichever transcript spelling
    happened to be extracted first, so a corrected name ("Thyrex" for the
    mis-heard "T-Rex", "Nyruk" for "Nairuk") could never be made to stick —
    the correction would be silently overwritten on every run.

    A pin belongs in ``entity_rules.yaml`` under ``canonical_name:``, where the
    reason for it can be written down; the value read back from the generated
    inventory is the same setting without its comment, kept for what is already
    pinned there.
    """

    data = _registry_data(registry_path)
    out: dict[str, str] = {}
    for cid, name in (data.get("canonical_name") or {}).items():
        cid, name = str(cid).strip(), str(name).strip()
        if cid and name:
            out[cid] = name
    for entry in data.get("entities") or []:
        cid = str(entry.get("concept_id", "")).strip()
        name = str(entry.get("canonical_name", "")).strip()
        if cid in out:
            continue  # an explicit rule wins over the generated inventory
        if cid and name:
            out[cid] = name
    return out


def _load_ignored(registry_path: Path) -> set[str]:
    """Concept ids listed under ``ignore:`` — never become concepts at all.

    Extraction inevitably produces generic buckets ("Brücke", "Turm",
    "Statue"): every session that features *a* bridge feeds the same concept,
    so it accumulates mentions of unrelated things and reads as one place
    that keeps changing. Such a concept cannot be fixed by merging or by a
    ruling — it should not exist. Its mentions are dropped and any file left
    over is pruned on the next run.
    """

    data = _registry_data(registry_path)
    return {str(c).strip() for c in (data.get("ignore") or []) if str(c).strip()}


def _load_important(registry_path: Path) -> set[str]:
    """Concept ids flagged ``important: true`` in the registry.

    These force the deep synthesis tier regardless of mention count — the
    escape hatch for entities the automatic rules underrate. Settable from
    ``entity_rules.yaml`` as an ``important:`` list as well, so the choice can
    be justified next to the other identity rules.
    """

    data = _registry_data(registry_path)
    flagged = {str(c).strip() for c in (data.get("important") or [])}
    flagged |= {
        str(entry.get("concept_id", "")).strip()
        for entry in data.get("entities") or []
        if entry.get("important")
    }
    return flagged - {""}


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
    ignored = _load_ignored(registry_path)
    pinned_names = _load_canonical_names(registry_path)
    splits = _load_splits(registry_path)
    dropped = 0
    # Also match registry keys after slugification, so "Lindo  Laut" folds
    # into a registry entry written as "lindo laut".
    slug_overrides = {slugify(k): v for k, v in overrides.items()}
    entities: dict[str, CanonicalEntity] = {}
    # Chronological position of each session, for the event-span cap.
    session_order = {sid: i for i, sid in enumerate(sorted(extractions))}

    for session_id in sorted(extractions):
        extraction = extractions[session_id]
        transcript = transcripts[session_id]
        for mention in extraction.entities:
            name_key = mention.name.strip().lower()
            # A per-session split wins over every name-based rule: it is the
            # only signal that separates two beings sharing one name.
            concept_id = (
                splits.get((name_key, transcript.date))
                or splits.get((name_key, session_id))
                or overrides.get(name_key)
                or slug_overrides.get(slugify(mention.name))
                or _default_concept_id(mention.type, mention.name)
            )
            if concept_id in ignored:
                dropped += 1
                continue
            # An event may span a few sittings (a tournament, a siege) but not
            # the whole campaign: past MAX_EVENT_SESSION_SPAN the same generic
            # name ("Vertrag") is a different occurrence, so it gets its own
            # id instead of being folded in. An explicit registry override is
            # a human saying they DO belong together and always wins.
            explicit = name_key in overrides or slugify(mention.name) in slug_overrides
            if mention.type in SESSION_SCOPED_TYPES and not explicit:
                claimed = entities.get(concept_id)
                if claimed is not None:
                    seen = [
                        session_order.get(m.session_id, 0) for m in claimed.mentions
                    ]
                    here = session_order.get(session_id, 0)
                    span = max(seen + [here]) - min(seen + [here]) + 1
                    if span > MAX_EVENT_SESSION_SPAN:
                        concept_id = f"{concept_id}_{transcript.date}"
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
                    subtype=mention.subtype.strip(),
                )
                entities[concept_id] = entity
            if (
                mention.name.strip() != entity.canonical_name
                and mention.name.strip() not in entity.aliases
            ):
                entity.aliases.append(mention.name.strip())
            if not entity.subtype and mention.subtype.strip():
                entity.subtype = mention.subtype.strip()
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

    if dropped:
        log.info(
            "[resolve] dropped %d mention(s) for %d ignored concept(s)",
            dropped,
            len(ignored),
        )
    # A hand-set canonical_name wins over the extracted spelling.
    for cid, entity in entities.items():
        pinned = pinned_names.get(cid)
        if pinned and pinned != entity.canonical_name:
            if entity.canonical_name not in entity.aliases:
                entity.aliases.append(entity.canonical_name)
            entity.canonical_name = pinned

    resolved = merge_near_duplicates(
        list(entities.values()), _load_never_merge_pairs(registry_path)
    )
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
    # Any other hand-maintained top-level key (``ignore:``, ``never_merge:``,
    # …) must survive: this function rewrites the file on every run, so a key
    # it does not know about would be silently deleted and the setting lost.
    # Keys that have moved to entity_rules.yaml are *not* copied back — this
    # dump would strip their comments, which is why they moved out.
    extra_keys: dict[str, object] = {}
    rules_path = rules_path_for(registry_path)
    migrated: set[str] = set()
    if rules_path.exists():
        migrated = set(yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {})
    if registry_path.exists():
        existing = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        merge = {} if "merge" in migrated else (existing.get("merge") or {})
        extra_keys = {
            k: v
            for k, v in existing.items()
            if k not in ("merge", "entities") and k not in migrated
        }
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
        # Omitted once the rules have moved out, so the generated file does not
        # sprout an empty key that invites hand-edits it would then eat.
        **({"merge": merge} if merge else {}),
        **extra_keys,
        "entities": inventory,
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Entity registry — GENERATED. The pipeline rewrites this file on\n"
        "# every run and the YAML dump strips comments, so do not document\n"
        "# anything here.\n"
        "#\n"
        f"# Identity rules (merge/never_merge/ignore/split) live in\n"
        f"# {RULES_FILENAME} next to this file, which nothing ever writes.\n"
        "#\n"
        "# Two hand-maintained fields survive here, per concept:\n"
        "#   aliases:         appended to, never clobbered\n"
        "#   important: true  forces the deep synthesis tier for entities the\n"
        "#                    automatic rules underrate (Characters and\n"
        "#                    Deities are always deep anyway)\n"
    )
    registry_path.write_text(
        header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    log.info("[resolve] wrote registry: %s", registry_path)
