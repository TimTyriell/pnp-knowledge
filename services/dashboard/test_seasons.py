import json
import sys

import app
import pytest
import seasons
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge"
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    kb = tmp_path / "kb"
    monkeypatch.setattr(app, "KNOWLEDGE_DIR", knowledge)
    monkeypatch.setattr(app, "default_transcript_dir", lambda: transcripts)
    monkeypatch.setattr(seasons, "KB_DIR", kb)
    seasons._current.clear()
    with TestClient(app.app, client=("127.0.0.1", 45000)) as http:
        yield http
    seasons._current.clear()


def _episodes(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "episodes.yaml").write_text(
        "seasons:\n  P:\n    label: Prolog\n  1:\n    label: Staffel 1\n"
        "episodes:\n  - video_id: old123\n    season: P\n"
        "  - video_id: new123\n    season: '1'\n",
        encoding="utf-8",
    )


def test_status_reports_frozen_and_active_seasons(client, tmp_path):
    _episodes(tmp_path / "knowledge")
    transcripts = tmp_path / "transcripts"
    (transcripts / "2025-01-01_old_old123.json").touch()
    (transcripts / "2026-01-01_new_new123.json").touch()
    manifest = {
        "schema": 1,
        "season": "P",
        "sessions": [{"session_id": "2025-01-01_old_old123"}],
        "frozen_at": "2026-11-11T10:00:00Z",
        "prompt_versions": {"extract": "6"},
        "models": {},
        "counts": {"sessions": 1},
    }
    path = tmp_path / "knowledge" / "frozen" / "P" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    extraction = path.parent / "extract" / "2025-01-01_old_old123.json"
    extraction.parent.mkdir()
    extraction.write_text("{}", encoding="utf-8")

    response = client.get("/api/seasons")
    assert response.status_code == 200
    rows = {row["key"]: row for row in response.json()["seasons"]}
    assert rows["P"]["frozen"]["counts"] == {"sessions": 1}
    assert rows["P"]["episodes"] == rows["P"]["transcripts"] == 1
    assert rows["1"]["frozen"] is None


def test_status_lists_transcripts_without_an_episode(client, tmp_path):
    _episodes(tmp_path / "knowledge")
    (tmp_path / "transcripts" / "2025-01-01_unlisted_unknown.json").touch()
    response = client.get("/api/seasons")
    assert response.status_code == 200
    assert response.json()["unlisted_transcripts"] == ["2025-01-01_unlisted_unknown"]


def test_estimate_uses_fixed_argv(monkeypatch):
    seen = []

    class Result:
        returncode = 0
        stdout = "estimate"
        stderr = ""

    monkeypatch.setattr(seasons, "_run", lambda argv, **kwargs: (seen.append(argv) or Result()))
    result = seasons.estimate("run", ["P"], {"P"})
    assert seen == [[sys.executable, "-m", "pnp_okf.cli", "run", "--thaw", "P", "--estimate"]]
    assert result == {"ok": True, "output": "estimate"}


def test_unknown_season_is_rejected(client, monkeypatch):
    called = []
    monkeypatch.setattr(seasons, "_run", lambda *args, **kwargs: called.append(args))
    _episodes(app.KNOWLEDGE_DIR)
    response = client.post("/api/runs/estimate", json={"thaw": ["P; rm -rf"]})
    assert response.status_code == 400
    assert called == []


def test_unknown_kind_is_rejected(client, monkeypatch):
    called = []
    monkeypatch.setattr(seasons, "_run", lambda *args, **kwargs: called.append(args))
    _episodes(app.KNOWLEDGE_DIR)
    response = client.post("/api/runs/estimate", json={"kind": "extract"})
    assert response.status_code == 400
    assert called == []


def test_start_requires_confirm(client, monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(seasons, "_popen", lambda *args, **kwargs: called.append(args))
    _episodes(app.KNOWLEDGE_DIR)
    response = client.post("/api/runs", json={})
    assert response.status_code == 400
    assert called == []


def test_second_start_is_a_conflict(client, monkeypatch):
    _episodes(app.KNOWLEDGE_DIR)

    class Process:
        def poll(self):
            return None

    monkeypatch.setattr(seasons, "_popen", lambda *args, **kwargs: Process())
    assert client.post("/api/runs", json={"confirm": True}).status_code == 202
    assert client.post("/api/runs", json={"confirm": True}).status_code == 409


def test_freeze_is_refused_while_running(client, monkeypatch):
    _episodes(app.KNOWLEDGE_DIR)

    class Process:
        def poll(self):
            return None

    monkeypatch.setattr(seasons, "_popen", lambda *args, **kwargs: Process())
    assert client.post("/api/runs", json={"confirm": True}).status_code == 202
    response = client.post("/api/seasons/P/freeze", json={})
    assert response.status_code == 409


def test_current_reports_exit_code_and_log_tail(client, tmp_path, monkeypatch):
    log = tmp_path / "run.log"
    log.write_text("\n".join(f"line {n}" for n in range(50)), encoding="utf-8")

    class Process:
        def poll(self):
            return 0

    seasons._current.update(proc=Process(), kind="run", thaw=[], log=log, started_at="2026-11-11T10:00:00Z")
    current = client.get("/api/runs/current").json()
    assert current["running"] is False
    assert current["exit_code"] == 0
    assert len(current["log_tail"].splitlines()) == 40


def test_remote_client_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "KNOWLEDGE_DIR", tmp_path)
    with TestClient(app.app, client=("192.0.2.10", 123)) as remote:
        assert remote.get("/api/seasons").status_code == 403
        assert remote.post("/api/runs", json={"confirm": True}).status_code == 403
