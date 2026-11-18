"""B1: the one-time rules migration rewrites references, keeps every comment."""

import sys
from pathlib import Path

import yaml
from pnp_okf.resolve import rekey_uids

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from migrate_rules_to_uids import migrate  # noqa: E402

UIDS = {"npcs/hexe": "c_aaaaaaaa", "factions/a": "c_bbbbbbbb", "factions/b": "c_cccccccc"}

RULES = """\
# header comment
merge:
  hexe: npcs/hexe
never_merge:
# why these stay apart
- - factions/a
  - factions/b
important:
- npcs/hexe  # GM 2026-08
- npcs/unbekannt
canonical_name:
  npcs/hexe: Landra  # mis-heard as Lenra
alias_block:
  npcs/hexe:
  - lenra
status_rules:
  drop:
  - npcs/hexe@s7
split:
  - name: hexe
    session: s3
    concept_id: npcs/hexe
"""


def test_migration_rewrites_references_and_keeps_comments():
    new, missing = migrate(RULES, UIDS)
    assert missing == ["npcs/unbekannt"]
    assert "# header comment" in new and "# why these stay apart" in new
    assert "- c_aaaaaaaa  # npcs/hexe -- GM 2026-08" in new
    assert "- - c_bbbbbbbb  # factions/a" in new
    assert "  c_aaaaaaaa: Landra  # npcs/hexe -- mis-heard as Lenra" in new
    assert "  - c_aaaaaaaa@s7  # npcs/hexe" in new
    # merge: and split: values define a target -- untouched.
    assert "  hexe: npcs/hexe" in new
    assert "    concept_id: npcs/hexe" in new


def test_migrated_rules_load_back_to_the_same_concepts():
    index = {uid: cid for cid, uid in UIDS.items()}
    before = rekey_uids(yaml.safe_load(RULES), index)
    after = rekey_uids(yaml.safe_load(migrate(RULES, UIDS)[0]), index)
    assert after == before


def test_migration_is_idempotent():
    once, _ = migrate(RULES, UIDS)
    assert migrate(once, UIDS)[0] == once
