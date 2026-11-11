"""--scope (D1 phase 3): which sessions may be sent to a model for extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pnp_okf.cli as cli
import pytest
from pnp_okf import extract as extract_mod
from pnp_okf.config import ConfigError, DeepSeekConfig
from pnp_okf.frozen import FrozenStore, write_json
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import SessionExtraction

LABEL = "agent:claude:claude-opus-5-5"
STEPS = ("extract", "deep", "standard", "state", "dedup")
ALL_AGENT = [arg for s in STEPS for arg in ("--model", f"{s}={LABEL}")]
A, B, C = "2026-01-01_a", "2026-01-02_b", "2026-01-03_c"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    # setenv-then-delenv records the original value, so the PNP_MODEL_* vars
    # that main() sets are restored on teardown.
    for var in [f"PNP_MODEL_{s.upper()}" for s in STEPS] + [
        "DEEPSEEK_MODEL", "DEEPSEEK_LIGHT_MODEL", "DEEPSEEK_EXTRACT_MODEL",
        "DEEPSEEK_STATE_MODEL", "PNP_STRICT_MODEL", "PNP_AGENT_DIR",
    ]:
        monkeypatch.setenv(var, "placeholder")
        monkeypatch.delenv(var)
    monkeypatch.setenv("PNP_AGENT_DIR", str(tmp_path / "agent"))
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    extract_mod._NO_STRUCTURED_OUTPUTS.clear()
    extract_mod._PROBED.clear()


def _transcripts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "transcripts"
    d.mkdir(exist_ok=True)
    for sid in (A, B, C):
        (d / f"{sid}.json").write_text(json.dumps({
            "video_date": sid[:10], "video_url": f"https://youtu.be/{sid[-1]}",
            "segments": [{"start": 1.0, "end": 2.0, "speaker": "GM", "text": f"Hallo {sid}"}],
        }), encoding="utf-8")
    return d


def _cfg() -> DeepSeekConfig:
    return DeepSeekConfig(api_key="", model=LABEL, base_url="https://example.invalid", step="extract")


def _cache(cache_dir: Path, transcript) -> None:
    """Make one session a cache hit, the way a previous run would have."""
    cfg = _cfg()
    key = extract_mod._cache_key(transcript, cfg)
    extract_mod._store_cache(
        extract_mod._cache_path(cache_dir, transcript, key), key,
        SessionExtraction(recap="Ein Rückblick."),
    )


def _freeze_a(knowledge: Path) -> FrozenStore:
    season = knowledge / "frozen" / "P"
    write_json(season / "manifest.json", {
        "schema": 1, "season": "P", "sessions": [{"session_id": A, "dialogue_sha": ""}],
    })
    write_json(season / "extract" / f"{A}.json", SessionExtraction(recap="Gefroren.").model_dump(mode="json"))
    return FrozenStore.load(knowledge)


def _scope(tmp_path: Path, scope: str) -> set[str]:
    transcripts = load_transcripts(_transcripts_dir(tmp_path))
    # A: frozen. B: cached. C: nothing.
    frozen = _freeze_a(tmp_path / "knowledge")
    cache = tmp_path / "cache"
    _cache(cache, next(t for t in transcripts if t.session_id == B))
    return cli._scope_ids(transcripts, scope, frozen, _cfg(), cache)


@pytest.mark.parametrize(("scope", "expected"), [
    ("all", {A, B, C}),
    ("active", {B, C}),        # A is frozen, so not active
    ("pending", {C}),          # A is frozen and B is cached
    (C, {C}),                  # full session id
    ("2026-01-02", {B}),       # date
    ("2026-01-01_a,2026-01-03_c", {A, C}),
])
def test_scope_selects_sessions(tmp_path, scope, expected):
    assert _scope(tmp_path, scope) == expected


def test_a_named_session_that_does_not_exist_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="2026-09-09"):
        _scope(tmp_path, "2026-09-09")


def test_scope_flag_is_on_run_and_extract_only():
    parser = cli._build_parser()
    assert parser.parse_args(["extract", "--scope", "pending"]).scope == "pending"
    assert parser.parse_args(["run", "--scope", "active"]).scope == "active"
    assert parser.parse_args(["extract"]).scope == "all"
    with pytest.raises(SystemExit):
        parser.parse_args(["state", "--scope", "all"])


def test_out_of_scope_session_with_nothing_cached_exits_2(tmp_path, caplog):
    # A is out of scope and has no cache: it must not be silently dropped.
    rc = cli.main(["extract", "--no-api", *ALL_AGENT, "--scope", B,
                   "--transcripts", str(_transcripts_dir(tmp_path)),
                   "--cache", str(tmp_path / "cache")])
    assert rc == 2
    assert A in caplog.text
    assert not (tmp_path / "agent").exists()


def test_only_in_scope_sessions_are_sent_to_the_agent(tmp_path):
    # A and C are out of scope but cached: reused. Only B, in scope, is sent.
    transcripts = load_transcripts(_transcripts_dir(tmp_path))
    cache = tmp_path / "cache"
    for t in transcripts:
        if t.session_id != B:
            _cache(cache, t)
    rc = cli.main(["extract", "--no-api", *ALL_AGENT, "--scope", B,
                   "--transcripts", str(_transcripts_dir(tmp_path)), "--cache", str(cache)])
    assert rc == 4
    requests = list((tmp_path / "agent" / "extract").glob("*.request.json"))
    assert len(requests) == 1
    text = requests[0].read_text(encoding="utf-8")
    assert B in text
    assert A not in text and C not in text
