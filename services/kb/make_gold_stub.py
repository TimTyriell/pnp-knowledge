#!/usr/bin/env python
"""Emit a hand-labelling stub for one session, prefilled from the extraction.

There is no ground truth for what the LLM *should* have extracted, so every
quality number in this repo measures the shape of the output rather than
whether it is correct. Closing that needs hand-labelled sessions, and the
cheapest honest way to get them is to correct a draft rather than type one
from scratch.

    python make_gold_stub.py 2025-03-26 > tests/data/gold/2025-03-26.yaml

Then edit the file: delete entities the model invented, fix wrong names and
types, and add the ones it missed. The `verdict:` field on each line is the
only thing you have to touch -- see the header written into the stub.

Read docs/architecture/PIPELINE.md section 10 before using the result.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pnp_okf.config import DeepSeekConfig
from pnp_okf.extract import _cache_key, _cache_path, _load_cached
from pnp_okf.ingest import load_transcripts

HERE = Path(__file__).resolve().parent
TRANSCRIPTS = HERE.parents[2] / "pnp-crawl" / "transcripts_final"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    wanted = argv[1]

    # Entity names are German. Redirecting stdout on Windows otherwise encodes
    # them in the console codepage and the YAML comes back undecodable.
    sys.stdout.reconfigure(encoding="utf-8")

    cfg = DeepSeekConfig.from_env()
    matches = [
        t
        for t in load_transcripts(TRANSCRIPTS)
        if wanted in (t.session_id, t.date) or t.session_id.startswith(wanted)
    ]
    if not matches:
        print(f"No transcript matching {wanted!r}", file=sys.stderr)
        return 1
    transcript = matches[0]

    key = _cache_key(transcript, cfg)
    extraction = _load_cached(_cache_path(HERE / ".cache", transcript, key), key)
    if extraction is None:
        print(
            f"No cached extraction for {transcript.session_id}. Extract it first "
            "(costs money) or pick a session that is already cached.",
            file=sys.stderr,
        )
        return 1

    print(f"# Hand-labelled ground truth for {transcript.date}.")
    print("#")
    print("# Prefilled from the cached extraction -- CORRECT IT, do not trust it.")
    print("# For each entity set verdict to one of:")
    print("#   ok      - the model was right (name and type both)")
    print("#   wrong   - hallucinated, or not actually an entity  -> counts against precision")
    print("#   rename  - real entity, wrong name; put the right one in `should_be`")
    print("# Then ADD any entity the model missed with `verdict: missed`,")
    print("# which is what makes recall measurable. Missing entities are the")
    print("# half no amount of output-shape checking can see.")
    print("#")
    print(f"# Source: {transcript.url}")
    print()
    print("# Flip this to true once you have actually been through the list.")
    print("# While it is false the quality test refuses to score this file --")
    print("# an unreviewed stub is all 'ok', which would report perfect")
    print("# precision and recall from labels nobody checked.")
    print("reviewed: false")
    print()
    print(f"session_id: {transcript.session_id}")
    print(f"date: '{transcript.date}'")
    print("entities:")
    for m in extraction.entities:
        print(f"  - name: {m.name!r}")
        print(f"    type: {m.type.value}")
        print(f"    citation_ts: '{m.citation_ts}'")
        print("    verdict: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
