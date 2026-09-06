from __future__ import annotations

import json
from pathlib import Path

from pnp_okf.cli import _build_parser, main


def _make_transcript(tmp_path: Path, stem: str) -> None:
    payload = {
        "video_date": stem[:10],
        "video_url": "https://youtu.be/x",
        "video_title": "Test",
        "language": "de",
        "segments": [{"start": 1.0, "end": 2.0, "speaker": "GM", "text": "Hallo Welt"}],
    }
    (tmp_path / f"{stem}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_check_missing_config_exits_2(tmp_path: Path, monkeypatch):
    _make_transcript(tmp_path, "2025-03-26_RF_abc")
    # Ensure no DeepSeek env vars leak in from the real environment.
    for var in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.delenv(var, raising=False)
    ret = main(["check", "--transcripts", str(tmp_path)])
    assert ret == 2


def test_check_with_valid_config(tmp_path: Path, monkeypatch):
    _make_transcript(tmp_path, "2025-03-26_RF_abc")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    ret = main(["check", "--transcripts", str(tmp_path)])
    assert ret == 0


def test_force_and_reextract_are_independent_flags():
    """--force (re-roll synthesis prose) must not also re-roll extraction —
    that coupling is what let a forced re-run resample every entity's name
    and silently rename ~800 concepts (see test_incremental_ingest.py)."""

    parser = _build_parser()

    plain = parser.parse_args(["run"])
    assert plain.force is False
    assert plain.reextract is False

    forced = parser.parse_args(["run", "--force"])
    assert forced.force is True
    assert forced.reextract is False

    reextracted = parser.parse_args(["run", "--reextract"])
    assert reextracted.force is False
    assert reextracted.reextract is True


def test_run_allow_prune_flag_defaults_off():
    parser = _build_parser()
    assert parser.parse_args(["run"]).allow_prune is False
    assert parser.parse_args(["run", "--allow-prune"]).allow_prune is True


def test_run_allow_rename_flag_defaults_off():
    parser = _build_parser()
    assert parser.parse_args(["run"]).allow_rename is False
    assert parser.parse_args(["run", "--allow-rename"]).allow_rename is True




def test_a_killed_run_leaves_a_trace_the_next_run_records(tmp_path: Path, monkeypatch):
    """A hard kill must not vanish.

    _write_run_status only runs at the end of a run, so a SIGKILL or a machine
    sleeping mid-synthesis wrote nothing at all. On 2026-09-05 that is exactly
    what happened: a run died at ~15:37 leaving a half-written bundle, and
    history.jsonl has no row for it -- the failure was discovered days later by
    reading link targets. The marker written at start is the trace.
    """

    from pnp_okf.cli import _begin_run, _write_run_status

    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path))

    _begin_run("2026-09-05T15:37:00Z")          # this run gets killed
    _begin_run("2026-09-05T18:00:00Z")          # the next run notices

    rows = [
        json.loads(line)
        for line in (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["started_at"] == "2026-09-05T15:37:00Z"
    assert rows[0]["ok"] is False
    assert "killed" in rows[0]["error"]


def test_a_finished_run_leaves_no_stale_marker(tmp_path: Path, monkeypatch):
    from pnp_okf.cli import _begin_run, _write_run_status

    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path))

    _begin_run("2026-09-05T18:00:00Z")
    _write_run_status("2026-09-05T18:00:00Z", ok=True, error=None, counts={})
    _begin_run("2026-09-05T19:00:00Z")

    rows = [
        json.loads(line)
        for line in (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [r["ok"] for r in rows] == [True]
