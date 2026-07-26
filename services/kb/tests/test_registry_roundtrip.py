"""write_registry rewrites the file every run — hand-set keys must survive.

``ignore:`` and ``never_merge:`` are curated by hand and consumed by resolve
and dedup. A rewrite that only knows about ``merge:`` and ``entities:`` drops
them silently, so the next run re-materializes suppressed concepts and
re-proposes rejected merges.
"""

from pathlib import Path

import yaml

from pnp_okf.models import CanonicalEntity, EntityType
from pnp_okf.resolve import write_registry


def test_unknown_top_level_keys_survive_a_rewrite(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    reg.write_text(
        yaml.safe_dump(
            {
                "merge": {"warzul": "deities/vharzul"},
                "ignore": ["locations/bruecke", "locations/turm"],
                "never_merge": [["characters/miko", "characters/myko"]],
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    write_registry(
        [CanonicalEntity(concept_id="npcs/x", type=EntityType.NPC, canonical_name="X")],
        reg,
    )

    doc = yaml.safe_load(reg.read_text(encoding="utf-8"))
    assert doc["ignore"] == ["locations/bruecke", "locations/turm"]
    assert doc["never_merge"] == [["characters/miko", "characters/myko"]]
    assert doc["merge"] == {"warzul": "deities/vharzul"}   # still preserved
    assert [e["concept_id"] for e in doc["entities"]] == ["npcs/x"]
