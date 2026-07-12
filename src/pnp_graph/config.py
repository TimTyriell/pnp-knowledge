"""All tunables for the pnp-graph pipeline."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TRANSCRIPT_DIR = REPO_ROOT / "transcripts"
STATE_DIR = REPO_ROOT / "state"
DATA_DIR = REPO_ROOT / "data"
ALIAS_REGISTRY_PATH = DATA_DIR / "alias_registry.json"
SRD_PATH = DATA_DIR / "daggerheart_srd.json"

# Two extraction profiles (macro-graph migration): 'local' is the free/offline
# Ollama path, kept for dev smoke tests only — its NUM_CTX can't hold a
# megachunk. Real ingests run 'flagship' (DeepSeek API): a frontier model
# reading a whole scene at once, asked to over-summarize into macro-Events
# instead of a blow-by-blow (see docs/evolution). Select via env var, e.g. a
# VS Code launch config's "env": {"PNP_PROFILE": "flagship"}.
PROFILE = os.getenv("PNP_PROFILE", "local")
_PROFILES = {
    "local": {
        "PROVIDER": "ollama",
        "LLM_MODEL": "qwen3:14b",
        # 4000 chars ≈ 1k tokens/chunk (was 2000): the S01 quality analysis
        # traced micro-event inflation + context-blind entity duplicates to
        # ~250-token chunks ("every chunk must deliver something"). Still
        # well inside NUM_CTX.
        "CHUNK_SIZE": 4000,
        "CHUNK_OVERLAP": 600,
    },
    "flagship": {
        "PROVIDER": "deepseek",
        # flash (cheap) for testing, pro (better) for prod. Override via
        # DEEPSEEK_MODEL env. Old deepseek-chat/-reasoner ids retire 2026-07-24.
        "LLM_MODEL": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        # ~44000 chars ≈ 11k tokens: a whole 20-30 min scene in one chunk, so
        # the model over-summarizes into 1-2 macro-Events instead of a
        # blow-by-blow. Deliberately large — recall is traded for parsimony.
        "CHUNK_SIZE": 44000,
        "CHUNK_OVERLAP": 3000,
    },
}
if PROFILE not in _PROFILES:
    raise ValueError(f"Unknown PNP_PROFILE {PROFILE!r} — expected one of {sorted(_PROFILES)}")
_profile = _PROFILES[PROFILE]
PROVIDER = _profile["PROVIDER"]
LLM_MODEL = _profile["LLM_MODEL"]
CHUNK_SIZE = _profile["CHUNK_SIZE"]
CHUNK_OVERLAP = _profile["CHUNK_OVERLAP"]

EMBED_MODEL = "nomic-embed-text"  # docs/evolution/11, WP11 — always local regardless of PROFILE
EMBED_DIM = 768

# WP13.4 — GraphRAG-style entity summarization: rewriting a short bio from a
# few notes is a prose task, not structured extraction, so it doesn't need
# the flagship model — always local Ollama regardless of PROFILE (same
# reasoning as EMBED_MODEL), run as a separate step after ingest, not the
# per-scene hot path.
SUMMARIZER_MODEL = "qwen3:14b"

# WP13.5 — chunk-level vector index ("vector = das Buch"): extraction chunks
# (up to CHUNK_SIZE=44000 chars on flagship) are far too coarse a unit to
# embed directly — one vector over an entire scene is nearly useless for
# pinpoint semantic search. Split each chunk into small overlapping passages
# at this granularity for embedding, independent of the extraction profile.
PASSAGE_SIZE = 1500
PASSAGE_OVERLAP = 200

# audit_v7pro §8 #1 — DeepSeek prefix-cache: the per-chunk known-world gazetteer
# grows every scene, breaking the cacheable prompt prefix on every call. Refresh
# it only every N chunks (extract.py extract_session) so the prefix stays
# byte-identical across a window; the resolver's fuzzy+alias pass catches any
# spelling drift inside a window. Flagship-relevant; harmless on local.
KNOWN_WORLD_REFRESH_EVERY = 10

# audit_v7pro §8 #2 — model cascade: segment scenes with a deterministic
# silence-gap heuristic (chunking.heuristic_segment) instead of a second
# whole-transcript DeepSeek pass. Flip to True to restore the LLM segmenter
# (build_segmenter) as a fallback if heuristic boundaries prove too coarse.
USE_LLM_SEGMENTER = False

# Q4_K_M 14B long-range recall degrades well before Ollama's trained 40960 max;
# structured multi-entity extraction needs full recall per chunk, not gist, so
# stay conservative. num_ctx must cover prompt + CHUNK_SIZE + JSON output —
# pinned explicitly since Ollama's silent VRAM-based auto-default (4096) caused
# runaway generation loops (repeated context-shift/discard, never converging).
# Ollama-only; irrelevant when PROVIDER == "deepseek".
NUM_CTX = 8192

# hard cap per LLM call (both providers) so a runaway generation (see below)
# fails fast into _invoke_with_retry's retry/failure-dump path instead of
# hanging forever.
LLM_TIMEOUT_S = 300

# root cause of the runaway loops (confirmed via Ollama's server.log: n_decoded
# climbing past 19k tokens over 7m44s, repeated "slot context shift" instead of
# ever stopping): temperature=0 (argmax) + repeat_penalty=1.0 (disabled) lets
# json_schema-constrained decoding repeat the same array entry forever once it
# starts, since the grammar never forces the array to end. repeat_penalty
# discourages the repeat; num_predict is a hard token-count backstop so a loop
# that starts anyway still terminates well before another 7-minute stall.
# Ollama-only; irrelevant when PROVIDER == "deepseek".
REPEAT_PENALTY = 1.1
NUM_PREDICT = 4096

# Plain endpoint, not /beta: /beta's strict function-calling mode ignores our
# compound schema on large payloads (hallucinates a different one entirely —
# see extract.py's _structured_method) so it's not worth the tradeoff versus
# plain function-calling's occasional missed tool-call.
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
FLAGSHIP_MAX_TOKENS = 32768  # was 8192: too low for dense combat chunks, truncated JSON -> None

NEO4J_URL = "bolt://localhost:7687"  # container runs NEO4J_AUTH=none, no user/password

# Seeded vocabulary observed in a prior Claude-authored session report for this
# campaign (Session_Report_S02) — biases the local model toward reusing the same
# relation types instead of inventing new phrasing per chunk. Not a hard enum.
SUGGESTED_PREDICATES = [
    "MEMBER_OF", "OWNED_BY", "HOSTILE_TO", "ALLY_OF", "LOCATED_IN", "TRIGGERED",
    "PARTICIPATED_IN", "RESULTED_IN", "TARGETS", "KNOWS", "FEARS", "SUBQUEST_OF",
]

# Closed relationship vocabulary (docs/evolution/04). Enforced in resolve.py:
# model output maps through PREDICATE_SYNONYMS, then anything off-list is
# coerced to RELATES_TO and logged — never written as a new type.
ALLOWED_PREDICATES = {
    "IN_SESSION", "DIRECTS", "MEMBER_OF", "OWNED_BY",  # APPEARS_IN folded into IN_SESSION (P-5)
    "LOCATED_IN", "AT_LOCATION",
    "HAS_CLASS", "HAS_SUBCLASS", "HAS_ANCESTRY", "HAS_COMMUNITY", "USES_CARD",
    "HAS_FEATURE", "RUNS", "USES",
    "PARTICIPATED_IN", "TARGETS", "TRIGGERED", "RESULTED_IN",
    "INVOLVES",
    "KNOWS", "FEARS", "HOSTILE_TO", "ALLIED_WITH",
    "PLAYS", "RELATES_TO",
    "SUBQUEST_OF",  # Quest -> parent arc Quest (P-6/§6 sub-quest hierarchy)
    "TRUSTS", "BETRAYED", "KILLED", "FAMILY_OF",  # narrative-arc verbs (docs/evolution/11, WP9)
    "MENTIONS",  # Chunk -> any entity named in that passage (docs/evolution/13, WP13.5)
}
PREDICATE_SYNONYMS = {
    "ALLY_OF": "ALLIED_WITH",
    "HOSTILE": "HOSTILE_TO",
    "OWNED": "OWNED_BY",
    "IS_IN": "LOCATED_IN",
    "PART_OF": "MEMBER_OF",
    "RELATED_TO": "FAMILY_OF",  # RELATES_TO stays the distinct generic fallback
}

# Bitemporal edge classification (docs/evolution/11, WP9) — every predicate is
# exactly one of these three. Unclassified (incl. RELATES_TO and any
# off-vocab predicate) gets no valid_from/valid_to lifecycle: see
# resolve.predicate_class(). PLAYS is a state predicate conceptually but is
# EXEMPT from the generic lifecycle mechanics — its own per-session edge
# (docs/evolution/09) already is its history. OWNS was folded into OWNED_BY
# (the only ownership direction written now — resolve.py swaps endpoints for
# any model output still using OWNS) so the two didn't need independent
# supersede handling for the same fact.
STATE_PREDICATES = {
    "ALLIED_WITH", "HOSTILE_TO", "TRUSTS", "MEMBER_OF", "LOCATED_IN", "AT_LOCATION",
    "OWNED_BY", "KNOWS", "FEARS", "HAS_CLASS", "HAS_SUBCLASS", "USES_CARD", "PLAYS",
}
EVENT_PREDICATES = {
    "KILLED", "BETRAYED", "PARTICIPATED_IN", "TRIGGERED", "RESULTED_IN",
    "TARGETS", "IN_SESSION",
}
IDENTITY_PREDICATES = {"FAMILY_OF", "HAS_ANCESTRY", "HAS_COMMUNITY"}
STATE_PREDICATES_WITH_LIFECYCLE = STATE_PREDICATES - {"PLAYS"}

# Cardinality-one side per state predicate, used to auto-supersede (WP9): the
# endpoint that can only hold one *current* value at a time. Fact superseded
# when a new edge of the same type appears from/to that endpoint with a
# different value on the other side — the old edge's valid_to closes.
# Only genuinely EXCLUSIVE facts belong here (audit_v7pro §7.2 — position and
# ownership). Everything else is many-to-many and stays open: a plain read
# gates on `valid_to IS NULL`, and staleness on those is carried by
# `last_observed_session` (resolve.py) rather than a forced close.
# `source_types` (optional) restricts the supersede to those start-node types:
# LOCATED_IN is exclusive only for Character/Item POSITIONS — Location->Location
# (geography) and Faction->Location are stable and must never close.
# Deliberately NOT keyed (audit): AT_LOCATION / HAS_CLASS / HAS_SUBCLASS are
# STABLE (an event's place and a character's class don't move) — valid_from
# only; MEMBER_OF / ALLIED_WITH / HOSTILE_TO / TRUSTS / KNOWS / FEARS /
# USES_CARD are many-to-many.
STATE_PREDICATE_KEY = {
    "LOCATED_IN": {"side": "start", "source_types": {"Character", "Item"}},
    "OWNED_BY": {"side": "start"},
}

# Domain/range per predicate (docs/evolution/KG_Qualitaetsanalyse_S01, fix B):
# {predicate: (allowed source :Entity.type set, allowed target set)}. Enforced
# in resolve.py against the LLM's free-form `relationships` list only — the
# deterministic edges resolve_graph() writes itself (IN_SESSION, PLAYS,
# PARTICIPATED_IN, ...) are correct by construction and
# never run through this table. RELATES_TO is intentionally absent: it is the
# unconstrained catch-all fallback for off-vocab predicates.
PREDICATE_DOMAINS = {
    # IN_SESSION is the single provenance predicate for all types now (P-5,
    # APPEARS_IN folded in) — Character joins Event/Quest as a valid source.
    "IN_SESSION": ({"Event", "Quest", "Character"}, {"Session"}),
    "DIRECTS": ({"Player"}, {"Session"}),  # GM-is-world: the GM's ONLY edge
    "MEMBER_OF": ({"Character"}, {"Faction"}),
    "OWNED_BY": ({"Item"}, {"Character"}),
    "LOCATED_IN": ({"Location", "Character", "Item", "Faction"}, {"Location"}),
    "AT_LOCATION": ({"Event"}, {"Location"}),
    "HAS_CLASS": ({"Character"}, {"RuleEntity"}),
    "HAS_SUBCLASS": ({"Character"}, {"RuleEntity"}),
    "HAS_ANCESTRY": ({"Character"}, {"RuleEntity"}),
    "HAS_COMMUNITY": ({"Character"}, {"RuleEntity"}),
    "USES_CARD": ({"Character"}, {"RuleEntity"}),
    "HAS_FEATURE": ({"Character"}, {"RuleEntity"}),
    "RUNS": ({"Character"}, {"RuleEntity"}),
    "USES": ({"Character"}, {"Item", "RuleEntity"}),
    "PARTICIPATED_IN": ({"Character"}, {"Event"}),
    "TARGETS": ({"Event"}, {"Character", "Item", "Location"}),
    "TRIGGERED": ({"Character", "Event"}, {"Event", "Character"}),
    "RESULTED_IN": ({"Event"}, {"Event", "Item", "Quest"}),
    "SUBQUEST_OF": ({"Quest"}, {"Quest"}),  # sub-quest -> parent campaign arc (§6)
    "INVOLVES": ({"Event", "Quest"}, {"Character", "Item", "Location", "Faction"}),
    "KNOWS": ({"Character"}, {"Character"}),
    "FEARS": ({"Character"}, {"Character", "Faction"}),
    "HOSTILE_TO": ({"Character", "Faction"}, {"Character", "Faction"}),
    "ALLIED_WITH": ({"Character", "Faction"}, {"Character", "Faction"}),
    "PLAYS": ({"Player"}, {"Character"}),
    "TRUSTS": ({"Character"}, {"Character"}),
    "BETRAYED": ({"Character"}, {"Character"}),
    "KILLED": ({"Character"}, {"Character"}),
    "FAMILY_OF": ({"Character"}, {"Character"}),
    "MENTIONS": ({"Chunk"}, {"Character", "Location", "Item", "Quest", "Event", "Faction",
                             "RuleEntity"}),
}

# LLM identity adjudication (audit v6): a new mint whose best fuzzy ratio
# against an existing same-type entry lands in this band is too close to
# ignore but too far to auto-merge (FUZZY_THRESHOLD) — the pair goes to the
# adjudicator LLM, which judges by role/description context (Breska/Breschka
# merges; Tindrael/Timrell stays split). Verdicts land in the alias registry
# and state/review/<sid>/adjudications.jsonl.
ADJUDICATE_GRAY_BAND = (0.7, 0.9)

# Report used German confidence tokens; local prompt emits English. Converge both.
CONFIDENCE_MAP = {"hoch": "high", "mittel": "medium", "niedrig": "low"}

# Deterministic event gate (KG_Qualitaetsanalyse_S01 §1 "Event-Begriff zu weit"):
# an Event needs a state change. Titles matching these casefolded substrings are
# meta/deliberation/rules-talk, not events — dropped in resolve.py. Roll-shaped
# titles are dropped too (a bare dice roll isn't a macro-Event; the detail lives
# in the vector store); the \broll\b regex lives in resolve.py so 'Schriftrolle'
# never matches.
META_EVENT_TERMS = (
    "clarification", "explanation", "explain", "mention", "considers",
    "questions", "discussion", "klarstellung", "erklärt", "erlaeutert",
    "erläutert", "regel",
    # session-opening recaps/introductions change no world state (audit v6 F15)
    "introduction", "vorstellung",
)

# Out-of-fiction noise (docs/evolution/KG_Qualitaetsanalyse_S01): stream/chat/VTT-tool
# talk that a small-context chunk can blend into the scene (e.g. a Twitch raid
# announcement minted as an NPC). Substring match, casefolded, against a Character
# surface name in resolve.py — never a full deny of the word elsewhere in text.
OOC_DENYLIST = (
    "twitch", "discord", "raid", "stream", "vtt", "talespire",
    "kinomodus", "turn-based-mode", "kampfmodus", "chat",
)

# Generic-mob backstop (macro-graph, mirrors is_named_artifact for Items): a
# combat-fodder adversary is identity-unstable (each goblin is a different
# goblin) so it never earns a node — the horde is a Faction, the fight an Event.
# The schema's is_named_character gate is the primary dial; this deterministic
# net catches the unmistakable combat types the model still mints. Kept
# CONSERVATIVE on purpose (no 'bauer'/'magier' — those are often named NPCs);
# folded/normalized tokens (resolve.is_generic_mob), so 'goblin' also hits
# 'Goblins'/'Goblin-Schütze'. Named bosses survive via is_named_character=True.
GENERIC_MOB_TERMS = (
    "goblin", "bugbear", "skelett", "wildschwein", "kreatur",
    "zombie", "ork", "bandit", "wache",
)

# Generic-place backstop for the is_named_location gate. Matched against the
# WHOLE normalized name (resolve.is_generic_place), NOT substrings — so bare
# stage-dressing ('der Wald' -> 'wald') drops while a real compound place
# ('Nebeliger Wald', 'Haus des Händlers') is left to the schema gate. Kept
# short and unmistakable; ambiguous heads (Berg/Haus/Dorf/Raum) are NOT here —
# those get judged by is_named_location upstream.
GENERIC_PLACE_TERMS = frozenset({
    "wald", "baum", "baeume", "stein", "steine", "mauer", "mauern", "wand",
    "tuer", "dach", "treppe", "treppen", "nebel", "blume", "blumen", "kisten",
    "kiste", "boden", "natur", "nature", "bruecke", "wasser", "statue",
})
