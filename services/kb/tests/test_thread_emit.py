"""Thread concepts (T6): deterministic files, session sections, pruning, validation.

No model is involved anywhere here. A thread body is the dated Verlauf of
the ledger's entries, so every line can be checked against its cited moment
(T00 §4.5, decision D3).
"""

from pathlib import Path

from pnp_okf.emit import (
    emit_indexes,
    emit_sessions,
    emit_threads,
    prune_threads,
    threads_by_session,
)
from pnp_okf.episodes import Episodes
from pnp_okf.models import (
    CanonicalEntity,
    EntityType,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.okf import split_document
from pnp_okf.state import Ledger, NameIndex, SessionState, ThreadUpdate
from pnp_okf.validate import validate_bundle

URL = "https://www.youtube.com/watch?v=abc"


def _update(tid: str, title: str, status: str, note: str = "Die Gruppe handelt.",
            involves: list[str] | None = None) -> ThreadUpdate:
    return ThreadUpdate(thread_id=tid, title=title, kind="quest", status=status,
                        note=note, citation_ts="00:01:00", involves=involves or [])


def _ledger_one_thread(status_s2: str | None = None) -> Ledger:
    led = Ledger()
    led.apply("s1", "2026-01-01", URL, SessionState(threads=[_update("NEU", "Evakuierung", "open")]))
    if status_s2:
        led.apply("s2", "2026-02-01", URL, SessionState(
            threads=[_update("threads/evakuierung", "Evakuierung", status_s2, "Erledigt.")]))
    return led


def test_emit_threads_writes_a_thread_concept_with_its_verlauf(tmp_path: Path):
    led = _ledger_one_thread()
    written, unmatched = emit_threads(tmp_path, list(led.threads.values()), NameIndex([]), Episodes(), None)

    assert written == ["threads/evakuierung"]
    assert unmatched == []
    fm, body = split_document((tmp_path / "threads" / "evakuierung.md").read_text(encoding="utf-8"))
    assert fm["type"] == "Thread"
    assert fm["id"] == "THREAD_EVAKUIERUNG"
    assert fm["kind"] == "quest" and fm["thread_status"] == "open"
    assert fm["opened"] == "2026-01-01"
    assert "resolved" not in fm
    assert fm["sources"][0]["url_at"] == f"{URL}&t=60s"
    assert "## Verlauf" in body
    assert "eröffnet" in body and "Session 2026-01-01 @ 00:01:00" in body
    assert "# Belege" in body


def test_resolved_thread_records_when_it_was_resolved(tmp_path: Path):
    led = _ledger_one_thread(status_s2="resolved")
    emit_threads(tmp_path, list(led.threads.values()), NameIndex([]), Episodes(), None)

    fm, body = split_document((tmp_path / "threads" / "evakuierung.md").read_text(encoding="utf-8"))
    assert fm["thread_status"] == "resolved"
    assert fm["resolved"] == "2026-02-01"
    assert "erledigt" in body


def test_involves_link_to_concepts_and_unknown_names_are_reported(tmp_path: Path):
    led = Ledger()
    led.apply("s1", "2026-01-01", URL, SessionState(
        threads=[_update("NEU", "Evakuierung", "open", involves=["Xenia Rotkam", "Unbekannt"])]))
    names = NameIndex([CanonicalEntity(
        concept_id="npcs/xenia_rotkam", type=EntityType.NPC, canonical_name="Xenia Rotkam")])

    written, unmatched = emit_threads(tmp_path, list(led.threads.values()), names, Episodes(), None)

    assert unmatched == ["threads/evakuierung: Unbekannt"]
    fm, body = split_document((tmp_path / "threads" / "evakuierung.md").read_text(encoding="utf-8"))
    assert fm["involves"] == ["npcs/xenia_rotkam"]
    assert "[Xenia Rotkam](/npcs/xenia_rotkam.md)" in body


def test_prune_threads_deletes_only_stale_thread_files(tmp_path: Path):
    d = tmp_path / "threads"
    d.mkdir()
    for name in ("a", "b", "index"):
        (d / f"{name}.md").write_text("x", encoding="utf-8")

    removed = prune_threads(tmp_path, {"threads/a"})

    assert removed == 1
    assert (d / "a.md").exists() and (d / "index.md").exists()
    assert not (d / "b.md").exists()


def test_threads_by_session_groups_entries_with_step_words():
    led = _ledger_one_thread(status_s2="resolved")
    by_session = threads_by_session(led.threads.values())

    assert by_session["s1"] == [("threads/evakuierung", "Evakuierung", "eröffnet", "Die Gruppe handelt.")]
    assert by_session["s2"] == [("threads/evakuierung", "Evakuierung", "erledigt", "Erledigt.")]


def test_emit_sessions_renders_offene_faeden_between_anchors_and_entities(tmp_path: Path):
    transcript = SessionTranscript(session_id="s1", date="2026-01-01", url=URL, title="S1")
    extraction = SessionExtraction(recap="Recap.", entities=[])
    threads = {"s1": [("threads/evakuierung", "Evakuierung", "eröffnet", "Die Gruppe handelt.")]}

    entries = emit_sessions(tmp_path, {"s1": transcript}, {"s1": extraction},
                            threads_by_session=threads)

    text = (tmp_path / "sessions" / "2026-01-01.md").read_text(encoding="utf-8")
    assert "# Offene Fäden" in text
    assert "- [Evakuierung](/threads/evakuierung.md) — eröffnet: Die Gruppe handelt." in text
    assert entries  # the session still indexed


def test_emit_indexes_lists_threads_by_status(tmp_path: Path):
    led = _ledger_one_thread()
    emit_indexes(tmp_path, [], [], threads=list(led.threads.values()))

    text = (tmp_path / "threads" / "index.md").read_text(encoding="utf-8")
    assert "## Offen" in text
    assert "[Auftrag: Evakuierung](evakuierung.md)" in text


def _good_thread(path: Path, kind: str = "quest") -> None:
    name = path.stem.upper()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: Thread\n"
        f"id: THREAD_{name}\n"
        f"title: {name}\n"
        "description: Ein Faden.\n"
        "tags:\n- threads\n"
        f"kind: {kind}\n"
        "thread_status: open\n"
        "timestamp: '2026-01-01T00:00:00Z'\n"
        "---\n\nEin Faden.\n",
        encoding="utf-8",
    )


def test_validate_accepts_a_well_formed_thread_and_flags_a_bad_kind(tmp_path: Path):
    _good_thread(tmp_path / "threads" / "x.md")
    _good_thread(tmp_path / "threads" / "y.md", kind="foo")

    report = validate_bundle(tmp_path)

    assert [cid for cid, _ in report.invalid_thread_fields] == ["threads/y"]
    assert "threads/x" not in report.missing_required_fields
    assert report.integrity_ok
