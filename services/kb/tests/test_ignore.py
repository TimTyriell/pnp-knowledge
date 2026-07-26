"""Generic buckets must be suppressible entirely, not just merged."""

from pathlib import Path

import yaml

from pnp_okf.models import EntityMention, EntityType, SessionExtraction, SessionTranscript
from pnp_okf.resolve import resolve_entities


def _setup(tmp_path: Path, ignore):
    reg = tmp_path / "entity_registry.yaml"
    reg.write_text(yaml.safe_dump({"merge": {}, "ignore": ignore}), encoding="utf-8")
    ex = {
        "s1": SessionExtraction(
            recap="r",
            entities=[
                EntityMention(name="Brücke", type=EntityType.LOCATION, note="n", citation_ts="00:01:00"),
                EntityMention(name="Breska", type=EntityType.LOCATION, note="n", citation_ts="00:02:00"),
            ],
        )
    }
    tr = {"s1": SessionTranscript(session_id="s1", date="2025-01-01", url="u")}
    return ex, tr, reg


def test_ignored_concept_never_materializes(tmp_path: Path):
    ex, tr, reg = _setup(tmp_path, ["locations/bruecke"])
    ids = {e.concept_id for e in resolve_entities(ex, tr, reg)}
    assert "locations/bruecke" not in ids   # dropped outright
    assert "locations/breska" in ids        # neighbours unaffected


def test_without_ignore_the_bucket_still_appears(tmp_path: Path):
    ex, tr, reg = _setup(tmp_path, [])
    ids = {e.concept_id for e in resolve_entities(ex, tr, reg)}
    assert "locations/bruecke" in ids
