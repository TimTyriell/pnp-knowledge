"""Propose merge: rules for near-duplicate concepts. Read-only, no LLM.

The synthesizer often names a near-duplicate in the first sentence of a
concept's body ("Tarkia (auch [Tarkir](/locations/tarkir.md))"). Identity
ignores that signal -- it comes only from the extracted names -- so the pair
survives every run. This script reads the signal back out: a link in a
concept's first paragraph to a concept in the same directory, either in the
explicit "(auch [...])" form or with a similar title, is a candidate pair.

Proposals are printed as merge: lines for a human to rule on. Nothing is
written, and pairs already in never_merge: are skipped.

    python dup_doctor.py
"""

from __future__ import annotations

import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # services/kb
sys.path.insert(0, str(ROOT / "src"))

from pnp_okf.okf import split_document  # noqa: E402
from pnp_okf.resolve import _load_never_merge_pairs  # noqa: E402

KNOWLEDGE = ROOT.parent.parent / "knowledge"
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
SIMILAR = 0.75
LINK_RE = re.compile(r"\[([^\]]+)\]\(/?([^)\s]+?)\.md\)")
AUCH_RE = re.compile(r"\(auch \[([^\]]+)\]\((/[^)]+)\.md\)")


def similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    return a in b or b in a or SequenceMatcher(None, a, b).ratio() >= SIMILAR


def main() -> int:
    # Sessions are excluded: a session page is a dated log, not a concept, and
    # two sessions naming each other in their first line is not a duplicate.
    docs: dict[str, tuple[dict, str]] = {}
    for path in BUNDLE.rglob("*.md"):
        if path.name in ("index.md", "log.md"):
            continue
        cid = path.relative_to(BUNDLE).with_suffix("").as_posix()
        if cid.startswith("sessions/"):
            continue
        docs[cid] = split_document(path.read_text(encoding="utf-8"))

    titles = {cid: str(fm.get("title") or "") for cid, (fm, _) in docs.items()}
    # The survivor of a merge is the better-attested concept, mirroring the
    # resolver's own preference for the id with more mentions.
    sources = {cid: len(fm.get("sources") or []) for cid, (fm, _) in docs.items()}
    never = {frozenset(group) for group in _load_never_merge_pairs(REGISTRY)}

    pairs: dict[frozenset[str], str] = {}
    for cid, (_, body) in docs.items():
        first = body.split("\n\n", 1)[0]
        directory = cid.rsplit("/", 1)[0]
        auch = {target.lstrip("/") for _, target in AUCH_RE.findall(first)}
        for _, target in LINK_RE.findall(first):
            target = target.lstrip("/")
            if target == cid or target not in docs:
                continue
            if target.rsplit("/", 1)[0] != directory:
                continue
            if target in auch:
                why = "auch"
            elif similar(titles[cid], titles[target]):
                why = "similar"
            else:
                continue
            pair = frozenset((cid, target))
            if pair in never:
                continue
            pairs.setdefault(pair, why)

    print(f"concepts (excl. sessions): {len(docs)}")
    print(f"candidate pairs: {len(pairs)} (never_merge pairs skipped: {len(never)})\n")

    proposals = []
    for pair, why in pairs.items():
        winner, loser = sorted(pair, key=lambda c: (-sources[c], c))
        if not titles[loser]:
            continue
        proposals.append((winner, loser, why))
    proposals.sort()

    print("# review each pair: keep the merge line (merge) or move it to never_merge:")
    print("merge:")
    for winner, loser, why in proposals:
        print(
            f"  {titles[loser].lower()}: {winner}"
            f"   # {titles[loser]} -> {titles[winner]} ({loser}; {why}; "
            f"sources {sources[loser]} vs {sources[winner]})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
