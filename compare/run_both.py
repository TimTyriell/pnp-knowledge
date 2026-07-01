"""Run both transcript->graph pipelines on the same sessions, into two Neo4j DBMS.

  custom  (src/pnp_graph)                  -> bolt://localhost:7687  (typed schema nodes)
  ai-kg   (../ai-knowledge-graph, sibling) -> bolt://localhost:7688  (generic Entity triples)

The custom pipeline already writes :7687 unchanged. ai-knowledge-graph writes no
Neo4j of its own (HTML/JSON only), so this script also acts as its Neo4j sink:
it runs generate-graph.py to produce a triples JSON, then MERGEs those triples
into the :7688 DBMS.

Serial by design: per session it runs the custom pipeline to completion, THEN
ai-kg. Never two LLM jobs at once (single GPU / 12GB VRAM can't host two
qwen3:14b). "Parallel" means side-by-side comparison, not concurrent execution.

Usage:
    python compare/run_both.py [--only 2025-03-26] [--skip-custom] [--skip-aikg]

Prereqs (manual, see plan): both Neo4j DBMS started, NEO4J_PASSWORD set, Ollama
running with qwen3:14b, ai-kg deps installed (networkx pyvis python-louvain tomli
requests).
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))  # so we can import pnp_graph and reuse its helpers

from neo4j import GraphDatabase  # noqa: E402

from pnp_graph.chunking import ordered_sessions, session_id_from_path  # noqa: E402
from pnp_graph.store import get_password, sanitize_predicate  # noqa: E402

TRANSCRIPT_DIR = REPO_ROOT / "transcripts"
# ai-knowledge-graph lives as a sibling repo (c:\dev\pnp\ai-knowledge-graph),
# not nested under this one. Override with AIKG_DIR env if relocated again.
AIKG_DIR = Path(os.environ.get("AIKG_DIR", REPO_ROOT.parent / "ai-knowledge-graph"))
AIKG_CONFIG = REPO_ROOT / "compare" / "aikg_qwen.toml"
OUT_DIR = REPO_ROOT / "compare" / "out"

AIKG_NEO4J_URL = os.environ.get("AIKG_NEO4J_URL", "bolt://localhost:7688")
# Second DBMS may share the password or set its own.
AIKG_NEO4J_PASSWORD = os.environ.get("AIKG_NEO4J_PASSWORD")  # falls back below


def run_custom(session_id: str) -> None:
    """Custom pipeline for one session -> Neo4j :7687 (its own config)."""
    env = {**os.environ, "PYTHONPATH": str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    subprocess.run(
        [sys.executable, "-m", "pnp_graph.cli", "ingest", "--only", session_id],
        cwd=REPO_ROOT, env=env, check=True,
    )


def run_aikg_extract(txt_path: Path, session_id: str) -> Path:
    """ai-knowledge-graph extraction for one session -> triples JSON. Returns json path."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_out = OUT_DIR / f"{session_id}.html"
    json_out = html_out.with_suffix(".json")
    subprocess.run(
        [sys.executable, str(AIKG_DIR / "generate-graph.py"),
         "--input", str(txt_path),
         "--output", str(html_out),
         "--config", str(AIKG_CONFIG)],
        cwd=AIKG_DIR, check=True,
    )
    if not json_out.exists():
        raise RuntimeError(f"ai-kg produced no triples JSON for {session_id} (extraction likely failed)")
    return json_out


def _write_triples(tx, triples: list[dict], session_id: str) -> None:
    tx.run("CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")
    tx.run("MERGE (s:Session {id: $id})", id=session_id)
    for t in triples:
        if not isinstance(t, dict) or "subject" not in t or "object" not in t:
            continue
        rel = sanitize_predicate(str(t.get("predicate", "")))
        # rel is [A-Z0-9_] only (sanitize_predicate), safe to interpolate as rel type.
        tx.run(
            f"MERGE (a:Entity {{name: $s}}) "
            f"MERGE (b:Entity {{name: $o}}) "
            f"MERGE (a)-[r:`{rel}`]->(b) "
            f"SET r.inferred = $inferred, r.session_id = $sid",
            s=t["subject"], o=t["object"],
            inferred=bool(t.get("inferred", False)), sid=session_id,
        )


def load_aikg_to_neo4j(json_path: Path, session_id: str) -> int:
    """MERGE ai-kg triples into the :7688 DBMS. Idempotent. Returns triple count."""
    triples = json.loads(json_path.read_text(encoding="utf-8"))
    password = AIKG_NEO4J_PASSWORD or get_password()
    driver = GraphDatabase.driver(AIKG_NEO4J_URL, auth=("neo4j", password))
    try:
        driver.verify_connectivity()
        with driver.session() as db:
            db.execute_write(_write_triples, triples, session_id)
    finally:
        driver.close()
    return len(triples)


def main() -> None:
    ap = argparse.ArgumentParser(prog="run_both")
    ap.add_argument("--only", help="one session_id (date), e.g. 2025-03-26")
    ap.add_argument("--skip-custom", action="store_true")
    ap.add_argument("--skip-aikg", action="store_true")
    args = ap.parse_args()

    sessions = ordered_sessions(TRANSCRIPT_DIR)
    if args.only:
        sessions = [p for p in sessions if session_id_from_path(p) == args.only]
    if not sessions:
        print(f"No transcripts matched in {TRANSCRIPT_DIR}", file=sys.stderr)
        sys.exit(1)

    for path in sessions:
        sid = session_id_from_path(path)
        txt = path.with_suffix(".txt")
        print(f"\n{'='*60}\nSESSION {sid}\n{'='*60}")

        if not args.skip_custom:
            print(f"[custom] ingest --only {sid} -> :7687")
            run_custom(sid)

        if not args.skip_aikg:
            if not txt.exists():
                print(f"[ai-kg] SKIP {sid}: no .txt sibling at {txt}", file=sys.stderr)
                continue
            print(f"[ai-kg] extract {txt.name} -> triples")
            json_out = run_aikg_extract(txt, sid)
            n = load_aikg_to_neo4j(json_out, sid)
            print(f"[ai-kg] loaded {n} triples -> {AIKG_NEO4J_URL}")

    print("\nDone. Custom graph on :7687, ai-kg graph on :7688.")


if __name__ == "__main__":
    main()
