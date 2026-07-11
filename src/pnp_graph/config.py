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
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200

# Q4_K_M 14B long-range recall degrades well before Ollama's trained 40960 max;
# structured multi-entity extraction needs full recall per chunk, not gist, so
# stay conservative. num_ctx must cover prompt + CHUNK_SIZE + JSON output —
# pinned explicitly since Ollama's silent VRAM-based auto-default (4096) caused
# runaway generation loops (repeated context-shift/discard, never converging).
NUM_CTX = 8192

NEO4J_URL = "bolt://localhost:7687"  # container runs NEO4J_AUTH=none, no user/password

# Seeded vocabulary observed in a prior Claude-authored session report for this
# campaign (Session_Report_S02) — biases the local model toward reusing the same
# relation types instead of inventing new phrasing per chunk. Not a hard enum.
SUGGESTED_PREDICATES = [
    "MEMBER_OF", "OWNS", "HOSTILE_TO", "ALLY_OF", "LOCATED_IN", "TRIGGERED",
    "PARTICIPATED_IN", "RESULTED_IN", "TARGETS", "KNOWS", "FEARS", "MENTIONED_IN",
]

# Closed relationship vocabulary (docs/evolution/04). Enforced in resolve.py:
# model output maps through PREDICATE_SYNONYMS, then anything off-list is
# coerced to RELATES_TO and logged — never written as a new type.
ALLOWED_PREDICATES = {
    "IN_SESSION", "EVIDENCED_IN", "APPEARS_IN", "MEMBER_OF", "OWNS", "OWNED_BY",
    "LOCATED_IN", "AT_LOCATION",
    "HAS_CLASS", "HAS_SUBCLASS", "HAS_ANCESTRY", "HAS_COMMUNITY", "USES_CARD",
    "HAS_FEATURE", "RUNS", "USES",
    "PARTICIPATED_IN", "DECIDED", "ROLLED", "TARGETS", "TRIGGERED", "RESULTED_IN",
    "INVOLVES", "MENTIONED_IN",
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
    "TARGETS", "DECIDED", "MENTIONED_IN", "APPEARS_IN", "IN_SESSION", "EVIDENCED_IN",
}
IDENTITY_PREDICATES = {"FAMILY_OF", "HAS_ANCESTRY", "HAS_COMMUNITY"}
STATE_PREDICATES_WITH_LIFECYCLE = STATE_PREDICATES - {"PLAYS"}

# Report used German confidence tokens; local prompt emits English. Converge both.
CONFIDENCE_MAP = {"hoch": "high", "mittel": "medium", "niedrig": "low"}
