"""Unit tests for eval_matching's scoring core, over small hand-built fixtures
-- never the real (large) registry. See test_rules_doctor.py for the same
pattern against a sibling read-only diagnostic script.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval_matching import (  # noqa: E402
    build_alias_rows,
    closure_scores,
    live_stale_split,
    score_v3,
)


def test_v1_leave_one_out_scores_zero_recall_when_alias_is_the_only_signal():
    # The gold concept's ONLY alias is the merge key under test ("bar"), and
    # its own id-slug ("xyzxyz") is nothing like it -- a decoy concept's
    # id-slug ("baz") is a closer (if still wrong) match on the raw string.
    # Without leave-one-out, V1 would trivially "find" bar -> npcs/xyzxyz via
    # the very alias the merge rule produced, scoring 1.0 and burying the
    # decoy; with it, that row is filtered, so the decoy's unrelated id-slug
    # similarity is all that is left and gold must not rank first.
    entities = [
        {"concept_id": "npcs/xyzxyz", "canonical_name": "Xyzxyz", "aliases": ["Bar"]},
        {"concept_id": "npcs/baz", "canonical_name": "Baz", "aliases": []},
    ]
    rows = build_alias_rows(entities, lambda s: s)
    scores = closure_scores("bar", rows)
    ranked = sorted(scores, key=lambda c: (-scores[c], c))
    assert ranked[0] == "npcs/baz"
    assert ranked[0] != "npcs/xyzxyz"


def test_v3_unifies_vasul_and_basul():
    assert score_v3("vasul", "basul") == 1.0


def test_live_stale_split_against_a_fake_nested_cache(tmp_path: Path):
    cache = tmp_path / "extract"
    (cache / "2026-01-01_RF_a").mkdir(parents=True)
    (cache / "2026-01-01_RF_a" / "k1.json").write_text(
        json.dumps({"extraction": {"entities": [{"name": "Vasul", "type": "Deity"}]}}),
        encoding="utf-8",
    )
    (cache / "2026-02-02_RF_b").mkdir(parents=True)
    (cache / "2026-02-02_RF_b" / "k2.json").write_text(
        json.dumps({"extraction": {"entities": [{"name": "Zebros", "type": "Faction"}]}}),
        encoding="utf-8",
    )

    merge = {"vasul": "deities/vharzul", "warzul": "deities/vharzul"}
    live, stale = live_stale_split(merge, cache_dir=cache)
    assert live == {"vasul": "deities/vharzul"}
    assert stale == {"warzul": "deities/vharzul"}
