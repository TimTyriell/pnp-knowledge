"""World status and attitude (T7): derived from the state ledger, no model.

Rules are T00 §4.6 / §4.7 and docs/plans/T7-world-status-and-attitude.md. The
claim-never-overrides-observed rule is the one that matters most: a retelling
by an NPC must never change what the table saw happen.
"""

import logging
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
    load_status_rules,
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


# --- O3: a run of equal values is one fact, since its first record ---------

URL_P12 = "https://www.youtube.com/watch?v=ddddddddddd"
URL_P46 = "https://www.youtube.com/watch?v=eeeeeeeeeee"
URL_S1 = "https://www.youtube.com/watch?v=fffffffffff"
EPISODES_O3 = Episodes([
    {"id": "P-12", "video_id": "ddddddddddd"},
    {"id": "P-46", "video_id": "eeeeeeeeeee"},
    {"id": "S1-01-A", "video_id": "fffffffffff"},
])
O3_SESSIONS = [("P-12", "2025-06-17", URL_P12), ("P-46", "2026-01-10", URL_P46),
               ("S1-01-A", "2026-11-01", URL_S1)]


def _o3_ledger(per_session: list) -> Ledger:
    return _ledger([(sid, date, url, state)
                    for (sid, date, url), state in zip(O3_SESSIONS, per_session, strict=False)])


def test_a_status_repeated_across_sessions_is_since_its_first_record():
    led = _o3_ledger([
        SessionState(status_changes=[_status("Rotunas", "dead")]),
        SessionState(status_changes=[_status("Rotunas", "dead")]),
        SessionState(status_changes=[_status("Rotunas", "dead", ts="00:00:01")]),
    ])
    frag, _ = world_state_by_concept(led, _names(), EPISODES_O3)

    assert frag["characters/rotunas"]["world_status"] == {
        "value": "dead", "since": "P-12", "at": "02:02:27", "evidence": "observed"}
    assert "world_status_history" not in frag["characters/rotunas"]


def test_a_claim_and_an_observation_of_the_same_value_are_separate_runs():
    # Evidence is part of the run key: the claim stays visible (T7), the
    # observed record is current.
    led = _o3_ledger([
        SessionState(status_changes=[
            _status("Rotunas", "dead", ts="00:10:00", evidence="claimed", claimed_by="Seraph")]),
        SessionState(status_changes=[_status("Rotunas", "dead", ts="00:20:00")]),
    ])
    frag, _ = world_state_by_concept(led, _names(), EPISODES_O3)

    assert frag["characters/rotunas"]["world_status"] == {
        "value": "dead", "since": "P-46", "at": "00:20:00", "evidence": "observed"}
    assert [h["evidence"] for h in frag["characters/rotunas"]["world_status_history"]] == [
        "claimed", "observed"]


def test_dead_alive_dead_stays_three_records_and_current_is_the_last():
    led = _o3_ledger([
        SessionState(status_changes=[_status("Rotunas", "dead")]),
        SessionState(status_changes=[_status("Rotunas", "alive")]),
        SessionState(status_changes=[_status("Rotunas", "dead")]),
    ])
    frag, _ = world_state_by_concept(led, _names(), EPISODES_O3)

    history = frag["characters/rotunas"]["world_status_history"]
    assert [h["value"] for h in history] == ["dead", "alive", "dead"]
    assert frag["characters/rotunas"]["world_status"]["since"] == "S1-01-A"


def test_attitude_friendly_then_hostile_is_current_hostile():
    led = _o3_ledger([
        SessionState(attitudes=[_attitude("Vitius", "Gruppe", "friendly")]),
        SessionState(attitudes=[_attitude("Vitius", "Gruppe", "friendly")]),
        SessionState(attitudes=[_attitude("Vitius", "Gruppe", "hostile")]),
    ])
    frag, _ = world_state_by_concept(led, _names(), EPISODES_O3)

    assert frag["npcs/vitius"]["attitude"] == [
        {"toward": "party", "value": "hostile", "since": "S1-01-A", "at": "01:10:00", "evidence": "observed"}]


def test_attitude_friendly_three_times_has_since_of_the_first():
    led = _o3_ledger([SessionState(attitudes=[_attitude("Vitius", "Gruppe", "friendly")])] * 3)
    frag, _ = world_state_by_concept(led, _names(), EPISODES_O3)

    assert frag["npcs/vitius"]["attitude"][0]["since"] == "P-12"


# --- O3 status_rules: drop is a human correction, keyed by concept@session --

def test_dropped_session_is_skipped_and_since_moves_to_the_next_run():
    led = _o3_ledger([
        SessionState(status_changes=[_status("Rotunas", "dead")]),
        SessionState(status_changes=[_status("Rotunas", "dead")]),
        SessionState(status_changes=[_status("Rotunas", "dead")]),
    ])
    frag, unmatched = world_state_by_concept(
        led, _names(), EPISODES_O3, drop={("characters/rotunas", "P-12")})

    assert unmatched == []
    assert frag["characters/rotunas"]["world_status"]["since"] == "P-46"
    assert "world_status_history" not in frag["characters/rotunas"]


def test_drop_applies_to_attitude_records_too():
    led = _o3_ledger([
        SessionState(attitudes=[_attitude("Vitius", "Gruppe", "friendly")]),
        SessionState(attitudes=[_attitude("Vitius", "Gruppe", "hostile")]),
    ])
    frag, _ = world_state_by_concept(led, _names(), EPISODES_O3, drop={("npcs/vitius", "P-12")})

    assert frag["npcs/vitius"]["attitude"][0]["value"] == "hostile"
    assert frag["npcs/vitius"]["attitude"][0]["since"] == "P-46"


def test_load_status_rules_reads_the_drop_family(tmp_path: Path):
    (tmp_path / "entity_rules.yaml").write_text(
        "status_rules:\n  drop:\n  - characters/rotunas@P-12\n  - npcs/vitius@P-46\n", encoding="utf-8")
    assert load_status_rules(tmp_path / "entity_registry.yaml") == {
        ("characters/rotunas", "P-12"), ("npcs/vitius", "P-46")}


def test_load_status_rules_is_empty_without_the_family(tmp_path: Path):
    (tmp_path / "entity_rules.yaml").write_text("{}\n", encoding="utf-8")
    assert load_status_rules(tmp_path / "entity_registry.yaml") == set()


def test_load_status_rules_ignores_and_logs_malformed_entries(tmp_path: Path, caplog):
    (tmp_path / "entity_rules.yaml").write_text(
        "status_rules:\n  drop:\n  - characters/rotunas@P-12\n  - characters/rotunas\n"
        "  - '@P-46'\n  - npcs/vitius@\n  - 42\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pnp_okf.state"):
        assert load_status_rules(tmp_path / "entity_registry.yaml") == {("characters/rotunas", "P-12")}
    assert caplog.text.count("malformed") == 4
