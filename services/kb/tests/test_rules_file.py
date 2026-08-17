"""Identity rules live in entity_rules.yaml, which the pipeline never writes.

entity_registry.yaml is regenerated on every run through a YAML dump, so a rule
kept there loses its comment — the reason for the rule — the first time the
pipeline runs. The split keeps input and output apart for real.
"""

from pathlib import Path

import yaml

from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.resolve import (
    _load_ignored,
    _load_never_merge_pairs,
    _load_alias_overrides,
    rules_path_for,
    write_registry,
)

RULES = """\
# A comment that must survive every run.
merge:
  vasul: deities/vharzul
never_merge:
- - characters/rotunas
  - npcs/geist_von_rotunas
ignore:
- items/heiltrank
"""


def _registry(tmp_path: Path) -> Path:
    path = tmp_path / "entity_registry.yaml"
    path.write_text("entities: []\n", encoding="utf-8")
    rules_path_for(path).write_text(RULES, encoding="utf-8")
    return path


def test_rules_are_read_from_the_sidecar_file(tmp_path: Path):
    path = _registry(tmp_path)
    assert _load_alias_overrides(path)["vasul"] == "deities/vharzul"
    assert _load_ignored(path) == {"items/heiltrank"}
    assert {"characters/rotunas", "npcs/geist_von_rotunas"} in _load_never_merge_pairs(path)


def test_writing_the_registry_leaves_the_rules_file_alone(tmp_path: Path):
    path = _registry(tmp_path)
    entity = CanonicalEntity(
        concept_id="npcs/x", type=EntityType.NPC, canonical_name="X",
        mentions=[MentionRef(session_id="s", date="2025-01-01", url="u",
                             citation_ts="00:00:01", note="n")],
    )
    write_registry([entity], path)

    assert rules_path_for(path).read_text(encoding="utf-8") == RULES
    # …and the rules are not copied back into the generated file, where the
    # next dump would strip their comments again.
    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert set(written) == {"entities"}


def test_rules_still_work_when_left_in_the_registry(tmp_path: Path):
    # Back-compat: a repo that has not migrated yet must keep resolving.
    path = tmp_path / "entity_registry.yaml"
    path.write_text("merge:\n  vasul: deities/vharzul\nentities: []\n", encoding="utf-8")
    assert _load_alias_overrides(path)["vasul"] == "deities/vharzul"
