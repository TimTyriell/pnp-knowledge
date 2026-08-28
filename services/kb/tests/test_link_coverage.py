"""The real linking test: is a name mentioned in prose actually a link?

``pnp validate`` already checks that every markdown link *present* in a body
resolves (0 broken today) — but that check runs *after* emit, and emit's own
normalize_body() silently rewrites any link it cannot resolve back to plain
text (links.py, drop_unresolved=True), logged only at debug. A link that
never made it into the body at all, or one synthesis wrote as bare prose
instead of a markdown link, is invisible to both. "0 broken links" is
therefore not the same claim as "every reference is linked" — this test
measures the claim validate.py cannot make: how often another entity's name
appears in a concept's body as plain text, outside any markdown link.

This is deliberately a *coverage* signal, not a correctness gate — a body
mentioning "der Turm" is not always the concept `locations/turm`, and forcing
every such mention into a link would over-link generic language. So this
ratchets against a measured baseline like the other bundle-quality tests:
the number it should not be allowed to quietly grow.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from pnp_okf.models import TYPE_DIR

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"

pytestmark = pytest.mark.skipif(not BUNDLE.is_dir(), reason="no bundle checked out")

_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!\w+:)([^)\s]*?\.md)\)")

# Only proper-noun-length names are considered: short names produce enough
# accidental substring hits in ordinary prose to swamp the signal (this is
# the same tradeoff test_canon_decisions.py's context.py fix had to navigate
# for source-heading matching, just applied to link coverage instead).
_MIN_NAME_LEN = 5

# Unlinked mentions of another entity's name, measured on this branch. A
# body mentioning another concept's name in plain prose is exactly the
# "nodes not linked correctly" symptom reported for this bundle — the count
# was previously unmeasured (validate.py cannot see it; see module
# docstring), so this baseline is the first real measurement, not a design
# target. Ratchet: it may only go down.
UNLINKED_MENTION_BASELINE = 1871


def _bundle_files() -> list[tuple[str, str, str]]:
    """(concept_id, canonical_name, body) for every non-session concept."""

    out = []
    for etype_dir in TYPE_DIR.values():
        for path in sorted((BUNDLE / etype_dir).glob("*.md")):
            if path.name == "index.md":
                continue
            text = path.read_text(encoding="utf-8")
            parts = text.split("---\n", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            name = str(fm.get("title") or "").strip()
            if not name:
                continue
            out.append((f"{etype_dir}/{path.stem}", name, parts[2]))
    return out


def _name_pattern(names: list[str]) -> re.Pattern:
    escaped = sorted((re.escape(n) for n in names), key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(escaped) + r")(?!\w)")


def _count_unlinked_mentions() -> int:
    entities = _bundle_files()
    name_to_cid: dict[str, str] = {}
    for cid, name, _body in entities:
        if len(name) >= _MIN_NAME_LEN:
            name_to_cid.setdefault(name, cid)
    if not name_to_cid:
        return 0
    pattern = _name_pattern(list(name_to_cid))

    total = 0
    for cid, own_name, body in entities:
        stripped = _LINK_RE.sub("", body)
        for match in pattern.finditer(stripped):
            name = match.group(1)
            if name == own_name:
                continue  # a body referring to its own title is not a link
            total += 1
    return total


def test_unlinked_mentions_have_not_grown():
    total = _count_unlinked_mentions()
    assert total <= UNLINKED_MENTION_BASELINE, (
        f"{total} plain-text mentions of another entity's name outside any "
        f"markdown link (baseline {UNLINKED_MENTION_BASELINE}). This is the "
        f"honest 'are nodes linked correctly' number — validate.py's 0 "
        f"broken links only counts links that were written, not mentions "
        f"that never became one."
    )
