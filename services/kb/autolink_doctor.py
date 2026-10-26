"""Find likely noun collisions in the bundle's autolinks. Read-only, no LLM.

synthesize.link_targets links the first bare occurrence of every entity name.
A common German noun that is also an entity name or alias ("Krieg" the war vs.
the PC Krieg) therefore mislinks every prose occurrence. This script lists the
single-word capitalised link labels whose text is not the target's own title
and whose target is a person or item page -- the likeliest such collisions --
and prints a ready-to-paste autolink_block: block (top 20) for a human to
prune. Nothing is written.

    python autolink_doctor.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # services/kb
sys.path.insert(0, str(ROOT / "src"))

from pnp_okf.okf import split_document  # noqa: E402

BUNDLE = ROOT.parent.parent / "knowledge" / "bundle" / "splitter_des_ewigen"
# A prose noun that links to a person or item page is the collision that hurts;
# a place or faction linking to its own page is not.
SUSPECT_DIRS = ("characters", "npcs", "items")
TOP_N = 20
# Bundle links are "[label](/dir/slug.md)"; the leading slash is optional here
# so this also reads output that has not been through the fix pass.
LINK_RE = re.compile(r"\[([^\]]+)\]\(/?([^)\s]+?)\.md\)")


def concepts(bundle: Path) -> dict[str, tuple[str, str]]:
    """``concept_id -> (title, body)`` for every concept file in the bundle."""

    out: dict[str, tuple[str, str]] = {}
    for path in bundle.rglob("*.md"):
        if path.name in ("index.md", "log.md"):
            continue
        cid = path.relative_to(bundle).with_suffix("").as_posix()
        fm, body = split_document(path.read_text(encoding="utf-8"))
        out[cid] = (str(fm.get("title") or ""), body)
    return out


def main() -> int:
    docs = concepts(BUNDLE)
    pairs: Counter[tuple[str, str]] = Counter()
    for _, body in docs.values():
        for label, target in LINK_RE.findall(body):
            pairs[(label, target)] += 1

    rows = []
    for (label, target), count in pairs.items():
        # Single word only: multi-word labels ("Lindo Laut") are unlikely to be
        # a noun that collides with ordinary prose.
        if " " in label or not label[:1].isupper():
            continue
        if target.split("/", 1)[0] not in SUSPECT_DIRS:
            continue
        title = docs.get(target, ("", ""))[0]
        if label == title:
            continue
        rows.append((label, target, count, title))
    rows.sort(key=lambda r: (-r[2], r[0], r[1]))

    print(f"bundle concepts: {len(docs)}")
    print(
        f"suspect links: {len(rows)} (single-word capitalised label, target in "
        f"{'/'.join(SUSPECT_DIRS)}, label != target title)\n"
    )
    print(f"{'label':<24} | {'target':<48} | {'count':>5} | target title")
    for label, target, count, title in rows:
        print(f"{label:<24} | {target:<48} | {count:>5} | {title}")

    names = list(dict.fromkeys(label for label, *_ in rows))[:TOP_N]
    print(f"\n# autolink_block candidates (top {TOP_N}, prune before pasting)")
    print("autolink_block:")
    for name in names:
        print(f"- {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
