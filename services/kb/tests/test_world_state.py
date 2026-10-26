"""World status and attitude (T7): derived from the state ledger, no model.

Rules are T00 §4.6 / §4.7 and docs/plans/T7-world-status-and-attitude.md. The
claim-never-overrides-observed rule is the one that matters most: a retelling
by an NPC must never change what the table saw happen.
"""

from pathlib import Path

from pnp_okf.emit import emit_entity, insert_before_belege
from pnp_okf.episodes import Episodes
from pnp_okf.models import CanonicalEntity, EntityType
from pnp_okf.okf import split_document
from pnp_okf.state import (
    AttitudeChange,
    Ledger,
    NameIndex,
    SessionState,
    StatusChange,
    render_stand_section,
    world_state_by_concept,
)
from pnp_okf.validate import validate_bundle

URL_P34 = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
URL_P40 = "https://www.youtube.com/watch?v=bbbbbbbbbbb"
URL_P01 = "https://www.youtube.com/watch?v=ccccccccccc"
EPISODES = Episodes([
    {"id": "P-01", "video_id": "ccccccccccc"},
    {"id": "P-34", "video_id": "aaaaaaaaaaa"},
    {"id": "P-40", "video_id": "bbbbbbbbbbb"},
])
ENTITIES = [
    CanonicalEntity(concept_id="characters/rotunas", type=EntityType.CHARACTER, canonical_name="Rotunas"),
    CanonicalEntity(concept_id="characters/lindo_laut", type=EntityType.CHARACTER, canonical_name="Lindo Laut"),
    CanonicalEntity(concept_id="npcs/vitius", type=EntityType.NPC, canonical_name="Vitius"),
    CanonicalEntity(concept_id="items/schwert", type=EntityType.ITEM, canonical_name="Schwert"),
]


def _status(name, value, ts="02:02:27", evidence="observed", claimed_by="") -> StatusChange:
    return StatusChange(name=name, value=value, note="n", citation_ts=ts,
                        evidence=evidence, claimed_by=claimed_by)


def _attitude(name, toward, value, ts="01:10:00") -> AttitudeChange:
    return AttitudeChange(name=name, toward=toward, value=value, note="n", citation_ts=ts)


def _ledger(sessions: list[tuple[str, str, str, SessionState]]) -> Ledger:
    led = Ledger()
    for sid, date, url, state in sessions:
        led.apply(sid, date, url, state)
    return led


def _names() -> NameIndex:
    return NameIndex(ENTITIES)


TITLES = {e.concept_id: e.canonical_name for e in ENTITIES}


def test_observed_death_beats_a_later_claim_and_both_stay_in_history():
    led = _ledger([
        ("s1", "2026-04-09", URL_P34, SessionState(status_changes=[_status("Rotunas", "dead")])),
        ("s2", "2026-08-04", URL_P40, SessionState(status_changes=[
            _status("Rotunas", "dead", ts="00:30:00", evidence="claimed", claimed_by="Seraph")])),
    ])
    frag, unmatched = world_state_by_concept(led, _names(), EPISODES)

    assert unmatched == []
    current = frag["characters/rotunas"]["world_status"]
    assert current == {"value": "dead", "since": "P-34", "at": "02:02:27", "evidence": "observed"}
    history = frag["characters/rotunas"]["world_status_history"]
    assert len(history) == 2
    assert history[1]["evidence"] == "claimed" and history[1]["claimed_by"] == "Seraph"


def test_later_claim_never_overrides_observed_alive():
    led = _ledger([
        ("s1", "2026-01-01", URL_P01, SessionState(status_changes=[_status("Rotunas", "alive", ts="00:12:00")])),
        ("s2", "2026-08-04", URL_P40, SessionState(status_changes=[
            _status("Rotunas", "dead", ts="00:30:00", evidence="claimed", claimed_by="Seraph")])),
    ])
    frag, _ = world_state_by_concept(led, _names(), EPISODES)

    assert frag["characters/rotunas"]["world_status"]["value"] == "alive"
    stand = render_stand_section(frag["characters/rotunas"], TITLES)
    assert "Status: lebendig seit P-01" in stand
    assert "tot laut Seraph" in stand


def test_status_not_allowed_for_the_directory_is_unmatched_not_emitted():
    led = _ledger([
        ("s1", "2026-01-01", URL_P34, SessionState(status_changes=[
            _status("Rotunas", "destroyed"), _status("Schwert", "destroyed")])),
    ])
    frag, unmatched = world_state_by_concept(led, _names(), EPISODES)

    assert "characters/rotunas" not in frag
    assert frag["items/schwert"]["world_status"]["value"] == "destroyed"
    assert any(line.startswith("Rotunas: destroyed") for line in unmatched)


def test_unknown_name_for_status_is_unmatched():
    led = _ledger([("s1", "2026-01-01", URL_P34, SessionState(status_changes=[_status("Niemand", "dead")]))])
    frag, unmatched = world_state_by_concept(led, _names(), EPISODES)

    assert frag == {}
    assert any(line.startswith("Niemand: dead") for line in unmatched)


def test_attitude_toward_group_is_party_and_toward_a_pc_is_its_concept():
    led = _ledger([
        ("s1", "2026-01-01", URL_P34, SessionState(attitudes=[
            _attitude("Vitius", "Gruppe", "hostile"),
            _attitude("Vitius", "Lindo Laut", "friendly", ts="01:20:00")])),
    ])
    frag, unmatched = world_state_by_concept(led, _names(), EPISODES)

    attitudes = frag["npcs/vitius"]["attitude"]
    assert {(a["toward"], a["value"]) for a in attitudes} == {
        ("party", "hostile"), ("characters/lindo_laut", "friendly")}
    assert unmatched == []


def test_attitude_toward_an_unknown_name_is_unmatched():
    led = _ledger([("s1", "2026-01-01", URL_P34, SessionState(attitudes=[
        _attitude("Vitius", "Jemand Fremdes", "wary")]))])
    frag, unmatched = world_state_by_concept(led, _names(), EPISODES)

    assert "attitude" not in frag.get("npcs/vitius", {})
    assert any("Jemand Fremdes" in line for line in unmatched)


def test_attitude_on_an_item_is_unmatched_not_emitted():
    led = _ledger([("s1", "2026-01-01", URL_P34, SessionState(attitudes=[
        _attitude("Schwert", "Gruppe", "hostile")]))])
    frag, unmatched = world_state_by_concept(led, _names(), EPISODES)

    assert frag == {}
    assert any(line.startswith("Schwert: attitude") for line in unmatched)


def test_history_only_appears_with_more_than_one_entry():
    led = _ledger([("s1", "2026-01-01", URL_P34, SessionState(status_changes=[_status("Rotunas", "dead")]))])
    frag, _ = world_state_by_concept(led, _names(), EPISODES)
    assert "world_status_history" not in frag["characters/rotunas"]


def test_empty_ledger_yields_nothing():
    assert world_state_by_concept(Ledger(), _names(), EPISODES) == ({}, [])
    assert render_stand_section({}, TITLES) == ""


def test_stand_section_lists_status_history_and_attitudes():
    led = _ledger([
        ("s1", "2026-01-01", URL_P34, SessionState(
            status_changes=[_status("Rotunas", "dead", ts="02:02:27")],
            attitudes=[_attitude("Vitius", "Lindo Laut", "friendly", ts="01:20:00")])),
    ])
    frag, _ = world_state_by_concept(led, _names(), EPISODES)
    stand = render_stand_section(frag["characters/rotunas"], TITLES)
    assert stand.startswith("## Stand")
    assert "- Status: tot seit P-34 (beobachtet, 02:02:27)" in stand
    vitius = render_stand_section(frag["npcs/vitius"], TITLES)
    assert "- Haltung zu Lindo Laut: freundlich seit P-34 (beobachtet)" in vitius


def test_insert_before_belege_puts_the_section_above_the_heading():
    body = "Text.\n\n# Belege\n\n[P-34] Session 2026-04-09"
    out = insert_before_belege(body, "## Stand\n\n- Status: tot")
    assert out.index("## Stand") < out.index("# Belege")
    assert insert_before_belege(body, "") == body
    assert insert_before_belege("Text.", "## Stand").endswith("## Stand\n")


def test_emit_entity_writes_world_status_into_the_frontmatter(tmp_path: Path):
    fragment = {"world_status": {"value": "dead", "since": "P-34", "at": "02:02:27", "evidence": "observed"}}
    emit_entity(tmp_path, ENTITIES[0], "Text.", None, extra_frontmatter=fragment)

    fm, _ = split_document((tmp_path / "characters" / "rotunas.md").read_text(encoding="utf-8"))
    assert fm["world_status"] == fragment["world_status"]


def test_validate_flags_a_status_value_the_directory_may_not_carry(tmp_path: Path):
    emit_entity(tmp_path, ENTITIES[3], "Text.", None, extra_frontmatter={
        "world_status": {"value": "dead", "since": "P-34", "at": "02:02:27", "evidence": "observed"}})
    report = validate_bundle(tmp_path)

    assert [cid for cid, _ in report.invalid_world_status] == ["items/schwert"]
    assert report.integrity_ok  # advisory, like the thread checks
