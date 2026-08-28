"""A run must not silently abandon most of the previous registry's identities.

The 2026-08 incident this guards against: a forced re-extraction resampled
the LLM for 61 already-ingested sessions, rewording most extracted entity
names. Since concept_id is derived from the extracted name, that renamed
~800 concepts in one pass, and prune_orphans (which only sees the bundle,
after emit has already overwritten it under the new names) had nothing left
to catch. check_rename_safety runs one stage earlier, right after resolve,
comparing the freshly resolved concept ids against the *previous* registry's
— before a single file is written.
"""

from pathlib import Path

import yaml

from pnp_okf.emit import check_rename_safety
from pnp_okf.models import CanonicalEntity, EntityType


def _ent(concept_id: str) -> CanonicalEntity:
    return CanonicalEntity(concept_id=concept_id, type=EntityType.NPC, canonical_name="X")


def _write_registry(path: Path, concept_ids: list[str]) -> None:
    doc = {"entities": [{"concept_id": cid} for cid in concept_ids]}
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_no_registry_yet_is_always_safe(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    assert check_rename_safety(registry, [_ent("npcs/a")]) is True


def test_mass_rename_is_refused(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    _write_registry(registry, [f"npcs/c{i}" for i in range(40)])

    # Every previously known id is gone; the resolved set is entirely new ids.
    resolved = [_ent(f"npcs/renamed_{i}") for i in range(40)]
    assert check_rename_safety(registry, resolved) is False


def test_normal_growth_is_allowed(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    old_ids = [f"npcs/c{i}" for i in range(40)]
    _write_registry(registry, old_ids)

    # 38 survive untouched, 1 renamed, 5 brand new -> well under 10%.
    resolved = [_ent(cid) for cid in old_ids[:38]]
    resolved.append(_ent("npcs/c39_renamed"))
    resolved.extend(_ent(f"npcs/new_{i}") for i in range(5))
    assert check_rename_safety(registry, resolved) is True


def test_guard_is_off_below_the_size_floor(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    _write_registry(registry, ["npcs/a", "npcs/b", "npcs/c"])

    # All 3 renamed -- would be 100% abandoned, but too small to be a signal.
    resolved = [_ent("npcs/x"), _ent("npcs/y"), _ent("npcs/z")]
    assert check_rename_safety(registry, resolved) is True


def test_allow_rename_overrides_the_guard(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    _write_registry(registry, [f"npcs/c{i}" for i in range(40)])

    resolved = [_ent(f"npcs/renamed_{i}") for i in range(40)]
    assert check_rename_safety(registry, resolved, allow=True) is True
