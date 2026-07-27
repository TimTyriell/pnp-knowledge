"""The real rules file must not contradict itself.

YAML resolves a duplicate key by silently keeping the last one, so a stale
`uhoriaks: deities/uhoriaks` sitting above a corrected
`uhoriaks: deities/ohoriaks` looks fine and behaves at random depending on
edit order. A merge pointing at an id that nothing else defines is the other
half of the same problem: it reads like a rule and does nothing.
"""

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

RULES = Path(__file__).resolve().parents[3] / "knowledge" / "entity_rules.yaml"
KEY = re.compile(r"^  (?P<key>[^#\s][^:]*):\s*(?P<value>\S.*)$")

pytestmark = pytest.mark.skipif(not RULES.exists(), reason="no bundle checked out")


def _merge_keys() -> list[str]:
    keys, in_merge = [], False
    for line in RULES.read_text(encoding="utf-8").splitlines():
        if not line.startswith((" ", "#", "\t")) and line.strip():
            in_merge = line.startswith("merge:")
            continue
        match = KEY.match(line)
        if in_merge and match:
            keys.append(match.group("key"))
    return keys


def test_no_duplicate_merge_keys():
    dupes = sorted(k for k, n in Counter(_merge_keys()).items() if n > 1)
    assert not dupes, f"duplicate merge keys silently drop rules: {dupes}"


def test_every_merge_target_is_well_formed():
    # A target must name a real concept directory, or the mention lands in a
    # directory the emit stage never writes and the entity vanishes.
    data = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {}
    from pnp_okf.models import TYPE_DIR

    dirs = set(TYPE_DIR.values())
    bad = sorted(
        f"{name} -> {cid}"
        for name, cid in (data.get("merge") or {}).items()
        if cid.split("/", 1)[0] not in dirs or "/" not in cid
    )
    assert not bad, f"merge targets outside the known concept dirs: {bad}"
