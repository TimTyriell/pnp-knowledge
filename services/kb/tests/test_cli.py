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


