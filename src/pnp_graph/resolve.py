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
    ADJUDICATE_GRAY_BAND,
    ALIAS_REGISTRY_PATH,
    ALLOWED_PREDICATES,
    CONFIDENCE_MAP,
    EVENT_PREDICATES,
    GENERIC_MOB_TERMS,
    GENERIC_PLACE_TERMS,
    IDENTITY_PREDICATES,
    META_EVENT_TERMS,
    OOC_DENYLIST,
    PREDICATE_DOMAINS,
    PREDICATE_SYNONYMS,
    STATE_DIR,
    STATE_PREDICATES,
)
from .chunking import split_passages
from .schema import GraphExtraction
from .store import sanitize_predicate

log = logging.getLogger("pnp_graph.resolve")

FUZZY_THRESHOLD = 0.9
# Looser than FUZZY_THRESHOLD deliberately: GM-surface false positives just
# drop one edge (cheap), while false negatives leak ASR noise into the graph
# as a phantom Character (the CHAR_Kieler/CHAR_Dennis pattern). 'Deniz'
# vs 'Dennis' scores 0.73 — real cast names in this campaign score <=0.6.
GM_FUZZY_THRESHOLD = 0.7

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

# Sections whose new mints get a gray-band scan for the LLM adjudicator
# (audit v6). Events are ephemeral, players deterministic from the cast,
# rules SRD-link-only — none of them adjudicate.
_ADJUDICATED_SECTIONS = frozenset({"characters", "locations", "quests", "factions", "items"})

# Sections that resolve in-memory within a run but are NEVER loaded from or
# written to disk. An Event is a specific one-off happening — it never recurs
# across sessions, so persisting it only bloats the registry (was 831 entries)
# and risks falsely merging two different scenes with the same title in
# different sessions. Cleared on load, excluded on save.
_EPHEMERAL_SECTIONS = frozenset({"events"})

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


# \broll\b-style boundary so 'Schriftrolle' never matches; catches
# 'Cookie rolls on Presence', 'Presence roll initiated by Celin', 'würfelt'.
_ROLL_TITLE_RE = re.compile(r"\broll(s|ed|ing)?\b|\bw(ü|ue)rfel", re.IGNORECASE)


def event_gate(title: str, quest_norms: set[str], player_names: list[str]) -> str | None:
    """Deterministic Event filter (KG_Qualitaetsanalyse_S01 fix C backstop).

    Returns a drop reason, or None if the event may be minted. Prompt already
    asks for state-change events only; this catches what the model ignores:
    meta/rules talk, roll-shaped events (a bare roll is not a macro-Event), player names
    as actors, and events duplicating a quest of the same name.
    """
    t = title.casefold()
    if any(term in t for term in META_EVENT_TERMS):
        return "meta-event (rules/deliberation talk)"
    if _ROLL_TITLE_RE.search(title):
        return "roll-shaped event (a bare roll is not a macro-Event)"
    if any(re.search(rf"\b{re.escape(p)}\b", title, re.IGNORECASE) for p in player_names):
        return "player name as actor"
    if normalize(title) in quest_norms:
        return "duplicates quest of same name"
    return None


def is_out_of_world(surface: str) -> bool:
    """Deterministic backstop for stream/chat/VTT-tool noise the prompt asks the
    model to skip but a small chunk can still blend into the fiction (docs/evolution/
    KG_Qualitaetsanalyse_S01, e.g. a Twitch raid minted as an NPC)."""
    s = surface.casefold()
    return any(term in s for term in OOC_DENYLIST)


def is_generic_mob(surface: str) -> bool:
    """Deterministic backstop for combat-fodder adversaries the is_named_character
    schema gate misses (macro-graph, mirrors is_out_of_world). A numbered instance
    ('Wache 1') or any GENERIC_MOB_TERM appearing as a token substring ('goblin' in
    'Goblins'/'Goblin-Schütze') is a generic mob — no node. Conservative by design;
    a named boss survives by the model marking is_named_character=True upstream."""
    tokens = normalize(surface).split()
    if tokens and tokens[-1].isdigit():
        return True
    return any(term in tok for tok in tokens for term in GENERIC_MOB_TERMS)


def is_generic_place(surface: str) -> bool:
    """Deterministic backstop for the is_named_location gate: a bare stage-dressing
    common noun ('der Wald' -> 'wald') is not a macro-place. Whole-name match only
    (NOT substring) so a real compound name ('Nebeliger Wald') survives."""
    return normalize(surface) in GENERIC_PLACE_TERMS


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
        for section in _EPHEMERAL_SECTIONS:  # never carry events across runs
            self.registry[section] = {}
        self._dirty = False
        # gray-band identity candidates queued for the LLM adjudicator
        # (audit v6); drained once per session by adjudicate.adjudicate_session
        self.pending_candidates: list[dict] = []

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        out = {k: v for k, v in self.registry.items() if k not in _EPHEMERAL_SECTIONS}
        self.path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
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
        if section in _ADJUDICATED_SECTIONS:
            self.pending_candidates.extend(self._gray_candidates(section, eid, surface))
        return eid

    def _gray_candidates(self, section: str, eid: str, surface: str) -> list[dict]:
        """Same-section entries whose best fuzzy ratio against the new mint lands
        in ADJUDICATE_GRAY_BAND: too close to ignore, too far to auto-merge —
        the LLM adjudicator decides (audit v6). Pairs already judged distinct
        (`adjudicated_distinct` memo) are never re-asked."""
        lo, hi = ADJUDICATE_GRAY_BAND
        norm = normalize(surface)
        distinct = set(self.registry[section][eid].get("adjudicated_distinct", []))
        out = []
        for oid, entry in self.registry[section].items():
            if oid == eid or oid in distinct or eid in entry.get("adjudicated_distinct", []):
                continue
            best = max((difflib.SequenceMatcher(None, norm, normalize(s)).ratio()
                        for s in self._surfaces(entry)), default=0.0)
            if lo <= best < hi:
                out.append({"section": section, "new_id": eid, "surface": surface,
                            "existing_id": oid, "ratio": round(best, 2)})
        return out

    def drain_candidates(self) -> list[dict]:
        """Hand the queued identity candidates to the adjudicator, deduplicated
        per pair; an alias-conflict entry wins over a plain gray-band one for
        the same pair (it carries the surface to strip on a distinct verdict)."""
        by_key: dict[tuple, dict] = {}
        for c in self.pending_candidates:
            key = (c["section"], c["new_id"], c["existing_id"])
            if key not in by_key or c.get("source"):
                by_key[key] = c
        self.pending_candidates = []
        return list(by_key.values())

    def merge_entries(self, section: str, keep_id: str, drop_id: str) -> None:
        """Adjudicator-approved merge: drop_id's surfaces become keep_id aliases."""
        drop = self.registry[section].pop(drop_id, None)
        if not drop:
            return
        keep = self.registry[section][keep_id]
        for s in [drop["canonical"], *drop.get("aliases", [])]:
            if s not in self._surfaces(keep):
                keep.setdefault("aliases", []).append(s)
        self._dirty = True

    def mark_distinct(self, section: str, a: str, b: str) -> None:
        """Adjudicator said different entities — memo both ways, never re-ask."""
        for x, y in ((a, b), (b, a)):
            entry = self.registry[section].get(x)
            if entry is not None and y not in entry.get("adjudicated_distinct", []):
                entry.setdefault("adjudicated_distinct", []).append(y)
                self._dirty = True

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
            # PC vs NPC is deterministic from the cast, not the LLM's `role`
            # guess: bootstrap_cast pre-seeds every player-character as CHAR_
            # before extraction, so a lookup miss here is by definition a
            # non-cast character = an NPC. Both live in the `characters`
            # section (one id space); only the prefix distinguishes them, and
            # `type` stays "Character" for both (the predicate domains, QA, and
            # summarize/embed all key on type=='Character' as "is a person").
            hit = self._lookup(section, surface)
            return hit or self._mint(section, "NPC", surface)
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

    def known_world(self) -> dict[str, list[str]]:
        """Campaign gazetteer for the extraction prompt (audit v6 engine fix):
        canonical names + aliases per section, so the model resolves mentions to
        known canon at extraction time instead of re-minting ASR spelling
        variants (Breska/Breschka/Brechka) for the resolver to guess at later.
        """
        sections = {"Characters": "characters", "Locations": "locations",
                    "Factions": "factions", "Quests": "quests", "Items": "items"}
        out: dict[str, list[str]] = {}
        for label, section in sections.items():
            lines = []
            for entry in self.registry[section].values():
                aliases = [a for a in entry.get("aliases", []) if a][:4]
                lines.append(entry["canonical"]
                             + (f" (aka {', '.join(aliases)})" if aliases else ""))
            out[label] = lines
        return out

    def canonical(self, eid: str) -> str | None:
        for _, section in _TYPE_MAP.values():
            entry = self.registry[section].get(eid)
            if entry:
                return entry["canonical"]
        return None

    def bootstrap_cast(self, cast: list[tuple[str, str | None, bool]]) -> dict:
        """Register players/characters from the transcript's speaker labels.

        Returns {'players': {player_id: props}, 'characters': {char_id: props},
        'plays': {player_id: char_id}} for this session. The GM gets NO
        Character node (GM-is-world, KG_Qualitaetsanalyse_S01): narratively the
        GM does not exist — resolve_graph gives the GM player one DIRECTS edge
        to the Session and drops every other GM-touching edge.
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
                continue  # no GM character, no PLAYS — DIRECTS is added in resolve_graph
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


def predicate_class(predicate: str) -> str | None:
    """WP9 bitemporal classification: 'state' / 'event' / 'identity' / None.

    None (incl. RELATES_TO, off-vocab) gets no valid_from/valid_to.
    """
    if predicate in STATE_PREDICATES:
        return "state"
    if predicate in EVENT_PREDICATES:
        return "event"
    if predicate in IDENTITY_PREDICATES:
        return "identity"
    return None


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
    chunk_texts: list[str] | None = None,
) -> dict:
    """GraphExtraction + cast -> {'entities': [...], 'edges': [...]} keyed on ids.

    Entities: {id, type, props}. Edges: {start_id, end_id, type, props}.
    Everything carries session_id + confidence (provenance, docs/evolution/04).
    With `evidence` (extract.py sidecar), every extracted fact gets an
    `evidence_chunks[]` property (chunk indices) — no separate Scene nodes/edges.
    Unresolvable endpoints drop the edge into state/failures/<sid>/dropped_edges.jsonl.
    With `chunk_texts` (the raw extraction chunk texts, 1:1 with evidence_chunks
    indices — named distinctly from the `chunks` local used elsewhere in this
    function for a per-item evidence_chunks list, never the same thing), every
    chunk is split into small `Chunk` passages and embedded (WP13.5,
    docs/evolution/13) — the "vector = das Buch" half: MENTIONS edges link
    each passage to every entity whose evidence_chunks include that scene, so
    graph expansion from an entity can pull the verbatim source text.
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
        if eid in entities:  # first occurrence wins; aliases/evidence/notes union
            old = entities[eid]["props"]
            aliases = sorted(set(old.get("aliases", [])) | set(props.get("aliases", [])))
            if aliases:
                old["aliases"] = aliases
            chunks = sorted(set(old.get("evidence_chunks", [])) | set(props.get("evidence_chunks", [])))
            if chunks:
                old["evidence_chunks"] = chunks
            # pending_notes (WP13.4): a Character re-mentioned in a later chunk
            # THIS session must not lose an earlier chunk's note — order-preserving
            # dedup, not a set (the summarizer reads these as prose, order matters).
            notes = old.get("pending_notes", []) + [
                n for n in props.get("pending_notes", []) if n not in old.get("pending_notes", [])]
            if notes:
                old["pending_notes"] = notes
        else:
            base = {"session_id": session_id, "confidence": "medium"}
            if type_ == "Player":  # campaign-wide, not session-scoped (audit v6 F29);
                del base["session_id"]  # per-session history lives on PLAYS{seq}
            entities[eid] = {"id": eid, "type": type_, "props": {**base, **props}}

    def add_edge(start: str, end: str, rtype: str, props: dict | None = None) -> None:
        key = (start, rtype, end)
        if key in edge_keys:
            return
        edge_keys.add(key)
        props = dict(props or {})
        if predicate_class(rtype) == "state" and "valid_from" not in props:
            props["valid_from"] = seq
            # "last seen" stamp (audit_v7pro §7.4): lets a read tell "stale,
            # not refuted" from "actively re-confirmed" on the many-to-many
            # state edges that never force-close (ALLIED_WITH, MEMBER_OF, ...).
            props["last_observed_session"] = seq
        edges.append({"start_id": start, "end_id": end, "type": rtype,
                      "props": {"session_id": session_id, "confidence": "high", **props}})

    # --- session + cast (deterministic, LLM-independent) ----------------
    add_entity(session_node_id, "Session", {"name": session_id, "date": session_id, "confidence": "high"})
    for pid, props in cast_info["players"].items():
        add_entity(pid, "Player", {**props, "confidence": "high"})
        surface_to_id[normalize(props["name"])] = pid
    for cid, props in cast_info["characters"].items():
        add_entity(cid, "Character", {**props, "confidence": "high"})
        surface_to_id[normalize(props["name"])] = cid
        add_edge(cid, session_node_id, "IN_SESSION")
    for pid, cid in cast_info["plays"].items():
        add_edge(pid, cid, "PLAYS", {"seq": seq})
    # GM-is-world (KG_Qualitaetsanalyse_S01): the GM player's ONLY edge is
    # DIRECTS -> Session. Every extracted edge that touches a GM surface is
    # dropped — GM narration is world state, not an actor's deed.
    gm_pids = {pid for pid, p in cast_info["players"].items() if p.get("role") == "GM"}
    gm_norms = {normalize(s) for s in ("GM", "DM", "Spielleiter", "Dungeon Master", "Game Master")}
    for pid in gm_pids:
        add_edge(pid, session_node_id, "DIRECTS")
        entry = resolver.registry["players"].get(pid, {})
        gm_norms |= {normalize(s) for s in (entry.get("canonical", ""), *entry.get("aliases", [])) if s}

    def is_gm_surface(surface: str | None) -> bool:
        """Exact/normalized hit, or a fuzzy one (ASR mangles 'Deniz' -> 'Dennis'
        the same way it mangles PC names — reuse the resolver's own threshold)."""
        if not surface:
            return False
        n = normalize(surface)
        if n in gm_norms:
            return True
        return any(difflib.SequenceMatcher(None, n, g).ratio() >= GM_FUZZY_THRESHOLD for g in gm_norms)

    # in-fiction edges landing on a Player re-route to their character (09)
    reroute = dict(cast_info["plays"])

    def chunks_of(field: str, key) -> list[int]:
        return sorted(set(evidence.get((field, key), [])))

    def register(surface: str, type_: str, props: dict, chunks: list[int]) -> str:
        # Cross-type collision guard (run-2/3 QA blocker): the model naming the
        # same thing as Faction in one chunk and Location in another is ONE
        # entity (FACTION_/LOC_Auftraggeber, CHAR_/LOC_Esterossa). If this
        # surface already resolved to an entity THIS SESSION — any type —
        # reuse it: first-seen type wins, evidence unions, no second mint.
        # Session-scoped on purpose: registry-wide same-name-across-types
        # stays legal (Daggerheart the Location vs. Daggerheart the Faction).
        prior = surface_to_id.get(normalize(surface))
        prior = reroute.get(prior, prior)  # player surfaces land on their character
        if prior and prior in entities:
            # Pass the FULL props through (not just evidence_chunks): a cast
            # member (pre-registered in resolve_graph's cast bootstrap, bare
            # name/role/is_pc only) always hits this branch on every mention,
            # so this is the only path a PC's aliases/pending_notes ever reach
            # add_entity's merge — narrowing to evidence_chunks silently
            # dropped them for every PC, every session (caught via WP13.4's
            # pending_notes KeyError; likely dropped `description` the same
            # way before that).
            extra = dict(props)
            if chunks:
                extra["evidence_chunks"] = chunks
            add_entity(prior, entities[prior]["type"], extra)
            return prior
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
        """Endpoint -> id of an entity produced this session, or None (never mints).

        GM surfaces resolve to None: the GM has no in-fiction node (GM-is-world),
        so any edge the model aims at the GM dies here."""
        if is_gm_surface(surface):
            return None
        eid = surface_to_id.get(normalize(surface))
        if not eid:  # alias-registry hit (e.g. 'Lindo' for CHAR_LindoLaut), no minting
            for _, section in _TYPE_MAP.values():
                hit = resolver._lookup_exact_or_norm(section, surface)
                if hit and (hit in entities or hit in reroute):
                    eid = hit
                    break
        eid = reroute.get(eid, eid)
        return None if eid in gm_pids else eid

    # --- extracted entities ----------------------------------------------
    for c in extraction.characters:
        if is_out_of_world(c.name):
            dropped.append({"subject": c.name, "predicate": "IN_SESSION",
                            "object": session_node_id, "reason": "out-of-world (stream/chat/VTT)"})
            continue
        if is_gm_surface(c.name):  # GM-is-world: never a Character node
            dropped.append({"subject": c.name, "predicate": "IN_SESSION",
                            "object": session_node_id, "reason": "gm-is-world"})
            continue
        # Generic-mob gate (pay-to-mint, like is_named_artifact for Items): a
        # generic/unnamed adversary is identity-unstable — each goblin is a
        # different goblin, so minting one fabricates a recurring entity. Drop;
        # the horde is a Faction, the fight an Event, the detail a Chunk. Cast
        # PCs bypass — they are pre-registered from the transcript (in `entities`
        # already), so the gate only ever fires on LLM-extracted surfaces.
        is_cast_pc = surface_to_id.get(normalize(c.name)) in entities
        if not is_cast_pc and (not c.is_named_character or is_generic_mob(c.name)):
            dropped.append({"subject": c.name, "predicate": "IN_SESSION",
                            "object": session_node_id, "reason": "generic mob (not a named individual)"})
            continue
        cid = register(c.name, "Character", {
            "name": c.name, "aliases": c.aliases,
            # WP13.4: a raw per-scene note, never written straight to
            # `description` — pending_notes accumulates across sessions
            # (store.py) until `cli summarize-entities` folds it into one
            # cohesive `character_summary` and clears it. Prevents a later
            # session's note from silently replacing an earlier one (Item 1
            # only stopped an EMPTY note from blanking the summary, not a
            # non-empty one from overwriting it).
            "pending_notes": [c.description] if c.description else [],
            "is_pc": c.role.upper() == "PC", "role": c.role or "NPC",
        }, chunks_of("characters", c.name))
        if cid in gm_pids:  # registry resolved a GM alias to the GM player
            continue
        # alias-conflict adjudication (audit v6 F1): a model-supplied alias that
        # is already a DIFFERENT known character (Tindrail carrying 'Timrell')
        # smells like a wrong merge — the adjudicator decides; a 'distinct'
        # verdict strips the alias from this node's props again.
        for alias in c.aliases:
            hit = resolver._lookup_exact_or_norm("characters", alias)
            memo = resolver.registry["characters"].get(cid, {}).get("adjudicated_distinct", [])
            if hit and hit != cid and hit not in memo:
                resolver.pending_candidates.append({
                    "section": "characters", "new_id": cid, "surface": alias,
                    "existing_id": hit, "ratio": None, "source": "alias-conflict"})
        add_edge(cid, session_node_id, "IN_SESSION")
    for loc in extraction.locations:
        # named-place gate (pay-to-mint, like is_named_artifact): generic
        # stage-dressing ('der Wald', 'die Tür') is where a beat happens, not a
        # macro-place — no node. The beat lives in the scene Event/Chunk.
        if not loc.is_named_location or is_generic_place(loc.name):
            dropped.append({"subject": loc.name, "predicate": "LOCATED_IN",
                            "object": session_node_id, "reason": "generic place (not a named location)"})
            continue
        register(loc.name, "Location", {"name": loc.name, "description": loc.description},
                 chunks_of("locations", loc.name))
    for item in extraction.items:
        if not item.is_named_artifact:
            continue  # generic loot lives in the vector store, never a node
        iid = register(item.name, "Item", {"name": item.name, "status": item.status},
                       chunks_of("items", item.name))
        if item.owner:
            owner_id = endpoint(item.owner)
            if owner_id:
                add_edge(iid, owner_id, "OWNED_BY")
    quest_norms = set()
    for q in extraction.quests:
        register(q.name, "Quest", {"name": q.name, "status": q.status},
                 chunks_of("quests", q.name))
        quest_norms.add(normalize(q.name))
    for f in extraction.factions:
        register(f.name, "Faction", {"name": f.name, "description": f.description},
                 chunks_of("factions", f.name))
    player_names = [p["name"] for p in cast_info["players"].values()]
    for e in extraction.events:
        reason = event_gate(e.label, quest_norms, player_names)
        if reason:
            dropped.append({"subject": e.label, "predicate": "IN_SESSION",
                            "object": session_node_id, "reason": reason})
            continue
        eid = register(e.label, "Event",
                       {"name": e.label, "summary": e.summary,
                        "significance": e.narrative_significance_reasoning},
                       chunks_of("events", e.label))
        add_edge(eid, session_node_id, "IN_SESSION")
        if e.location:
            loc_id = endpoint(e.location)
            if loc_id:
                add_edge(eid, loc_id, "AT_LOCATION")
        for participant in e.participants:
            part_id = endpoint(participant)
            if part_id:
                add_edge(part_id, eid, "PARTICIPATED_IN")

    # --- rules (docs/evolution/05, WP5-6) --------------------------------
    for ru in extraction.rule_entities:
        rid = srd_index.lookup(ru.name) if srd_index else None
        if rid:
            # shared, preloaded SRD node — link to it, never a per-session copy
            surface_to_id.setdefault(normalize(ru.name), rid)
        else:
            # SRD-link-only (audit v6, rule 5): a rule the SRD index doesn't
            # know is table paraphrase, in-character banter ('Blizzard'), or
            # ASR noise ('Maus') — never minted. The drop log doubles as the
            # backlog for extending data/daggerheart_srd.json.
            dropped.append({"subject": ru.name, "predicate": "RULE_ENTITY",
                            "object": ru.subtype, "reason": "no SRD match"})

    # --- relationships (endpoint validation, docs/evolution/03) ----------
    for r in extraction.relationships:
        raw = sanitize_predicate(r.predicate)
        raw = PREDICATE_SYNONYMS.get(raw, raw)
        if raw == "OWNS":
            # Character -[OWNS]-> Item folds into the one ownership direction
            # this pipeline keeps, Item -[OWNED_BY]-> Character — WP9 needs a
            # single direction per fact so supersede has one edge to close.
            subject, obj, rtype, on_vocab = r.object, r.subject, "OWNED_BY", True
        else:
            subject, obj = r.subject, r.object
            rtype, on_vocab = map_predicate(r.predicate)
        start = endpoint(subject)
        end = endpoint(obj)
        if not on_vocab:
            off_vocab.append(r.predicate)
        if not start or not end or start == end:
            if not (start and end):
                reason = ("gm-is-world" if is_gm_surface(r.subject) or is_gm_surface(r.object)
                          else "unresolved endpoint")
            else:
                reason = "self-loop"
            dropped.append({"subject": r.subject, "predicate": r.predicate,
                            "object": r.object, "reason": reason})
            continue
        domains = PREDICATE_DOMAINS.get(rtype)
        if domains:
            src_types, dst_types = domains
            # SRD-linked RuleEntity endpoints are shared/preloaded, not written
            # into `entities` this session (see rule_entities loop above) — skip
            # the check rather than crash or false-positive on their type.
            start_type = entities.get(start, {}).get("type")
            end_type = entities.get(end, {}).get("type")
            if start_type and end_type and (start_type not in src_types or end_type not in dst_types):
                dropped.append({"subject": r.subject, "predicate": r.predicate, "object": r.object,
                                "reason": f"domain/range violation ({start_type} -{rtype}-> {end_type})"})
                continue
        # P-6: party cohesion is implicit, not topology. The model sometimes
        # emits ALLIED_WITH between two PCs — drop it deterministically. (KNOWS
        # is left alone: PC<->NPC social edges are valuable, per the audit.)
        if rtype == "ALLIED_WITH":
            if (entities.get(start, {}).get("props", {}).get("is_pc")
                    and entities.get(end, {}).get("props", {}).get("is_pc")):
                dropped.append({"subject": r.subject, "predicate": r.predicate,
                                "object": r.object, "reason": "PC<->PC party cohesion (implicit)"})
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

    # --- WP13.5: chunk-level passages for the vector store ("vector = das
    # Buch") — split AFTER every other entity is registered, so MENTIONS can
    # link a passage to everything whose evidence_chunks name that scene. -----
    if chunk_texts:
        mentionable = [(eid, rec) for eid, rec in entities.items()
                       if rec["props"].get("evidence_chunks")]
        n_passages = 0
        for i, chunk_text in enumerate(chunk_texts, start=1):
            for j, passage in enumerate(split_passages(chunk_text), start=1):
                cid = f"CHUNK_{session_id}_{i:03d}_{j:02d}"
                add_entity(cid, "Chunk", {
                    "name": f"{session_id} scene {i}.{j}", "text": passage, "scene_index": i,
                })
                add_edge(cid, session_node_id, "IN_SESSION")
                for eid, rec in mentionable:
                    if i in rec["props"]["evidence_chunks"]:
                        add_edge(cid, eid, "MENTIONS")
                n_passages += 1
        log.info("Session %s: %d chunk passages minted for vector retrieval", session_id, n_passages)

    resolver.save()
    return {"entities": list(entities.values()), "edges": edges, "dropped": dropped}
