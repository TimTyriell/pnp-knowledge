"""All tunables for the pnp-graph pipeline."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TRANSCRIPT_DIR = REPO_ROOT / "transcripts"
STATE_DIR = REPO_ROOT / "state"

LLM_MODEL = "qwen3:14b"
CHUNK_SIZE = 3000
CHUNK_OVERLAP = 300

NEO4J_URL = "bolt://localhost:7687"
NEO4J_USER = "neo4j"

# Seeded vocabulary observed in a prior Claude-authored session report for this
# campaign (Session_Report_S02) — biases the local model toward reusing the same
# relation types instead of inventing new phrasing per chunk. Not a hard enum.
SUGGESTED_PREDICATES = [
    "MEMBER_OF", "OWNS", "HOSTILE_TO", "ALLY_OF", "LOCATED_IN", "TRIGGERED",
    "PARTICIPATED_IN", "RESULTED_IN", "TARGETS", "KNOWS", "FEARS", "MENTIONED_IN",
]
