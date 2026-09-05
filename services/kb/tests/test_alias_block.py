"""``alias_block:`` suppresses a display alias without touching identity.

Deleting an alias from the generated registry never sticks by itself:
write_registry preserves existing aliases and appends newly discovered ones,
so the old spelling comes back on the next run. alias_block is the
suppression list that survives a rewrite — display only, folding is
untouched.
"""

from pathlib import Path

import pytest
import yaml
from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.resolve import (
    _load_alias_blocks,
    _load_alias_overrides,
    _load_never_merge_pairs,
    _registry_data,
    rules_path_for,
    write_registry,
)

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
REAL_REGISTRY = KNOWLEDGE / "entity_registry.yaml"

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


    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    aliases = data["entities"][0]["aliases"]
    assert "Hack" not in aliases
    assert "Sumpfhexe" in aliases


@pytest.mark.skipif(not REAL_REGISTRY.is_file(), reason="no bundle checked out")
def test_no_never_merge_pair_shares_a_bare_alias():
    # closes the whole class 1.2 fixed one instance of: for every
    # never_merge: pair (concepts a human confirmed are genuinely distinct,
    # e.g. the two Hans NPCs), no bare name may survive as a link_targets()
    # candidate (canonical_name or alias, len >= 4, minus alias_block) on
    # more than one member -- otherwise link_targets() has to guess.
    data = _registry_data(REAL_REGISTRY)
    blocks = _load_alias_blocks(REAL_REGISTRY)
    names_by_concept: dict[str, set[str]] = {}
    for entry in data.get("entities") or []:
        cid = str(entry.get("concept_id", "")).strip()
        names = [str(entry.get("canonical_name", "")).strip(), *(entry.get("aliases") or [])]
        blocked = blocks.get(cid, set())
        names_by_concept[cid] = {
            n.strip().lower() for n in names if n.strip() and len(n.strip()) >= 4 and n.strip().lower() not in blocked
        }

    violations = []
    for pair in _load_never_merge_pairs(REAL_REGISTRY):
        sets = [names_by_concept.get(cid, set()) for cid in pair]
        shared = set.intersection(*sets) if sets else set()
        if shared:
            violations.append((sorted(pair), sorted(shared)))
    assert not violations, f"never_merge pair(s) still share a linkable bare name: {violations}"


def test_link_targets_drops_ambiguous_shared_name():
    # A name owned by two concepts must be dropped entirely, not resolved by
    # a tiebreak (better-attested wins) -- see synthesize.py::link_targets.
    from pnp_okf.synthesize import link_targets

    a = CanonicalEntity(
        concept_id="npcs/hans_wirt_zum_gruenen_sichelmond",
        type=EntityType.NPC,
        canonical_name="Hans, Wirt zum Grünen Sichelmond",
        aliases=["Hans"],
        mentions=[],
    )
    b = CanonicalEntity(
        concept_id="npcs/hans_soldat_aus_breska",
        type=EntityType.NPC,
        canonical_name="Hans, Soldat aus Breska",
        aliases=["Hans"],
        mentions=[MentionRef(session_id="s1", date="2026-01-01", url="u", citation_ts="0", note="n")],
    )
    targets = link_targets([a, b])
    assert "Hans" not in targets
    assert targets["Hans, Wirt zum Grünen Sichelmond"] == a.concept_id
    assert targets["Hans, Soldat aus Breska"] == b.concept_id


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
