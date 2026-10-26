"""The state pass's ledger is a pure fold over cached per-session outputs (T5).

Threads keep their identity through the fold: a thread minted once keeps its
id no matter how the model words it later (T00 §4.5).
"""

from pnp_okf.state import (
    AttitudeChange,
    Ledger,
    SessionState,
    StatusChange,
    ThreadUpdate,
    render_open_threads,
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
