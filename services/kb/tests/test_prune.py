"""Concepts that disappear must stop being published.

Emit only writes, so a merged-away or renamed concept used to keep its file
forever: stale body, stale links, duplicate titles in validation, and still
served by the API and the wiki export as though it were current.
"""

from pathlib import Path

from pnp_okf.emit import prune_orphans
from pnp_okf.models import CanonicalEntity, EntityType


def _ent(concept_id, etype):
    return CanonicalEntity(concept_id=concept_id, type=etype, canonical_name="X")


def test_orphaned_concept_is_removed_and_live_ones_kept(tmp_path: Path):
    (tmp_path / "characters").mkdir()
    (tmp_path / "npcs").mkdir()
    (tmp_path / "characters" / "dodo.md").write_text("live", encoding="utf-8")
    (tmp_path / "characters" / "esterossa.md").write_text("merged away", encoding="utf-8")
    (tmp_path / "characters" / "index.md").write_text("# idx", encoding="utf-8")
    (tmp_path / "npcs" / "lenra.md").write_text("live", encoding="utf-8")

    removed = prune_orphans(
        tmp_path,
        [_ent("characters/dodo", EntityType.CHARACTER), _ent("npcs/lenra", EntityType.NPC)],
    )

    assert removed == 1
    assert not (tmp_path / "characters" / "esterossa.md").exists()
    assert (tmp_path / "characters" / "dodo.md").exists()
    assert (tmp_path / "npcs" / "lenra.md").exists()
    assert (tmp_path / "characters" / "index.md").exists()  # never an orphan


def test_sessions_are_never_pruned(tmp_path: Path):
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "2025-04-09.md").write_text("recap", encoding="utf-8")
    assert prune_orphans(tmp_path, []) == 0
    assert (tmp_path / "sessions" / "2025-04-09.md").exists()
