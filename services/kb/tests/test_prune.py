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


def _seed_characters(tmp_path: Path, count: int) -> None:
    d = tmp_path / "characters"
    d.mkdir(exist_ok=True)
    for i in range(count):
        (d / f"c{i}.md").write_text("live", encoding="utf-8")


def test_mass_deletion_is_refused_without_allow(tmp_path: Path):
    """A run whose entity set covers only a sliver of the bundle (a partial
    --limit/--session run, or a re-extraction that renamed most concepts at
    once) must not be read as '39 concepts vanished' and prune them all."""

    _seed_characters(tmp_path, 40)  # only 40, well past the size-20 floor
    # Only one of the 40 on-disk concepts still exists in this run.
    removed = prune_orphans(tmp_path, [_ent("characters/c0", EntityType.CHARACTER)])

    assert removed == 0
    assert all((tmp_path / "characters" / f"c{i}.md").exists() for i in range(40))


def test_mass_deletion_proceeds_with_allow(tmp_path: Path):
    _seed_characters(tmp_path, 40)
    removed = prune_orphans(
        tmp_path, [_ent("characters/c0", EntityType.CHARACTER)], allow=True
    )

    assert removed == 39
    assert (tmp_path / "characters" / "c0.md").exists()
    assert not (tmp_path / "characters" / "c1.md").exists()


def test_small_bundle_prunes_normally_below_the_size_floor(tmp_path: Path):
    """The ratio guard only means something once there's enough to be a
    signal; below that a plain 1-of-3 stale file is still just pruned."""

    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "dodo.md").write_text("live", encoding="utf-8")
    (tmp_path / "characters" / "esterossa.md").write_text("stale", encoding="utf-8")

    removed = prune_orphans(tmp_path, [_ent("characters/dodo", EntityType.CHARACTER)])

    assert removed == 1
    assert not (tmp_path / "characters" / "esterossa.md").exists()
