"""All tunables for the pnp-graph pipeline."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TRANSCRIPT_DIR = REPO_ROOT / "transcripts"
STATE_DIR = REPO_ROOT / "state"
DATA_DIR = REPO_ROOT / "data"
ALIAS_REGISTRY_PATH = DATA_DIR / "alias_registry.json"
SRD_PATH = DATA_DIR / "daggerheart_srd.json"

LLM_MODEL = "qwen3:14b"
EMBED_MODEL = "nomic-embed-text"  # docs/evolution/11, WP11 — ~0.3 GB, co-resides with LLM_MODEL
EMBED_DIM = 768
# 4000 chars ≈ 1k tokens/chunk (was 2000): the S01 quality analysis traced
# micro-event inflation + context-blind entity duplicates to ~250-token chunks
# ("every chunk must deliver something"). Still well inside NUM_CTX.
CHUNK_SIZE = 4000
CHUNK_OVERLAP = 600

# Q4_K_M 14B long-range recall degrades well before Ollama's trained 40960 max;
# structured multi-entity extraction needs full recall per chunk, not gist, so
# stay conservative. num_ctx must cover prompt + CHUNK_SIZE + JSON output —
# pinned explicitly since Ollama's silent VRAM-based auto-default (4096) caused
# runaway generation loops (repeated context-shift/discard, never converging).
NUM_CTX = 8192

# hard cap per LLM call so a runaway generation (see below) fails fast into
# _invoke_with_retry's retry/failure-dump path instead of hanging forever.
LLM_TIMEOUT_S = 300

# root cause of the runaway loops (confirmed via Ollama's server.log: n_decoded
# climbing past 19k tokens over 7m44s, repeated "slot context shift" instead of
# ever stopping): temperature=0 (argmax) + repeat_penalty=1.0 (disabled) lets
# json_schema-constrained decoding repeat the same array entry forever once it
# starts, since the grammar never forces the array to end. repeat_penalty
# discourages the repeat; num_predict is a hard token-count backstop so a loop
# that starts anyway still terminates well before another 7-minute stall.
REPEAT_PENALTY = 1.1
NUM_PREDICT = 4096

NEO4J_URL = "bolt://localhost:7687"  # container runs NEO4J_AUTH=none, no user/password

# Seeded vocabulary observed in a prior Claude-authored session report for this
# campaign (Session_Report_S02) — biases the local model toward reusing the same
# relation types instead of inventing new phrasing per chunk. Not a hard enum.
SUGGESTED_PREDICATES = [
    "MEMBER_OF", "OWNS", "HOSTILE_TO", "ALLY_OF", "LOCATED_IN", "TRIGGERED",
    "PARTICIPATED_IN", "RESULTED_IN", "TARGETS", "KNOWS", "FEARS",
]

# Closed relationship vocabulary (docs/evolution/04). Enforced in resolve.py:
# model output maps through PREDICATE_SYNONYMS, then anything off-list is
# coerced to RELATES_TO and logged — never written as a new type.
ALLOWED_PREDICATES = {
    "IN_SESSION", "APPEARS_IN", "DIRECTS", "MEMBER_OF", "OWNS", "OWNED_BY",
    "LOCATED_IN", "AT_LOCATION",
    "HAS_CLASS", "HAS_SUBCLASS", "HAS_ANCESTRY", "HAS_COMMUNITY", "USES_CARD",
    "HAS_FEATURE", "RUNS", "USES",
    "PARTICIPATED_IN", "DECIDED", "ROLLED", "TARGETS", "TRIGGERED", "RESULTED_IN",
    "INVOLVES",
    "KNOWS", "FEARS", "HOSTILE_TO", "ALLIED_WITH",
    "PLAYS", "RELATES_TO",
    "KNOWN_FOR",  # Character -> Trait, count-incrementing (docs/evolution/10, WP6b)
    "TRUSTS", "BETRAYED", "KILLED", "FAMILY_OF",  # narrative-arc verbs (docs/evolution/11, WP9)
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
# exactly one of these three. Unclassified (incl. RELATES_TO, KNOWN_FOR, and
# any off-vocab predicate) gets no valid_from/valid_to lifecycle: see
# resolve.predicate_class(). PLAYS is a state predicate conceptually but is
# EXEMPT from the generic lifecycle mechanics — its own per-session edge
# (docs/evolution/09) already is its history.
STATE_PREDICATES = {
    "ALLIED_WITH", "HOSTILE_TO", "TRUSTS", "MEMBER_OF", "LOCATED_IN", "AT_LOCATION",
    "OWNS", "OWNED_BY", "KNOWS", "FEARS", "HAS_CLASS", "HAS_SUBCLASS", "USES_CARD", "PLAYS",
}
EVENT_PREDICATES = {
    "KILLED", "BETRAYED", "PARTICIPATED_IN", "TRIGGERED", "RESULTED_IN", "ROLLED",
    "TARGETS", "DECIDED", "APPEARS_IN", "IN_SESSION",
}
IDENTITY_PREDICATES = {"FAMILY_OF", "HAS_ANCESTRY", "HAS_COMMUNITY"}
STATE_PREDICATES_WITH_LIFECYCLE = STATE_PREDICATES - {"PLAYS"}

# Domain/range per predicate (docs/evolution/KG_Qualitaetsanalyse_S01, fix B):
# {predicate: (allowed source :Entity.type set, allowed target set)}. Enforced
# in resolve.py against the LLM's free-form `relationships` list only — the
# deterministic edges resolve_graph() writes itself (APPEARS_IN, PLAYS, ROLLED,
# DECIDED, PARTICIPATED_IN, KNOWN_FOR, ...) are correct by construction and
# never run through this table. RELATES_TO is intentionally absent: it is the
# unconstrained catch-all fallback for off-vocab predicates.
PREDICATE_DOMAINS = {
    "IN_SESSION": ({"Event", "RollEvent", "Decision", "Quest"}, {"Session"}),
    "APPEARS_IN": ({"Character"}, {"Session"}),
    "DIRECTS": ({"Player"}, {"Session"}),  # GM-is-world: the GM's ONLY edge
    "MEMBER_OF": ({"Character"}, {"Faction"}),
    "OWNS": ({"Character"}, {"Item"}),
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
    "DECIDED": ({"Character"}, {"Decision"}),
    "ROLLED": ({"Character"}, {"RollEvent"}),
    "TARGETS": ({"Event", "RollEvent"}, {"Character", "Item", "Location"}),
    "TRIGGERED": ({"Character", "Decision", "Event"}, {"Event", "Character"}),
    "RESULTED_IN": ({"Event", "Decision", "RollEvent"}, {"Event", "Item", "Quest"}),
    "INVOLVES": ({"Event", "Quest"}, {"Character", "Item", "Location", "Faction"}),
    "KNOWS": ({"Character"}, {"Character"}),
    "FEARS": ({"Character"}, {"Character", "Faction"}),
    "HOSTILE_TO": ({"Character", "Faction"}, {"Character", "Faction"}),
    "ALLIED_WITH": ({"Character", "Faction"}, {"Character", "Faction"}),
    "PLAYS": ({"Player"}, {"Character"}),
    "KNOWN_FOR": ({"Character"}, {"Trait"}),
    "TRUSTS": ({"Character"}, {"Character"}),
    "BETRAYED": ({"Character"}, {"Character"}),
    "KILLED": ({"Character"}, {"Character"}),
    "FAMILY_OF": ({"Character"}, {"Character"}),
}

# Report used German confidence tokens; local prompt emits English. Converge both.
CONFIDENCE_MAP = {"hoch": "high", "mittel": "medium", "niedrig": "low"}

# Deterministic event gate (KG_Qualitaetsanalyse_S01 §1 "Event-Begriff zu weit"):
# an Event needs a state change. Titles matching these casefolded substrings are
# meta/deliberation/rules-talk, not events — dropped in resolve.py. Roll-shaped
# titles are dropped too (RollEvent already covers them); the \broll\b regex
# lives in resolve.py so 'Schriftrolle' never matches.
META_EVENT_TERMS = (
    "clarification", "explanation", "explain", "mention", "considers",
    "questions", "discussion", "klarstellung", "erklärt", "erlaeutert",
    "erläutert", "regel",
)

# Closed RuleEntity subtype enum (KG_Qualitaetsanalyse_S01 §1 "subtype-Wildwuchs").
# Compared casefolded with an optional 'game' prefix stripped, so 'game-mechanic'
# and 'GameSystem' pass as Mechanic/System while 'diceroll', 'weapon trait',
# 'attribute', 'game-rule' etc. are dropped (real rules belong in the SRD file).
RULE_SUBTYPES = {
    "class", "subclass", "ancestry", "community", "domaincard",
    "classfeature", "feature", "adversary", "system", "mechanic", "trait",
}

# Out-of-fiction noise (docs/evolution/KG_Qualitaetsanalyse_S01): stream/chat/VTT-tool
# talk that a small-context chunk can blend into the scene (e.g. a Twitch raid
# announcement minted as an NPC). Substring match, casefolded, against a Character
# surface name in resolve.py — never a full deny of the word elsewhere in text.
OOC_DENYLIST = (
    "twitch", "discord", "raid", "stream", "vtt", "talespire",
    "kinomodus", "turn-based-mode", "kampfmodus", "chat",
)
