"""``canonical_name:`` and ``important:`` are settable from the rules file.

Both are hand-set decisions. Leaving them only in the generated inventory meant
the reason for a pin ("Holodarn is a mishearing, the Titan is Huludan") had
nowhere to live, because that file is rewritten by a comment-stripping dump.
"""

from pathlib import Path

from pnp_okf.models import EntityMention, EntityType, SessionExtraction, SessionTranscript
from pnp_okf.resolve import (
    _load_canonical_names,
    _load_important,
    _load_preserved_aliases,
    resolve_entities,
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


# --- hand-added aliases must actually reach link_targets(), not just the
# registry file (2026-08-29 bundle-quality audit: entity_registry.yaml's own
# header calls aliases: "appended to, never clobbered", but a hand-added
# spelling with no matching raw mention this run — e.g. "Lenra", the
# concept's own historical slug, once every transcript mention said
# "Landra"/"Hack" instead — never reached the entity's aliases list, so it
# was never linkable even though it was faithfully preserved in the file) ---

REGISTRY_WITH_HAND_ALIAS = """\
entities:
- concept_id: npcs/lenra
  type: NPC
  canonical_name: Landra, die Hag
  aliases:
  - Lenra
  - Hack
  mention_count: 1
"""


def test_load_preserved_aliases_reads_the_entities_section(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(REGISTRY_WITH_HAND_ALIAS, encoding="utf-8")
    assert _load_preserved_aliases(registry) == {"npcs/lenra": ["Lenra", "Hack"]}


def test_hand_added_alias_is_linkable_even_without_a_matching_mention(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(REGISTRY_WITH_HAND_ALIAS, encoding="utf-8")

    transcript = SessionTranscript(session_id="s1", date="2026-06-03", url="https://x")
    extraction = SessionExtraction(
        recap="r",
        entities=[
            EntityMention(
                # A raw mention slugifying to the concept's own id ("lenra")
                # is what creates the CanonicalEntity in the first place;
                # a *different*-spelled mention (e.g. "Landra") would land
                # here too, but only via the separate fuzzy-merge pass
                # (merge_near_duplicates, see test_identity.py) which this
                # test intentionally doesn't need to exercise.
                name="Lenra",
                type=EntityType.NPC,
                note="n",
                citation_ts="00:01:00",
            )
        ],
    )
    entities = resolve_entities({"s1": extraction}, {"s1": transcript}, registry)
    (entity,) = entities
    assert entity.concept_id == "npcs/lenra"
    # The hand-maintained "Hack" is now on the entity itself, not just
    # preserved in the file -- link_targets() (synthesize.py) reads exactly
    # this list, so a document mentioning "Hack" in prose can now resolve.
    assert "Hack" in entity.aliases
