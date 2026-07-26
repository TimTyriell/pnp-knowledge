"""Subtype grouping replaces collection concepts.

A "Verträge" page would be a node with no referent; in a property graph it
would link unrelated contracts and invent multi-hop paths between them. A
grouping is a view — a heading here, a label query later.
"""

from pathlib import Path

from pnp_okf.emit import emit_indexes
from pnp_okf.models import CanonicalEntity, EntityType


def _e(cid, name, subtype=""):
    return CanonicalEntity(
        concept_id=cid, type=EntityType.EVENT, canonical_name=name, subtype=subtype
    )


def test_index_groups_by_subtype_under_the_type_heading(tmp_path: Path):
    emit_indexes(
        tmp_path,
        [
            _e("events/kampf_am_pass", "Kampf am Pass", "Kampf"),
            _e("events/vertrag_mit_dem_daemon", "Vertrag mit dem Dämon", "Vertrag"),
            _e("events/namenlos", "Namenlos"),
        ],
        [],
    )
    text = (tmp_path / "events" / "index.md").read_text(encoding="utf-8")

    assert "# Ereignisse" in text          # type stays the page heading
    assert "## Kampf" in text              # subtypes nest beneath it
    assert "## Vertrag" in text
    assert "## Ohne Kategorie" in text     # unlabelled entries are not dropped
    assert "kampf_am_pass.md" in text and "namenlos.md" in text
    # No collection *entity* is invented for the grouping.
    assert not (tmp_path / "events" / "vertraege.md").exists()


def test_types_without_a_vocabulary_stay_flat(tmp_path: Path):
    emit_indexes(
        tmp_path,
        [
            CanonicalEntity(
                concept_id="characters/dodo", type=EntityType.CHARACTER,
                canonical_name="Dodo",
            )
        ],
        [],
    )
    text = (tmp_path / "characters" / "index.md").read_text(encoding="utf-8")
    assert "# Charaktere" in text
    assert "##" not in text
