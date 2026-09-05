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
# target. Lowered from 1871 to 1816 after a real `pnp run` applied Fix 1
# (autolink_prose) and the alias-seeding fix (resolve.py). Ratchet: it may
# only go down.
#
# 2026-08-30 spelling-drift branch: raised 1816 -> 1889. Folding
# factions/untote_horde_von_zebras into factions/belorus_untotenarmee (a
# spelling-split duplicate, see entity_rules.yaml) gave npcs/belorus.md a
# real new DeepSeek resynthesis with more grounding and more prose — richer,
# correct content, most of whose repeat name mentions are un-autolinked by
# design (autolink_prose only links a name's first occurrence per line). Not
# a linking regression; a byproduct of removing a duplicate identity.
#
# 2026-08-30 review-fix branch: RAISED 1889 -> 1912. This is the one ratchet
# move on the branch that goes the wrong way, and it is deliberate; the number
# was watched across three regenerations rather than set once.
#
# Measured 1867 (a *drop* of 22) after the code fixes alone: the ambiguity
# guard in link_targets() cost 12 names, but _linked_concept_ids() no longer
# letting a directory-qualified link (deities/foo) shadow an unrelated
# cross-type namesake (npcs/foo) more than paid for it. So the fix plan's
# prediction that the guard alone would raise this was wrong.
#
# The rise came from the two GM rulings that followed, plus one alias_block,
# and every point of it is a *wrong* link being refused:
#   - "Flüchtlinge" (~40 occurrences): the GM ruled the Ringtal refugees a
#     different group from Roland's, so factions/fluechtlinge exists again as
#     its own node and its bare generic name is blocked from autolinking.
#   - "Die Stadt": was an alias of locations/ehrenfels, so the ordinary noun
#     linked to Ehrenfels on 10+ pages including locations/sanddorn,
#     seelenwacht, boragdil and hartwacht — pages where it meant that page's
#     own city. Blocked.
#   - "Ende", already blocked earlier in the branch, same shape.
# A generic noun linked to one arbitrary concept is worse than plain text.
# Do not "fix" this by unblocking those aliases; the links it buys back are
# the wrong ones.
UNLINKED_MENTION_BASELINE = 1912


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
    for _cid, own_name, body in entities:
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


# --- deep-tier link coverage -------------------------------------------------
#
# UNLINKED_MENTION_BASELINE above counts unlinked *name mentions*; it doesn't
# separate "a stub with one mention has none to link" from "a 1000-word deep
# entry names half the campaign and links none of it". The second is the
# 2026-08-29 bundle-quality audit's actual finding: _autolink() (synthesize.py)
# used to run only on brief-tier bodies, so a deep/standard body relied on the
# model linking itself — which it mostly didn't. This measures that directly.

_ANY_LINK_RE = re.compile(r"\]\([^)\s]*?\.md\)")

# Deep-tier concepts (body has "## Überblick") with zero outgoing links.
# Was 53/60 before Fix 1 (autolink_prose, synthesize.py); a real `pnp run`
# afterward brought it to 0/73 — every deep-tier node now links at least one
# other concept. Kept as a hard ceiling, not just a ratchet: this pattern
# has a known complete fix and should never reappear silently.
DEEP_TIER_NO_LINK_BASELINE = 0


def test_deep_tier_nodes_are_linked():
    entities = _bundle_files()
    deep = [(cid, body) for cid, _name, body in entities if "## Überblick" in body]
    unlinked = sorted(cid for cid, body in deep if not _ANY_LINK_RE.search(body))
    assert len(unlinked) <= DEEP_TIER_NO_LINK_BASELINE, (
        f"{len(unlinked)} deep-tier concepts (body has '## Überblick') have "
        f"zero outgoing links (baseline {DEEP_TIER_NO_LINK_BASELINE}). These "
        f"are the richest entries in the bundle and are invisible to any "
        f"graph-shaped consumer. Re-run `pnp run` after Fix 1 before raising "
        f"this number: {unlinked[:10]}{'…' if len(unlinked) > 10 else ''}"
    )


# --- faction <-> character/NPC relation coverage -----------------------------
#
# The narrow half of the same defect: even where a deep node does link
# something, is it linking the *relation* Question 5 of the audit asked
# about (faction membership, faction<->territory)? Counted separately from
# test_deep_tier_nodes_are_linked because Fix 1 alone can raise that number
# without ever producing a single faction<->member edge — this is the
# quantity that actually proves the Belorius/Zebros and Landra/Cornivum
# seeds in the audit report got fixed.

_MEMBER_LINK_RE = re.compile(r"\]\(/?(?:\.\./)?(?:characters|npcs)/")
_FACTION_LINK_RE = re.compile(r"\]\(/?(?:\.\./)?factions/")

# (has-at-least-one-member-link, total) for factions/, and the NPC-side
# mirror. Was 22/42 and 31/228 before Fix 1 + the alias-seeding fix; a real
# `pnp run` brought it to 31/40 and 46/218. Ratchet in the *good* direction:
# the fraction may only go up (kept as counts, not a percentage, so a change
# in bundle size can't silently mask a regression).
#
# 2026-08-30 spelling-drift branch: factions/untote_horde_von_zebras (a
# spelling-split duplicate of factions/belorus_untotenarmee, see
# entity_rules.yaml's "untote horde von zebras" merge key) is gone —
# genuinely one fewer faction, and it happened to be one of the 31 with a
# member link. 31/40 -> 30/39, same fraction, not a regression.
#
# 2026-08-30 review-fix branch: NPC side 46/218 -> 45/219, re-measured after
# the regeneration. Accounted for exactly, by diffing the faction-linking NPC
# set against the previous bundle: three lost a faction link, two gained one.
# The one deliberate loss is npcs/buergermeister_spitzzahn, which linked
# "[Flüchtlinge](/factions/fluechtlinge_aus_breska.md)" on the bare generic
# noun that entity_rules.yaml's alias_block now drops (the merge: key, i.e.
# identity, is untouched — only linkability). The other two
# (npcs/joar_vanur "Gnollen", npcs/tyrael "Dämonen") were both resynthesized
# by DeepSeek in the same run and simply worded it differently; npcs/gorak
# and npcs/nyruk gained one the same way. Faction side is unchanged at 30/39.
#
# Final numbers after the GM rulings: the NPC side recovered to 46/219 (the
# resynthesis wording that had cost two links came back), and factions gained
# a member with the fluechtlinge split, 39 -> 40 total.
FACTIONS_WITH_MEMBER_LINK_BASELINE = 30
FACTIONS_TOTAL_BASELINE = 40
NPCS_WITH_FACTION_LINK_BASELINE = 46
NPCS_TOTAL_BASELINE = 219


def test_relation_coverage_has_not_dropped():
    entities = _bundle_files()
    factions = [body for cid, _name, body in entities if cid.startswith("factions/")]
    npcs = [body for cid, _name, body in entities if cid.startswith("npcs/")]

    fac_with_member = sum(1 for body in factions if _MEMBER_LINK_RE.search(body))
    npc_with_faction = sum(1 for body in npcs if _FACTION_LINK_RE.search(body))

    # A shrinking denominator (e.g. entity_rules.yaml merges/ignores some
    # factions or NPCs away) is fine and expected from this audit's fixes;
    # what must not happen is the *numerator* falling below its baseline
    # while the type still has roughly as many members as before.
    assert fac_with_member >= min(FACTIONS_WITH_MEMBER_LINK_BASELINE, len(factions)), (
        f"only {fac_with_member}/{len(factions)} factions link a member "
        f"(/characters/ or /npcs/), baseline was "
        f"{FACTIONS_WITH_MEMBER_LINK_BASELINE}/{FACTIONS_TOTAL_BASELINE}"
    )
    assert npc_with_faction >= min(NPCS_WITH_FACTION_LINK_BASELINE, len(npcs)), (
        f"only {npc_with_faction}/{len(npcs)} NPCs link a /factions/, "
        f"baseline was {NPCS_WITH_FACTION_LINK_BASELINE}/{NPCS_TOTAL_BASELINE}"
    )
