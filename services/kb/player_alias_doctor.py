"""Print alias_block suggestions for aliases that contain a real player name (T8).

Reads the private player-name list (``PNP_ROSTER_PRIVATE``) and the bundle,
and prints a YAML ``alias_block:`` snippet: ``concept_id: [alias, ...]`` for
every alias containing a player name. Paste the alias strings into
knowledge/entity_rules.yaml. Writes nothing itself.

The output contains player names, so it is for the terminal only. Do not
redirect it into a committed file. The aliases already exist in the committed
bundle, so blocking them adds no new exposure.

    PNP_ROSTER_PRIVATE=<path> python player_alias_doctor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pnp_okf.okf import split_document
from pnp_okf.validate import load_private_player_names, player_name_hits

ROOT = Path(__file__).resolve().parent  # services/kb
BUNDLE = ROOT.parent.parent / "knowledge" / "bundle" / "splitter_des_ewigen"


def alias_blocks(bundle: Path, names: list[str]) -> dict[str, list[str]]:
    """concept_id -> aliases that contain one of *names* (whole-word hits only)."""
    concepts = {cid for cid, where, _ in player_name_hits(bundle, names) if where == "alias"}
    out: dict[str, list[str]] = {}
    for cid in sorted(concepts):
        text = (bundle / f"{cid}.md").read_text(encoding="utf-8")
        frontmatter, _ = split_document(text)
        aliases = [str(a) for a in frontmatter.get("aliases") or []]
        out[cid] = [a for a in aliases if any(n in a for n in names)]
    return out


def main() -> int:
    names = load_private_player_names()
    if names is None:
        print("PNP_ROSTER_PRIVATE is not set or the file is missing.", file=sys.stderr)
        return 1
    blocks = alias_blocks(BUNDLE, names)
    if not blocks:
        print("No aliases contain a player name.", file=sys.stderr)
        return 0
    print(yaml.safe_dump({"alias_block": blocks}, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
