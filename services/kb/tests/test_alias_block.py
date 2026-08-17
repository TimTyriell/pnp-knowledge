"""``alias_block:`` suppresses a display alias without touching identity.

Deleting an alias from the generated registry never sticks by itself:
write_registry preserves existing aliases and appends newly discovered ones,
so the old spelling comes back on the next run. alias_block is the
suppression list that survives a rewrite — display only, folding is
untouched.
"""

from pathlib import Path

from pnp_okf.resolve import (
    _load_alias_blocks,
    _load_alias_overrides,
    rules_path_for,
    write_registry,
)
from pnp_okf.models import CanonicalEntity, EntityType

REGISTRY = """\
entities:
- concept_id: npcs/lenra
  type: NPC
  canonical_name: Die Hag Lenra
  aliases:
  - Hack
  - Sumpfhexe
  mention_count: 9
"""

RULES = """\
merge:
  hack: npcs/lenra
alias_block:
  npcs/lenra:
  - Hack
"""


def _paths(tmp_path: Path) -> Path:
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(REGISTRY, encoding="utf-8")
    rules_path_for(registry).write_text(RULES, encoding="utf-8")
    return registry


def test_alias_block_loads():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        registry = _paths(Path(d))
        blocks = _load_alias_blocks(registry)
        assert blocks == {"npcs/lenra": {"hack"}}


def test_write_registry_drops_blocked_alias(tmp_path: Path):
    registry = _paths(tmp_path)
    entity = CanonicalEntity(
        concept_id="npcs/lenra",
        type=EntityType.NPC,
        canonical_name="Die Hag Lenra",
        aliases=["Hack", "Sumpfhexe"],
        mentions=[],
    )
    write_registry([entity], registry)

    import yaml

    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    aliases = data["entities"][0]["aliases"]
    assert "Hack" not in aliases
    assert "Sumpfhexe" in aliases


def test_folding_still_works_despite_the_block(tmp_path: Path):
    # Blocking the display alias must not un-fold "hack" -> the merge
    # override is the only thing that decides identity.
    registry = _paths(tmp_path)
    overrides = _load_alias_overrides(registry)
    assert overrides["hack"] == "npcs/lenra"


if __name__ == "__main__":
    import sys
    import tempfile

    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                needs_path = "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]
                if needs_path:
                    with tempfile.TemporaryDirectory() as d:
                        fn(Path(d))
                else:
                    fn()
                print(f"ok    {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
    sys.exit(1 if failures else 0)
