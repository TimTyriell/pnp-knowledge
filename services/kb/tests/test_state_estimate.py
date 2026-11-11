import json

from pnp_okf.cli import main
from pnp_okf.frozen import write_json
from pnp_okf.state import write_glossary


def _fail_provider(cfg):
    raise AssertionError("state estimate called the provider")


def _cli_paths(root):
    transcripts = root / "transcripts"
    transcripts.mkdir()
    (transcripts / "2026-01-01_s1.json").write_text(json.dumps({
        "video_date": "2026-01-01", "video_url": "https://example.invalid/s1",
        "segments": [{"start": 0, "end": 1, "speaker": "A", "text": "Hallo"}],
    }), encoding="utf-8")
    knowledge = root / "knowledge"
    knowledge.mkdir()
    write_glossary(knowledge, [{"type": "NPC", "name": "Beispiel", "aliases": []}])
    return ["state", "--estimate", "--transcripts", str(transcripts),
            "--bundle", str(knowledge / "bundle" / "splitter"),
            "--cache", str(root / "cache")], knowledge


def _freeze(knowledge, *, complete):
    season = knowledge / "frozen" / "P"
    write_json(season / "extract" / "2026-01-01_s1.json", {"recap": "Fest"})
    if complete:
        write_json(season / "state" / "2026-01-01_s1.json", {
            "threads": [], "status_changes": [], "attitudes": [],
        })
    write_json(season / "manifest.json", {
        "schema": 1, "season": "P",
        "sessions": [{"session_id": "2026-01-01_s1", "dialogue_sha": ""}],
        "counts": {"sessions": 1, "state_sessions": int(complete)},
    })


def test_estimate_missing_frozen_state_is_blocked_without_provider_call(tmp_path, monkeypatch, capsys, caplog):
    import pnp_okf.state as state

    args, knowledge = _cli_paths(tmp_path)
    _freeze(knowledge, complete=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic")
    monkeypatch.setattr(state, "build_client", _fail_provider)

    assert main(args) == 2
    captured = capsys.readouterr()
    assert "frozen state is incomplete" in caplog.text.lower()
    assert captured.out == ""


def test_estimate_complete_frozen_state_succeeds(tmp_path, monkeypatch, capsys):
    import pnp_okf.state as state

    args, knowledge = _cli_paths(tmp_path)
    _freeze(knowledge, complete=True)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic")
    monkeypatch.setattr(state, "build_client", _fail_provider)

    assert main(args) == 0
    assert "1 cached, 0 would be called" in capsys.readouterr().out


def test_estimate_active_uncached_session_succeeds_without_provider_call(tmp_path, monkeypatch, capsys):
    import pnp_okf.state as state

    args, _ = _cli_paths(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic")
    monkeypatch.setattr(state, "build_client", _fail_provider)

    assert main(args) == 0
    assert "0 cached, 1 would be called" in capsys.readouterr().out
