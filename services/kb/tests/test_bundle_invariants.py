"""Structural invariants over the real bundle, registry, and run state.

Distinct from test_rules_applied.py (are hand-authored decisions applied) and
test_link_coverage.py (are entities linked to each other): this checks that
the bundle is *internally consistent* with the two things that reference it
from outside — entity_registry.yaml (the inventory the pipeline itself
tracks) and state/last_run.json (the pipeline's own account of what it last
produced) — and that the typed-ID scheme other repos (pnp-export-data) depend
on is intact.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from pnp_okf.models import ID_PREFIX, TYPE_DIR

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
CONFLICTS_DIR = KNOWLEDGE / "conflicts"
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"
STATE_DIR = Path(__file__).resolve().parents[1] / "state"
LAST_RUN = STATE_DIR / "last_run.json"

pytestmark = pytest.mark.skipif(not REGISTRY.exists(), reason="no bundle checked out")


def _split_frontmatter(text: str) -> dict[str, object]:
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def _entity_files() -> list[tuple[str, Path, dict]]:
    """(concept_id, path, frontmatter) for every non-session concept."""

    out = []
    for etype_dir in TYPE_DIR.values():
        for path in sorted((BUNDLE / etype_dir).glob("*.md")):
            if path.name == "index.md":
                continue
            out.append((f"{etype_dir}/{path.stem}", path, _split_frontmatter(path.read_text(encoding="utf-8"))))
    return out


def test_ids_match_the_typed_id_scheme():
    """Every ``id:`` uses one of the 8 real prefixes and is derivable from
    its concept_id — the scheme pnp-export-data's wiki page map depends on.
    Note there is no QUEST_/ROLL_ prefix in this pipeline (those exist only
    in the frozen graph/ pipeline and reports/rolls/*.csv), so a concept
    carrying one would be a cross-pipeline mixup, not a typo."""

    valid_prefixes = set(ID_PREFIX.values())
    bad = []
    for cid, _path, fm in _entity_files():
        eid = str(fm.get("id") or "").strip()
        etype_dir = cid.split("/", 1)[0]
        slug = cid.rsplit("/", 1)[-1]
        expected_prefix = next((p for t, d in TYPE_DIR.items() if d == etype_dir for p in [ID_PREFIX[t]]), None)
        expected = f"{expected_prefix}_{slug.upper()}" if expected_prefix else None
        if not eid or eid.split("_", 1)[0] not in valid_prefixes or eid != expected:
            bad.append(f"{cid}: id={eid!r}, expected={expected!r}")

    assert not bad, f"id: does not match the typed-ID scheme: {bad}"


def test_registry_and_bundle_agree():
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    registry_ids = {
        str(e.get("concept_id", "")).strip() for e in (registry.get("entities") or [])
    }
    bundle_ids = {cid for cid, _path, _fm in _entity_files()}

    missing_from_bundle = sorted(registry_ids - bundle_ids)
    missing_from_registry = sorted(bundle_ids - registry_ids)
    assert not missing_from_bundle, (
        f"in entity_registry.yaml but no concept file exists: {missing_from_bundle}"
    )
    assert not missing_from_registry, (
        f"a concept file exists but entity_registry.yaml never heard of it "
        f"(the next write_registry() run may silently drop its curated "
        f"aliases/important flag): {missing_from_registry}"
    )


def test_conflict_files_reference_real_concepts():
    bundle_ids = {cid for cid, _path, _fm in _entity_files()}
    bad = []
    for path in sorted(CONFLICTS_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        fm = _split_frontmatter(text)
        if "type: Conflict" not in text[:400]:
            continue  # e.g. merge_proposals.md, not a queue entry
        concept = str(fm.get("concept") or "").strip()
        if concept not in bundle_ids:
            bad.append(f"{path.name}: concept={concept!r}")
    assert not bad, f"conflict file points at a concept that does not exist: {bad}"


def test_last_run_conflict_count_matches_the_committed_queue():
    """The pipeline's own record of what it produced must match what is
    actually committed under conflicts/. A mismatch means the committed
    bundle is not the output of the run state/last_run.json describes —
    typically a branch checkout that brought back an older conflicts/
    snapshot alongside a newer (or older) last_run.json. Not a ratchet:
    this is a binary in-sync/out-of-sync fact, fixed by re-running `pnp run`
    on the checked-out branch, not by curation over time."""

    if not LAST_RUN.exists():
        pytest.skip("no state/last_run.json — pipeline has not been run here")
    status = json.loads(LAST_RUN.read_text(encoding="utf-8"))
    reported = status.get("counts", {}).get("conflicts_open")
    if reported is None:
        pytest.skip("last_run.json predates the conflicts_open counter")

    on_disk = sum(
        1
        for p in CONFLICTS_DIR.glob("*.md")
        if p.name != "README.md" and "type: Conflict" in p.read_text(encoding="utf-8")[:400]
    )
    assert on_disk == reported, (
        f"state/last_run.json says {reported} open conflict(s), but "
        f"{on_disk} 'type: Conflict' file(s) are actually committed under "
        f"{CONFLICTS_DIR} — the committed bundle and the last recorded run "
        f"disagree. Re-run `pnp run` on this checkout, or check out the "
        f"branch/commit last_run.json actually describes."
    )


# --- citation coverage --------------------------------------------------
#
# The bundle uses three citation-line shapes side by side: "[P-40] Session
# …" and "[S1-01-A] Session …" from the LLM synthesis, and numbered
# "1. Session …" from render_brief_body (synthesize.py) — brief entries are
# rendered locally and never see the model. A naive `grep '^\[P-'` (the
# mistake this audit's own first pass made) only sees the first two and
# wildly undercounts. This checks all three at once.

# A 4th variant surfaced on the 2026-08-29 audit's real `pnp run`: a
# numbered entry where the model wrapped the whole citation in a link
# ("1. [Session 2025-06-25 @ ...](url)") instead of "1. Session ... (url)".
# "Nummeriert auflisten... Session-Datum + Zeitstempel + URL" (prompts.py)
# doesn't pin the exact punctuation, so this is valid model output, not a
# malformed line — the numbered-marker branch allows an optional "[" before
# "Session" to catch it too.
_CITATION_LINE_RE = re.compile(r"^(\[[^\]]+\]|\d+\.)\s*\[?Session\s", re.MULTILINE)

# Entity concepts with zero recognizable citation line in any of the four
# formats. Was 5 on the pre-run bundle; a real `pnp run` (with re-extraction
# picking different entities each time) settled at 3. Ratchet: may only go
# down. Root cause is in extract.py (a mention without a citation_ts), out
# of scope for this audit's fixes — see docs/audits/2026-08-29-bundle-quality.md.
#
# 2026-08-30 review-fix branch: tightened 3 -> 1 after the regeneration.
# emit_entity now backfills a missing "# Belege" section from the entity's
# own mentions (the section was only ever a prompt instruction, never
# enforced), which repaired the standard-tier pages the model had shipped
# without one.
#
# Correcting the attribution above while here: the single remaining entry,
# deities/saris_patron, is NOT a missing-citation_ts case and is not in fact
# uncited. Its page carries a real citation with a real timestamp and URL —
# "[S1-02-B] Transkript der Session vom 23. Juli 2026, 01:48:07. Online
# verfügbar unter https://..." — which _CITATION_LINE_RE simply does not
# match, because the regex wants the literal word "Session" straight after
# the marker and the model wrote "Transkript der Session vom" instead. So
# this last 1 is a 5th citation-line variant the detector doesn't know, i.e.
# a false positive of the measurement, not a defect in the bundle. Left at 1
# deliberately rather than widening the regex: loosening a detector to reach
# zero would also blind it to genuinely uncited pages.
UNCITED_ENTITY_BASELINE = 1


def test_emit_entity_backfills_a_missing_belege_section(tmp_path: Path):
    # The "# Belege" heading is only a prompt instruction (prompts.py) for
    # standard/deep tiers -- nothing enforced it, so a model that skipped it
    # shipped an uncited page (npcs/lord_kalidarn_von_willauch). emit_entity
    # now backfills the section from the entity's own mentions, the same
    # citation loop render_brief_body uses.
    from pnp_okf.emit import emit_entity
    from pnp_okf.models import CanonicalEntity, EntityType, MentionRef

    entity = CanonicalEntity(
        concept_id="npcs/kalidarn_test",
        type=EntityType.NPC,
        canonical_name="Kalidarn Test",
        mentions=[
            MentionRef(session_id="s1", date="2025-10-14", url="https://youtu.be/a",
                       citation_ts="00:37:48", note="Erste Erwähnung."),
            MentionRef(session_id="s2", date="2025-10-21", url="https://youtu.be/b",
                       citation_ts="00:14:20", note="Zweite Erwähnung."),
        ],
    )
    emit_entity(tmp_path / "b", entity, "## Überblick\n\nEin Herrscher.\n")
    doc = (tmp_path / "b" / "npcs" / "kalidarn_test.md").read_text(encoding="utf-8")
    assert "# Belege" in doc
    assert "1. Session 2025-10-14 @ 00:37:48 (https://youtu.be/a)" in doc
    assert "2. Session 2025-10-21 @ 00:14:20 (https://youtu.be/b)" in doc


def test_every_entity_node_cites_a_source():
    uncited = sorted(
        cid
        for cid, path, _fm in _entity_files()
        if not _CITATION_LINE_RE.search(path.read_text(encoding="utf-8"))
    )
    assert len(uncited) <= UNCITED_ENTITY_BASELINE, (
        f"{len(uncited)} entity concept(s) have no recognizable citation "
        f"line in any of the bundle's three formats ([P-nn], [S1-nn-X], or "
        f"'N. Session …') — baseline {UNCITED_ENTITY_BASELINE}: {uncited}"
    )


# --- tier vs. evidence ----------------------------------------------------
#
# The 2026-08-29 audit's Question 1 finding: `important: true` is the de
# facto deep/shallow switch for every type except Character/Deity (see
# DEEP_MENTION_THRESHOLD, models.py), and it's applied inconsistently in
# both directions — forced onto barely-attested entities (padding) and
# withheld from clearly recurring ones (stubs). Both directions measured
# here so a fix in one direction can't silently regress the other.

_UEBERBLICK_RE = "## Überblick"


def test_tier_matches_the_evidence():
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    mention_count = {
        str(e.get("concept_id", "")).strip(): int(e.get("mention_count") or 0)
        for e in (registry.get("entities") or [])
    }

    too_deep, too_shallow = [], []
    for cid, path, _fm in _entity_files():
        text = path.read_text(encoding="utf-8")
        deep = _UEBERBLICK_RE in text
        mc = mention_count.get(cid, 0)
        if deep and mc <= 1:
            too_deep.append(cid)
        if not deep and mc >= 5:
            too_shallow.append(cid)

    # "Too deep": a full deep-tier writeup built from essentially one
    # mention -- the padding failure mode. Measured after a real `pnp run`
    # with `unimportant: deities/akastrale` and the corrected important:
    # pins (entity_rules.yaml) applied. Fixing 3 of those pins from a dead
    # concept_id to the real one (bodrak_gott_der_stille, kaleandra,
    # burg_des_belorus) legitimately raised this from 5 to 6: important:
    # is *designed* to force the deep tier onto a low-mention pivotal
    # entity (models.py's own docstring: "the escape hatch for entities
    # the automatic rules underrate"), so a pin finally working is not a
    # new defect -- akastrale, the one case with a directly contradicting
    # GM ruling ("kein umfangreicher Eintrag"), is the only one that was
    # ever a real bug, and it's already fixed via unimportant:. Ratchet
    # against these 6 going forward: may only go down.
    assert len(too_deep) <= 6, (
        f"{len(too_deep)} concept(s) have full deep-tier structure from "
        f"<=1 mention (baseline 6): {too_deep}"
    )
    # "Too shallow": a recurring entity (>=5 mentions) that never got the
    # deep tier -- the stub failure mode. Confirmed 0 after DEEP_MENTION_
    # THRESHOLD (models.py, Fix 2) took effect on a real `pnp run` -- kept
    # as a hard ceiling, not just a ratchet, since this pattern has a known
    # complete fix and should never reappear silently.
    assert len(too_shallow) <= 0, (
        f"{len(too_shallow)} concept(s) have >=5 mentions but never got a "
        f"deep-tier writeup (was fixed to 0 by lowering DEEP_MENTION_THRESHOLD): {too_shallow}"
    )


# --- canon routing directive must never reach the model --------------------
#
# PLAN-canon-rulings-routing.md defect #6, the highest-priority one: an
# `<!-- okf: entity=... -->` directive is invisible in rendered markdown, so
# a leak isn't something a human reviewer would spot by reading the bundle.
# context.load_sources is supposed to strip it before it ever reaches a
# prompt (test_directive_is_stripped_from_section_text pins that in
# isolation); this is the second end of the same pipe, checking the actual
# committed output in case a real file's formatting ever drifts from that
# test's fixture.


def test_no_leaked_okf_directive():
    leaked = sorted(
        str(path.relative_to(BUNDLE))
        for path in BUNDLE.rglob("*.md")
        if "<!-- okf:" in path.read_text(encoding="utf-8")
    )
    assert not leaked, (
        f"okf routing directive leaked into the generated bundle (should "
        f"have been stripped by context.load_sources before the prompt): {leaked}"
    )
