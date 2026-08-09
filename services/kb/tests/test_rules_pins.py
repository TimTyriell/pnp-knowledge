"""``canonical_name:`` and ``important:`` are settable from the rules file.

Both are hand-set decisions. Leaving them only in the generated inventory meant
the reason for a pin ("Holodarn is a mishearing, the Titan is Huludan") had
nowhere to live, because that file is rewritten by a comment-stripping dump.
"""

from pathlib import Path

from pnp_okf.resolve import (
    _load_canonical_names,
    _load_important,
    rules_path_for,
)

REGISTRY = """\
entities:
- concept_id: deities/huludan
  type: Deity
  canonical_name: Holodarn
  aliases: []
  mention_count: 3
- concept_id: npcs/lenra
  type: NPC
  canonical_name: Lenra
  aliases: []
  mention_count: 5
  important: true
"""

RULES = """\
canonical_name:
  # "Holodarn" was never a name, only a mishearing.
  deities/huludan: Huludan
important:
- deities/huludan
"""


def _paths(tmp_path: Path) -> Path:
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(REGISTRY, encoding="utf-8")
    rules_path_for(registry).write_text(RULES, encoding="utf-8")
    return registry


def test_rule_pin_beats_the_generated_name(tmp_path: Path):
    names = _load_canonical_names(_paths(tmp_path))
    assert names["deities/huludan"] == "Huludan"
    # Entries with no rule still take their name from the inventory.
    assert names["npcs/lenra"] == "Lenra"


def test_important_comes_from_both_places(tmp_path: Path):
    # The rules file adds to the flags already in the inventory rather than
    # replacing them, so a half-migrated repo keeps every flag it had.
    assert _load_important(_paths(tmp_path)) == {"deities/huludan", "npcs/lenra"}


def test_unimportant_overrides_a_registry_preserved_flag(tmp_path: Path):
    # npcs/lenra is important: true straight in the registry (no rule) — the
    # ratchet case: a past run baked the flag in, and nothing in the rules
    # file un-sets it unless unimportant: is used.
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(REGISTRY, encoding="utf-8")
    rules_path_for(registry).write_text(RULES + "unimportant:\n- npcs/lenra\n", encoding="utf-8")
    assert _load_important(registry) == {"deities/huludan"}
