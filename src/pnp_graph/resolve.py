"""Canonical-id resolution between extract and store (docs/evolution/03 + 09).

Turns a per-session `GraphExtraction` (surface names) into resolved entity/edge
dicts keyed on deterministic ids, so `store.py` can MERGE on `:Entity{id}`:

- surface name -> id via the campaign-persistent alias registry
  (`data/alias_registry.json`): exact hit -> normalized hit -> fuzzy within the
  same type (difflib >= 0.9, logged) -> mint a new id + registry write-back.
- players and characters are separate namespaces; in-fiction edges that land on
  a Player are re-routed to that player's active character via the per-session
  PLAYS mapping (docs/evolution/09).
- relationship endpoints that resolve to nothing are dropped and logged to
  `state/failures/<sid>/dropped_edges.jsonl` — never MERGE-created as phantoms.
- predicates map through PREDICATE_SYNONYMS then ALLOWED_PREDICATES; off-vocab
  types are coerced to RELATES_TO and logged. Confidence tokens normalize to
  English via CONFIDENCE_MAP.
"""

import difflib
import json
import logging
import re
import unicodedata

from .config import (
    ALIAS_REGISTRY_PATH,
    ALLOWED_PREDICATES,
    CONFIDENCE_MAP,
    PREDICATE_SYNONYMS,
    STATE_DIR,
)
from .schema import GraphExtraction
from .store import sanitize_predicate

log = logging.getLogger("pnp_graph.resolve")

FUZZY_THRESHOLD = 0.9

# extraction type -> (id prefix, registry section)
_TYPE_MAP = {
    "Player": ("PLAYER", "players"),
    "Character": ("CHAR", "characters"),
    "Location": ("LOC", "locations"),
    "Item": ("ITEM", "items"),
    "Quest": ("QUEST", "quests"),
    "Event": ("EVT", "events"),
    "Faction": ("FACTION", "factions"),
    "RuleEntity": ("RULE", "rules"),  # only for non-SRD mints; SRD hits use the shared id
}

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
_ARTICLE_RE = re.compile(r"^(der|die|das|ein|eine|the)\s+", re.IGNORECASE)
_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def _fold(text: str) -> str:
    """Fold German umlauts/ß and strip remaining diacritics."""
    text = text.translate(_UMLAUTS)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def normalize(surface: str) -> str:
    """Comparison key: casefold, drop parentheticals/articles/punctuation, fold umlauts."""
    s = _PAREN_RE.sub("", surface)
    s = _ARTICLE_RE.sub("", s.strip())
    s = _fold(s).casefold()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def slug(surface: str) -> str:
    """Human-readable id part: 'der Lindo Laut (Tim)' -> 'LindoLaut'."""
    s = _PAREN_RE.sub("", surface)
    s = _ARTICLE_RE.sub("", s.strip())
    words = re.sub(r"[^A-Za-z0-9]+", " ", _fold(s)).split()
    return "".join(w[:1].upper() + w[1:] for w in words) or "Unknown"


class Resolver:
    """Alias registry + per-call resolution. Mutations write back to disk via save()."""

    def __init__(self, registry_path=ALIAS_REGISTRY_PATH):
        self.path = registry_path
        if registry_path.exists():
            self.registry = json.loads(registry_path.read_text(encoding="utf-8"))
        else:
            self.registry = {}
        for _, section in _TYPE_MAP.values():
            self.registry.setdefault(section, {})
        self._dirty = False

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._dirty = False

    # --- lookup helpers -------------------------------------------------

    def _surfaces(self, entry: dict) -> list[str]:
        return [entry["canonical"], *entry.get("aliases", [])]

    def _lookup(self, section: str, surface: str) -> str | None:
        """Exact -> normalized -> fuzzy within one registry section."""
        entries = self.registry[section]
        for eid, entry in entries.items():
            if surface in self._surfaces(entry):
                return eid
        norm = normalize(surface)
        if not norm:
            return None
        for eid, entry in entries.items():
            if any(normalize(s) == norm for s in self._surfaces(entry)):
                return eid
        best: tuple[float, str] | None = None
        for eid, entry in entries.items():
            for s in self._surfaces(entry):
                ratio = difflib.SequenceMatcher(None, norm, normalize(s)).ratio()
                if ratio >= FUZZY_THRESHOLD and (best is None or ratio > best[0]):
                    best = (ratio, eid)
        if best:
            log.info("fuzzy match (%.2f): %r -> %s [review]", best[0], surface, best[1])
            self._add_alias(section, best[1], surface)
            return best[1]
        return None

    def _add_alias(self, section: str, eid: str, surface: str) -> None:
        entry = self.registry[section][eid]
        if surface not in self._surfaces(entry):
            entry.setdefault("aliases", []).append(surface)
            self._dirty = True

    def _mint(self, section: str, prefix: str, surface: str, **extra) -> str:
        base = f"{prefix}_{slug(surface)}"
        eid = base
        n = 2
        while eid in self.registry[section]:  # id taken by a different canonical
            eid = f"{base}_{n}"
            n += 1
        self.registry[section][eid] = {"canonical": surface.strip(), "aliases": [], **extra}
        self._dirty = True
        log.info("new entity — review: %s (%r)", eid, surface)
        return eid

    # --- public API -----------------------------------------------------

    def resolve(self, surface: str, type_: str) -> str:
        """Surface form -> canonical id, minting a new id if nothing matches.

        For Character lookups, an exact/normalized player hit wins first (the
        model must never fork a player's real name into a Character node).
        Never matches across types.
        """
        prefix, section = _TYPE_MAP[type_]
        if type_ == "Character":
            player_hit = self._lookup_exact_or_norm("players", surface)
            if player_hit:
                return player_hit
        hit = self._lookup(section, surface)
        return hit or self._mint(section, prefix, surface)

    def _lookup_exact_or_norm(self, section: str, surface: str) -> str | None:
        entries = self.registry[section]
        norm = normalize(surface)
        for eid, entry in entries.items():
            if surface in self._surfaces(entry) or any(
                normalize(s) == norm for s in self._surfaces(entry)
            ):
                return eid
        return None

    def canonical(self, eid: str) -> str | None:
        for _, section in _TYPE_MAP.values():
            entry = self.registry[section].get(eid)
            if entry:
                return entry["canonical"]
        return None

    def bootstrap_cast(self, cast: list[tuple[str, str | None, bool]]) -> dict:
        """Register players/characters from the transcript's speaker labels.

        Returns {'players': {player_id: props}, 'characters': {char_id: props},
        'plays': {player_id: char_id}} for this session. GM gets a narrator
        Character (is_pc False, role GM) so in-fiction narration has a target.
        """
        players: dict[str, dict] = {}
        characters: dict[str, dict] = {}
        plays: dict[str, str] = {}
        for player, character, is_gm in cast:
            pid = self._lookup_exact_or_norm("players", player) or self._mint(
                "players", "PLAYER", player, **({"role": "GM"} if is_gm else {})
            )
            players[pid] = {"name": self.registry["players"][pid]["canonical"],
                           "role": "GM" if is_gm else "player"}
            if is_gm:
                cname = f"{player} (GM)"
                cid = self._lookup_exact_or_norm("characters", cname) or self._mint(
                    "characters", "CHAR", cname, is_pc=False, role="GM"
                )
                characters[cid] = {"name": cname, "is_pc": False, "role": "GM"}
            else:
                cid = self._lookup_exact_or_norm("characters", character) or self._mint(
                    "characters", "CHAR", character
                )
                characters[cid] = {"name": self.registry["characters"][cid]["canonical"],
                                   "is_pc": True, "role": "PC"}
            plays[pid] = cid
        return {"players": players, "characters": characters, "plays": plays}


def map_predicate(predicate: str) -> tuple[str, bool]:
    """(mapped_type, was_on_vocab). Off-vocab predicates coerce to RELATES_TO."""
    p = sanitize_predicate(predicate)
    p = PREDICATE_SYNONYMS.get(p, p)
    if p in ALLOWED_PREDICATES:
        return p, True
    return "RELATES_TO", False


def normalize_confidence(value: str) -> str:
    v = (value or "").strip().lower()
    return CONFIDENCE_MAP.get(v, v if v in ("high", "medium", "low") else "medium")


def resolve_graph(
    resolver: Resolver,
    extraction: GraphExtraction,
    session_id: str,
    cast_info: dict,
    seq: int = 0,
    evidence: dict | None = None,
    srd_index=None,
) -> dict:
    """GraphExtraction + cast -> {'entities': [...], 'edges': [...]} keyed on ids.

    Entities: {id, type, props}. Edges: {start_id, end_id, type, props}.
    Everything carries session_id + confidence (provenance, docs/evolution/04).
    With `evidence` (extract.py sidecar), every extracted fact gets an
    `evidence_chunks[]` property (chunk indices) — no separate Scene nodes/edges.
    Unresolvable endpoints drop the edge into state/failures/<sid>/dropped_edges.jsonl.
    """
    evidence = evidence or {}
    session_node_id = f"SESS_{session_id}"
    entities: dict[str, dict] = {}
    edges: list[dict] = []
    edge_keys: set[tuple] = set()
    surface_to_id: dict[str, str] = {}
    dropped: list[dict] = []
    off_vocab: list[str] = []

    def add_entity(eid: str, type_: str, props: dict) -> None:
        if eid in entities:  # first occurrence wins; aliases + evidence union
            old = entities[eid]["props"]
            aliases = sorted(set(old.get("aliases", [])) | set(props.get("aliases", [])))
            if aliases:
                old["aliases"] = aliases
            chunks = sorted(set(old.get("evidence_chunks", [])) | set(props.get("evidence_chunks", [])))
            if chunks:
                old["evidence_chunks"] = chunks
        else:
            entities[eid] = {"id": eid, "type": type_,
                             "props": {"session_id": session_id, "confidence": "medium", **props}}

    def add_edge(start: str, end: str, rtype: str, props: dict | None = None) -> None:
        key = (start, rtype, end)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({"start_id": start, "end_id": end, "type": rtype,
                      "props": {"session_id": session_id, "confidence": "high", **(props or {})}})

    # --- session + cast (deterministic, LLM-independent) ----------------
    add_entity(session_node_id, "Session", {"name": session_id, "date": session_id, "confidence": "high"})
    for pid, props in cast_info["players"].items():
        add_entity(pid, "Player", {**props, "confidence": "high"})
        surface_to_id[normalize(props["name"])] = pid
    for cid, props in cast_info["characters"].items():
        add_entity(cid, "Character", {**props, "confidence": "high"})
        surface_to_id[normalize(props["name"])] = cid
        add_edge(cid, session_node_id, "APPEARS_IN")
    for pid, cid in cast_info["plays"].items():
        add_edge(pid, cid, "PLAYS", {"seq": seq})
    # in-fiction edges landing on a Player re-route to their character (09)
    reroute = dict(cast_info["plays"])

    def chunks_of(field: str, key) -> list[int]:
        return sorted(set(evidence.get((field, key), [])))

    def register(surface: str, type_: str, props: dict, chunks: list[int]) -> str:
        eid = resolver.resolve(surface, type_)
        if eid.startswith("PLAYER_"):  # model coined a player's name as an entity
            eid = reroute.get(eid, eid)
            surface_to_id.setdefault(normalize(surface), eid)
            return eid
        props["name"] = resolver.canonical(eid) or surface  # stable across surface variants
        if chunks:
            props["evidence_chunks"] = chunks
        add_entity(eid, type_, props)
        surface_to_id.setdefault(normalize(surface), eid)
        return eid

    def endpoint(surface: str) -> str | None:
        """Endpoint -> id of an entity produced this session, or None (never mints)."""
        eid = surface_to_id.get(normalize(surface))
        if not eid:  # alias-registry hit (e.g. 'Lindo' for CHAR_LindoLaut), no minting
            for _, section in _TYPE_MAP.values():
                hit = resolver._lookup_exact_or_norm(section, surface)
                if hit and (hit in entities or hit in reroute):
                    eid = hit
                    break
        return reroute.get(eid, eid)

    # --- extracted entities ----------------------------------------------
    for c in extraction.characters:
        cid = register(c.name, "Character", {
            "name": c.name, "aliases": c.aliases,
            "is_pc": c.type.upper() == "PC", "role": c.type or "NPC",
        }, chunks_of("characters", c.name))
        add_edge(cid, session_node_id, "APPEARS_IN")
    for loc in extraction.locations:
        register(loc.name, "Location", {"name": loc.name, "description": loc.description},
                 chunks_of("locations", loc.name))
    for item in extraction.items:
        iid = register(item.name, "Item", {"name": item.name, "status": item.status},
                       chunks_of("items", item.name))
        if item.owner:
            owner_id = endpoint(item.owner)
            if owner_id:
                add_edge(iid, owner_id, "OWNED_BY")
    for q in extraction.quests:
        register(q.name, "Quest", {"name": q.name, "status": q.status},
                 chunks_of("quests", q.name))
    for f in extraction.factions:
        register(f.name, "Faction", {"name": f.name, "description": f.description},
                 chunks_of("factions", f.name))
    for e in extraction.events:
        eid = register(e.title, "Event", {"name": e.title, "summary": e.summary},
                       chunks_of("events", e.title))
        add_edge(eid, session_node_id, "IN_SESSION")
        if e.location:
            loc_id = endpoint(e.location)
            if loc_id:
                add_edge(eid, loc_id, "AT_LOCATION")
        for participant in e.participants:
            part_id = endpoint(participant)
            if part_id:
                add_edge(part_id, eid, "PARTICIPATED_IN")

    # --- rules, rolls, decisions (docs/evolution/05, WP5-6) ---------------
    for ru in extraction.rule_entities:
        chunks = chunks_of("rule_entities", ru.name)
        rid = srd_index.lookup(ru.name) if srd_index else None
        if rid:
            # shared, preloaded SRD node — link to it, never a per-session copy
            surface_to_id.setdefault(normalize(ru.name), rid)
        else:
            subtype = re.sub(r"[^A-Za-z0-9]", "", ru.subtype) or "System"
            rid = resolver._lookup("rules", ru.name) or resolver._mint(
                "rules", f"RULE_{subtype.upper()}", ru.name)
            props = {"name": resolver.canonical(rid) or ru.name, "subtype": ru.subtype,
                     "source": "session"}
            if chunks:
                props["evidence_chunks"] = chunks
            add_entity(rid, "RuleEntity", props)
            surface_to_id.setdefault(normalize(ru.name), rid)

    for roll in extraction.roll_events:
        rid = f"ROLL_{session_id}_{slug(roll.name)}"  # session-scoped: rolls never recur
        chunks = chunks_of("roll_events", roll.name)
        props = {"name": roll.name, "trait_or_action": roll.trait_or_action,
                 "outcome": roll.outcome, "confidence": normalize_confidence(roll.confidence)}
        if chunks:
            props["evidence_chunks"] = chunks
        add_entity(rid, "RollEvent", props)
        add_edge(rid, session_node_id, "IN_SESSION")
        surface_to_id.setdefault(normalize(roll.name), rid)
        if roll.roller:
            who = endpoint(roll.roller)
            if who:
                add_edge(who, rid, "ROLLED")
        if roll.target:
            tgt = endpoint(roll.target)
            if tgt and tgt != rid:
                add_edge(rid, tgt, "TARGETS")

    for dec in extraction.decisions:
        did = f"DEC_{session_id}_{slug(dec.name)}"  # session-scoped, like rolls
        chunks = chunks_of("decisions", dec.name)
        props = {"name": dec.name, "quote": dec.quote, "consequence": dec.consequence,
                 "confidence": normalize_confidence(dec.confidence)}
        if chunks:
            props["evidence_chunks"] = chunks
        add_entity(did, "Decision", props)
        add_edge(did, session_node_id, "IN_SESSION")
        surface_to_id.setdefault(normalize(dec.name), did)
        if dec.decided_by:
            who = endpoint(dec.decided_by)
            if who:
                add_edge(who, did, "DECIDED")

    # --- traits (docs/evolution/10, WP6b): recurring behavior aggregates
    # into one counted Trait node per character (store.py increments
    # KNOWN_FOR.count on re-occurrence), never N repeated Event nodes -------
    for tr in extraction.traits:
        char_id = endpoint(tr.character) if tr.character else None
        if not char_id:
            dropped.append({"subject": tr.character, "predicate": "KNOWN_FOR",
                            "object": tr.name, "reason": "unresolved character"})
            continue
        char_slug = char_id[len("CHAR_"):] if char_id.startswith("CHAR_") else slug(char_id)
        tid = f"TRAIT_{char_slug}_{slug(tr.name)}"
        add_entity(tid, "Trait", {"name": tr.name})
        add_edge(char_id, tid, "KNOWN_FOR")
        surface_to_id.setdefault(normalize(tr.name), tid)

    # --- relationships (endpoint validation, docs/evolution/03) ----------
    for r in extraction.relationships:
        start = endpoint(r.subject)
        end = endpoint(r.object)
        rtype, on_vocab = map_predicate(r.predicate)
        if not on_vocab:
            off_vocab.append(r.predicate)
        if not start or not end or start == end:
            dropped.append({"subject": r.subject, "predicate": r.predicate,
                            "object": r.object, "reason": "unresolved endpoint" if not (start and end) else "self-loop"})
            continue
        rel_chunks = chunks_of("relationships", (r.subject, r.predicate, r.object)) \
            or ([r.evidence] if r.evidence else [])
        add_edge(start, end, rtype, {
            "confidence": normalize_confidence(r.confidence),
            "evidence_chunks": rel_chunks,
            **({"original_predicate": sanitize_predicate(r.predicate)} if not on_vocab else {}),
        })

    if dropped:
        fail_dir = STATE_DIR / "failures" / session_id
        fail_dir.mkdir(parents=True, exist_ok=True)
        with (fail_dir / "dropped_edges.jsonl").open("a", encoding="utf-8") as f:
            for d in dropped:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        log.warning("%d edges dropped (unresolved endpoints) -> %s", len(dropped), fail_dir)
    if off_vocab:
        log.warning("%d off-vocab predicates coerced to RELATES_TO: %s",
                    len(off_vocab), sorted(set(off_vocab)))

    resolver.save()
    return {"entities": list(entities.values()), "edges": edges, "dropped": dropped}
