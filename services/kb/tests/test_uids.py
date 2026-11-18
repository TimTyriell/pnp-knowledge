"""B1 / ADR-007: opaque concept uids, minted once and kept across renames."""

from pathlib import Path

import yaml
from pnp_okf.emit import check_rename_safety, emit_entity
from pnp_okf.models import (
    CanonicalEntity,
    EntityMention,
    EntityType,
    MentionRef,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.okf import split_document
from pnp_okf.resolve import (
    UID_RE,
    _load_canonical_names,
    _load_important,
    assign_uids,
    load_uid_index,
    resolve_entities,
    write_registry,
)


def _ent(cid, name, etype=EntityType.NPC, aliases=()):
    return CanonicalEntity(
        concept_id=cid, type=etype, canonical_name=name, aliases=list(aliases),
        mentions=[MentionRef(session_id="s1", date="2026-01-01", url="u", citation_ts="00:00:01", note="n")],
    )


def _run_once(reg: Path, entities):
    uids = assign_uids(entities, reg)
    write_registry(entities, reg, uids)
    return uids


def _registry(reg: Path) -> dict:
    return yaml.safe_load(reg.read_text(encoding="utf-8"))


def test_new_concepts_get_well_formed_unique_uids(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    uids = _run_once(reg, [_ent("npcs/a", "A"), _ent("npcs/b", "B")])
    assert all(UID_RE.match(u) for u in uids.values())
    assert len(set(uids.values())) == 2
    assert {e["concept_id"]: e["uid"] for e in _registry(reg)["entities"]} == uids


def test_uid_is_preserved_across_runs(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    first = _run_once(reg, [_ent("npcs/a", "A")])
    second = _run_once(reg, [_ent("npcs/a", "A"), _ent("npcs/b", "B")])
    assert second["npcs/a"] == first["npcs/a"]
    assert second["npcs/b"] != first["npcs/a"]


def test_rename_sharing_a_name_inherits_the_uid(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    first = _run_once(reg, [_ent("npcs/hexe_landra", "Hexe Landra", aliases=["Landra"])])
    # The re-extraction words it "Landra, die Hag": a new id, one shared name.
    second = _run_once(reg, [_ent("npcs/landra_die_hag", "Landra, die Hag", aliases=["Landra"])])
    assert second["npcs/landra_die_hag"] == first["npcs/hexe_landra"]
    # The uid now lives only on the live concept, never twice.
    retired = {e["concept_id"]: e for e in _registry(reg)["retired"]}
    assert retired["npcs/hexe_landra"]["uid"] != first["npcs/hexe_landra"]


def test_unrelated_new_concept_does_not_inherit(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    first = _run_once(reg, [_ent("npcs/harald", "Harald")])
    second = _run_once(reg, [_ent("npcs/berthold", "Berthold")])
    assert second["npcs/berthold"] != first["npcs/harald"]
    # The retired concept keeps its uid, so it gets it back if it recurs.
    third = _run_once(reg, [_ent("npcs/harald", "Harald"), _ent("npcs/berthold", "Berthold")])
    assert third["npcs/harald"] == first["npcs/harald"]


def test_inheritance_respects_the_identity_space(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    first = _run_once(reg, [_ent("locations/zebros", "Zebros", EntityType.LOCATION)])
    second = _run_once(reg, [_ent("factions/zebros_reich", "Reich", EntityType.FACTION, aliases=["Zebros"])])
    assert second["factions/zebros_reich"] != first["locations/zebros"]


def test_retired_without_uid_gets_one_and_keeps_it_on_return(tmp_path: Path):
    # An O1-demoted concept leaves entities: for retired:. It must come back
    # under the same uid when its id recurs.
    reg = tmp_path / "entity_registry.yaml"
    reg.write_text(yaml.safe_dump({"retired": [
        {"concept_id": "items/schluessel", "type": "Item", "canonical_name": "Schlüssel", "aliases": []},
    ]}), encoding="utf-8")
    _run_once(reg, [_ent("npcs/a", "A")])
    minted = {e["concept_id"]: e["uid"] for e in _registry(reg)["retired"]}["items/schluessel"]
    assert UID_RE.match(minted)
    back = _run_once(reg, [_ent("npcs/a", "A"), _ent("items/schluessel", "Schlüssel", EntityType.ITEM)])
    assert back["items/schluessel"] == minted


def test_rules_may_name_a_concept_by_uid(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    uid = _run_once(reg, [_ent("npcs/thyrex", "T-Rex")])["npcs/thyrex"]
    (tmp_path / "entity_rules.yaml").write_text(
        f"important:\n- {uid}  # npcs/thyrex\ncanonical_name:\n  {uid}: Thyrex  # npcs/thyrex\n",
        encoding="utf-8",
    )
    assert "npcs/thyrex" in _load_important(reg)
    assert _load_canonical_names(reg)["npcs/thyrex"] == "Thyrex"
    assert load_uid_index(reg) == {uid: "npcs/thyrex"}


def test_uid_keyed_rule_applies_in_resolve(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    uid = _run_once(reg, [_ent("npcs/thyrex", "Thyrex")])["npcs/thyrex"]
    (tmp_path / "entity_rules.yaml").write_text(f"ignore:\n- {uid}\n", encoding="utf-8")
    ex = {"s1": SessionExtraction(recap="r", entities=[
        EntityMention(name="Thyrex", type=EntityType.NPC, note="n", citation_ts="00:00:01"),
        EntityMention(name="Berthold", type=EntityType.NPC, note="n", citation_ts="00:00:02"),
    ])}
    tr = {"s1": SessionTranscript(session_id="s1", date="2026-01-01", url="u")}
    assert [e.concept_id for e in resolve_entities(ex, tr, reg)] == ["npcs/berthold"]


def test_rename_guard_counts_a_uid_kept_rename_as_kept(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    before = [_ent(f"npcs/n{i}", f"Name {i}", aliases=[f"Alias {i}"]) for i in range(25)]
    _run_once(reg, before)
    # Every id moves, every concept still shares an alias with its old self.
    after = [_ent(f"npcs/m{i}", f"Neu {i}", aliases=[f"Alias {i}"]) for i in range(25)]
    assert not check_rename_safety(reg, after)  # by concept id: a mass rename
    assert check_rename_safety(reg, after, uids=assign_uids(after, reg))


def test_rename_guard_still_trips_on_a_real_mass_loss(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    _run_once(reg, [_ent(f"npcs/n{i}", f"Name {i}") for i in range(25)])
    after = [_ent(f"npcs/m{i}", f"Anders {i}") for i in range(25)]
    assert not check_rename_safety(reg, after, uids=assign_uids(after, reg))


def test_emit_writes_uid_after_id(tmp_path: Path):
    emit_entity(tmp_path, _ent("npcs/a", "A"), "Text.", uid="c_abcdefgh")
    fm, _ = split_document((tmp_path / "npcs" / "a.md").read_text(encoding="utf-8"))
    assert fm["uid"] == "c_abcdefgh"
    keys = list(fm)
    assert keys.index("uid") == keys.index("id") + 1
