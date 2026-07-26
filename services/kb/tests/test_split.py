"""Two beings sharing one name must be separable — merging cannot do this.

The campaign has two Haralds (a privateer captain and a demon in Abisalis)
extracted under the identical string; only the session distinguishes them.

The concept ids must not be token-subsets of one another ("harald" vs
"harald_daemon"), or the token-subset pass folds the deliberate split straight
back together. Hence the ``<qualifier>_harald`` naming.
"""

from pathlib import Path

import yaml

from pnp_okf.models import (
    EntityMention,
    EntityType,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.resolve import resolve_entities

SPLIT = [
    {"name": "harald", "session": "2026-03-18", "concept_id": "npcs/freibeuter_harald"},
    {"name": "harald", "session": "2026-04-14", "concept_id": "npcs/abisalis_harald"},
]


def _fixture(tmp_path: Path, split, never_merge=None):
    reg = tmp_path / "entity_registry.yaml"
    reg.write_text(
        yaml.safe_dump({"merge": {}, "split": split, "never_merge": never_merge or []}),
        encoding="utf-8",
    )

    def mention():
        return EntityMention(
            name="Harald", type=EntityType.NPC, note="n", citation_ts="00:01:00"
        )

    ex = {
        "s1": SessionExtraction(recap="r", entities=[mention()]),
        "s2": SessionExtraction(recap="r", entities=[mention()]),
    }
    tr = {
        "s1": SessionTranscript(session_id="s1", date="2026-03-18", url="u"),
        "s2": SessionTranscript(session_id="s2", date="2026-04-14", url="u"),
    }
    return ex, tr, reg


def test_same_name_different_sessions_split_into_two_concepts(tmp_path: Path):
    ex, tr, reg = _fixture(tmp_path, SPLIT)
    ents = {e.concept_id: e for e in resolve_entities(ex, tr, reg)}
    assert set(ents) == {"npcs/freibeuter_harald", "npcs/abisalis_harald"}
    assert len(ents["npcs/freibeuter_harald"].mentions) == 1
    assert len(ents["npcs/abisalis_harald"].mentions) == 1


def test_without_a_split_rule_both_collapse_into_one(tmp_path: Path):
    ex, tr, reg = _fixture(tmp_path, [])
    ents = {e.concept_id: e for e in resolve_entities(ex, tr, reg)}
    assert set(ents) == {"npcs/harald"}
    assert len(ents["npcs/harald"].mentions) == 2


def test_never_merge_protects_a_split_from_the_automatic_pass(tmp_path: Path):
    # Subset-shaped ids on purpose: without the guard the token-subset rule
    # would fold "harald" into "harald_daemon" and undo the split.
    bad_split = [
        {"name": "harald", "session": "2026-04-14", "concept_id": "npcs/harald_daemon"},
    ]
    ex, tr, reg = _fixture(
        tmp_path, bad_split, never_merge=[["npcs/harald", "npcs/harald_daemon"]]
    )
    ents = {e.concept_id for e in resolve_entities(ex, tr, reg)}
    assert ents == {"npcs/harald", "npcs/harald_daemon"}
