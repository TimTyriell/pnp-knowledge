from __future__ import annotations

import json
from pathlib import Path

from pnp_okf.cli import main


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
