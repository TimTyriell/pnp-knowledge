"""The state pass's ledger is a pure fold over cached per-session outputs (T5).

Threads keep their identity through the fold: a thread minted once keeps its
id no matter how the model words it later (T00 §4.5).
"""

from pathlib import Path

import yaml
from pnp_okf.state import (
    GLOSSARY_FILENAME,
    AttitudeChange,
    Ledger,
    SessionState,
    StatusChange,
    ThreadUpdate,
    build_glossary,
    load_glossary,
    render_glossary,
    render_open_threads,
    render_state_report,
    write_glossary,
)


def _t(tid="NEU", title="Evakuierung", status="open", **kw):
    return ThreadUpdate(thread_id=tid, title=title, kind="quest", status=status,
                        note=kw.get("note", "n"), citation_ts="00:01:00",
                        involves=kw.get("involves", []), evidence=kw.get("evidence", "observed"))


def test_new_thread_is_minted_from_its_title():
    led = Ledger()
    led.apply("s1", "2026-01-01", "u", SessionState(threads=[_t()]))
    assert list(led.threads) == ["threads/evakuierung"]
    assert led.threads["threads/evakuierung"].opened == "s1"


def test_same_title_twice_gets_a_suffix():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t(), _t()]))
    assert list(led.threads) == ["threads/evakuierung", "threads/evakuierung_2"]


def test_update_by_id_keeps_identity_even_if_title_changes():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t()]))
    led.apply("s2", "d", "u", SessionState(threads=[_t("threads/evakuierung", "Ganz anderer Titel", "resolved")]))
    rec = led.threads["threads/evakuierung"]
    assert rec.title == "Evakuierung" and rec.status == "resolved" and rec.resolved == "s2"
    assert len(led.threads) == 1


def test_unknown_id_mints_and_warns():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t("threads/gibts_nicht", "X")]))
    assert "threads/x" in led.threads
    assert any("unknown thread id" in w for w in led.warnings)


def test_reopening_clears_resolved():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t(status="resolved")]))
    led.apply("s2", "d", "u", SessionState(threads=[_t("threads/evakuierung", status="open")]))
    assert led.threads["threads/evakuierung"].resolved is None


def test_open_threads_render_is_deterministic_and_excludes_closed():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t(title="B"), _t(title="A", status="resolved")]))
    text = render_open_threads(led)
    assert "threads/b" in text and "threads/a" not in text
    assert render_open_threads(Ledger()) == "(keine offenen Fäden)"


def test_status_and_attitude_are_recorded_with_evidence():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(
        status_changes=[StatusChange(name="Rotunas", value="dead", note="n", citation_ts="02:02:27")],
        attitudes=[AttitudeChange(name="Vitius", toward="", value="hostile", note="n",
                                  citation_ts="00:10:00", evidence="claimed")],
    ))
    assert led.statuses[0].value == "dead" and led.statuses[0].entry.evidence == "observed"
    assert led.attitudes[0].toward == "Gruppe" and led.attitudes[0].entry.evidence == "claimed"


def test_involves_is_deduplicated_in_first_seen_order():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t(involves=["Xenia", "Hof"])]))
    led.apply("s2", "d", "u", SessionState(threads=[_t("threads/evakuierung", involves=["Hof", "Brim"])]))
    assert led.threads["threads/evakuierung"].involves == ["Xenia", "Hof", "Brim"]


# --- frozen glossary (commit 2) -------------------------------------------

def _registry(tmp_path: Path, entities: list[dict]) -> Path:
    path = tmp_path / "entity_registry.yaml"
    path.write_text(yaml.safe_dump({"entities": entities}, allow_unicode=True), encoding="utf-8")
    return path


def test_build_glossary_excludes_events_caps_aliases_and_sorts(tmp_path):
    reg = _registry(tmp_path, [
        {"type": "Event", "canonical_name": "Schlacht", "aliases": []},
        {"type": "NPC", "canonical_name": "Xenia", "aliases": ["a", "b", "c", "d", "e"]},
        {"type": "Character", "canonical_name": "Zed", "aliases": []},
        {"type": "Character", "canonical_name": "Abel", "aliases": []},
        {"type": "Location", "canonical_name": "Hof", "aliases": ["", "Halbling"]},
    ])
    rows = build_glossary(reg)
    assert [r["name"] for r in rows] == ["Abel", "Zed", "Xenia", "Hof"]
    assert rows[2]["aliases"] == ["a", "b", "c"]
    assert rows[3]["aliases"] == ["Halbling"]


def test_write_then_load_roundtrips_and_keeps_header(tmp_path):
    rows = [{"type": "NPC", "name": "Xenia", "aliases": ["Xen"]}]
    path = write_glossary(tmp_path, rows)
    assert path.name == GLOSSARY_FILENAME
    assert path.read_text(encoding="utf-8").startswith("# Frozen name list")
    assert load_glossary(tmp_path) == rows


def test_load_glossary_missing_file_is_empty(tmp_path):
    assert load_glossary(tmp_path) == []


def test_render_glossary_is_byte_identical_across_calls():
    rows = [{"type": "NPC", "name": "Xenia", "aliases": ["Xen", "X"]},
            {"type": "Item", "name": "Schwert", "aliases": []}]
    first, second = render_glossary(rows), render_glossary(rows)
    assert first == second
    assert first == "- NPC: Xenia (auch: Xen, X)\n- Item: Schwert"


# --- review report (commit 4) ----------------------------------------------

def test_report_lists_each_thread_status_change_and_warning():
    led = Ledger()
    led.apply("s1", "2026-01-01", "u", SessionState(
        threads=[_t()],
        status_changes=[StatusChange(name="Rotunas", value="dead", note="n", citation_ts="02:02:27")],
    ))
    led.apply("s2", "2026-01-08", "u", SessionState(threads=[_t("threads/gibts_nicht", "Y")]))
    text = render_state_report(led)
    assert "threads/evakuierung" in text and "threads/y" in text
    assert "Rotunas" in text and "dead" in text
    assert "unknown thread id" in text
