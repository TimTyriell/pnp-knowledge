"""CLI: python -m pnp_graph.cli ingest [--only DATE]

status / reset-session / --dry-run land in later phases.
"""

import argparse
import logging

from .config import TRANSCRIPT_DIR
from .ingest import ingest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("neo4j").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(prog="pnp_graph")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="extract sessions oldest->newest into Neo4j")
    p_ingest.add_argument("--dir", default=str(TRANSCRIPT_DIR), help="transcript directory")
    p_ingest.add_argument("--only", help="ingest only this session_id (date), e.g. 2025-04-01")

    p_rec = sub.add_parser("reconcile-report",
                           help="diff the hand-authored report graph vs the local graph")
    p_rec.add_argument("session", help="session_id (date), e.g. 2025-03-26")

    p_ask = sub.add_parser("ask", help="ask a question against the graph (retrieval + local LLM)")
    p_ask.add_argument("question")
    p_ask.add_argument("--k", type=int, default=8, help="top-k seed entities")
    p_ask.add_argument("--as-of", type=int, default=None,
                       help="answer as of this session seq instead of the current state")

    args = parser.parse_args()
    if args.cmd == "ingest":
        from pathlib import Path
        ingest(Path(args.dir), only=args.only)
    elif args.cmd == "reconcile-report":
        from .reconcile import print_reconciliation
        print_reconciliation(args.session)
    elif args.cmd == "ask":
        from .retrieve import ask
        from .store import connect
        driver = connect()
        try:
            print(ask(driver, args.question, k=args.k, as_of_session=args.as_of))
        finally:
            driver.close()


if __name__ == "__main__":
    main()
