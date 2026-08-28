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
