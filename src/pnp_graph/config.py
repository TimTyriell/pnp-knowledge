"""All tunables for the pnp-graph pipeline."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TRANSCRIPT_DIR = REPO_ROOT / "transcripts"
STATE_DIR = REPO_ROOT / "state"

LLM_MODEL = "qwen3:14b"
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
