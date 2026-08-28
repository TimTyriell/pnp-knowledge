"""A resolved conflict must stay resolved.

prune_conflicts() (emit.py) already deletes a conflict file the moment a run
no longer reproduces it, and test_conflict_workflow.py already pins that
contract in isolation. What nothing checks is the *campaign-specific* half of
the same promise: that a conflict a human actually looked at and settled
doesn't quietly reappear because the fix in entity_rules.yaml or
Kanon_Entscheidungen.md stopped applying (see test_rules_applied.py and
test_canon_decisions.py for how that happens) or because a stale
conflicts/ snapshot came back on a branch checkout (see
test_bundle_invariants.py).

data/resolved_conflicts.txt is the append-only ledger: resolve a conflict,
add its concept_id, and this test keeps it resolved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
CONFLICTS_DIR = KNOWLEDGE / "conflicts"
LEDGER = Path(__file__).resolve().parent / "data" / "resolved_conflicts.txt"

pytestmark = pytest.mark.skipif(not CONFLICTS_DIR.is_dir(), reason="no bundle checked out")


def _resolved_ids() -> list[str]:
    lines = LEDGER.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def test_resolved_conflicts_have_not_come_back():
    reappeared = []
    for concept_id in _resolved_ids():
        slug = concept_id.replace("/", "__")
        path = CONFLICTS_DIR / f"{slug}.md"
        if path.exists() and "type: Conflict" in path.read_text(encoding="utf-8")[:400]:
            reappeared.append(concept_id)
    assert not reappeared, (
        f"conflict(s) marked resolved in {LEDGER.name} are back in the "
        f"queue: {reappeared}. Check whether the entity_rules.yaml/"
        f"Kanon_Entscheidungen.md fix that resolved them still applies "
        f"(test_rules_applied.py / test_canon_decisions.py), or whether "
        f"this is a stale branch checkout (test_bundle_invariants.py)."
    )
