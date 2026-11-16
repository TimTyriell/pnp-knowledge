"""O7: an entity only ever carries a subtype from its own type's closed list.

A mention folded into a concept of another directory (a ``merge:`` rule) keeps
the type of the directory, but its subtype used to be copied verbatim from the
mention, so a Location subtype ``Wildnis`` landed on a faction.
"""

from pathlib import Path

import yaml
from pnp_okf.models import EntityMention, EntityType, SessionExtraction, SessionTranscript
from pnp_okf.resolve import resolve_entities


def _run(tmp_path: Path, mentions_by_session, merge=None):
    reg = tmp_path / "entity_registry.yaml"
    reg.write_text(
        yaml.safe_dump({"merge": merge or {}, "split": [], "never_merge": []}),
        encoding="utf-8",
    )
    ex = {
        sid: SessionExtraction(recap="r", entities=ms)
        for sid, ms in mentions_by_session.items()
    }
    tr = {
        sid: SessionTranscript(session_id=sid, date=f"2026-03-{i + 1:02d}", url="u")
        for i, sid in enumerate(mentions_by_session)
    }
    return resolve_entities(ex, tr, reg)


def _mention(name, etype, subtype=""):
    return EntityMention(
        name=name, type=etype, subtype=subtype, note="n", citation_ts="00:01:00"
    )


def test_cross_directory_merge_drops_foreign_subtype(tmp_path: Path):
    ents = _run(
        tmp_path,
        {"s1": [_mention("Wilde Horde", EntityType.LOCATION, "Wildnis")]},
        merge={"Wilde Horde": "factions/wilde_horde"},
    )
    assert len(ents) == 1
    assert ents[0].concept_id == "factions/wilde_horde"
    assert ents[0].type == EntityType.FACTION
    assert ents[0].subtype == ""


def test_valid_subtype_of_own_type_is_kept(tmp_path: Path):
    ents = _run(tmp_path, {"s1": [_mention("Schwert", EntityType.ITEM, "Waffe")]})
    assert ents[0].subtype == "Waffe"


def test_type_without_a_list_carries_no_subtype(tmp_path: Path):
    ents = _run(tmp_path, {"s1": [_mention("Gorthak", EntityType.NPC, "Volk")]})
    assert ents[0].subtype == ""


def test_subtype_adoption_from_later_mention_still_works(tmp_path: Path):
    ents = _run(
        tmp_path,
        {
            "s1": [_mention("Rabenhof", EntityType.LOCATION, "")],
            "s2": [_mention("Rabenhof", EntityType.LOCATION, "Gebäude")],
        },
    )
    assert len(ents) == 1
    assert ents[0].subtype == "Gebäude"
