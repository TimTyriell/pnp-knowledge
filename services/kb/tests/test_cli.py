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


def test_extraction_model_is_selectable_and_defaults_to_the_strong_model(monkeypatch):
    """Extraction routes through the tier system like synthesis does.

    It always used the strong model because cli.py handed _extract_all the raw
    cfg and never called for_tier(). Extraction is ~a quarter of a rebuild's
    bill, so whether it can be moved should be a config decision, not a code
    change -- but the default must not shift underneath anyone.
    """

    from pnp_okf.config import DeepSeekConfig

    for var in ("DEEPSEEK_MODEL", "DEEPSEEK_LIGHT_MODEL", "DEEPSEEK_EXTRACT_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")

    cfg = DeepSeekConfig.from_env()
    assert cfg.for_tier("extract").model == "deepseek-v4-pro", "default must not move"
    assert cfg.for_tier("deep").model == "deepseek-v4-pro"
    assert cfg.for_tier("standard").model == "deepseek-v4-flash"

    monkeypatch.setenv("DEEPSEEK_EXTRACT_MODEL", "deepseek-v4-flash")
    assert DeepSeekConfig.from_env().for_tier("extract").model == "deepseek-v4-flash"


def test_estimate_makes_no_llm_call(tmp_path: Path, monkeypatch, capsys):
    """--estimate must price the run without spending anything.

    The ~$6.50 rebuild cost was learned by paying it. The whole point of this
    flag is that the number arrives before the money leaves, so the one thing
    it must never do is call the model. base_url points at an unroutable host,
    so any real call fails loudly rather than silently succeeding.
    """

    _make_transcript(tmp_path, "2025-03-26_RF_abc")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("PNP_PRICE_IN_DEEPSEEK_V4_PRO", "0.66")
    monkeypatch.setenv("PNP_PRICE_OUT_DEEPSEEK_V4_PRO", "1.98")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))

    ret = main([
        "run", "--estimate",
        "--transcripts", str(tmp_path),
        "--bundle", str(tmp_path / "bundle"),
        "--cache", str(tmp_path / "cache"),
    ])

    assert ret == 0
    out = capsys.readouterr().out
    assert "extract" in out.lower()
    assert "estimate" in out.lower()
    # It must not have written a run record either -- nothing happened.
    assert not (tmp_path / "state" / "run_in_progress.json").exists()


def _seed_extract_cache(tmp_path: Path, stem: str) -> None:
    """Put one session in the cache the way a real run would leave it."""

    from pnp_okf.config import DeepSeekConfig
    from pnp_okf.extract import _cache_key, _cache_path, _store_cache
    from pnp_okf.ingest import load_transcripts
    from pnp_okf.models import SessionExtraction

    cfg = DeepSeekConfig.from_env().for_tier("extract")
    (transcript,) = [t for t in load_transcripts(tmp_path) if t.session_id == stem]
    key = _cache_key(transcript, cfg)
    _store_cache(
        _cache_path(tmp_path / "cache", transcript, key), key,
        SessionExtraction(recap="Eine Sitzung.", entities=[]),
    )


def _estimate(tmp_path: Path, *extra: str) -> int:
    return main([
        "run", "--estimate",
        "--transcripts", str(tmp_path),
        "--bundle", str(tmp_path / "bundle"),
        "--cache", str(tmp_path / "cache"),
        *extra,
    ])


def test_estimate_prices_the_flags_it_was_given(tmp_path: Path, monkeypatch, capsys):
    """--reextract and --force must show up in the number, not be ignored.

    _estimate_run walked the cache and never looked at either flag, so
    `run --estimate --reextract` reported a warm cache and printed "this run
    is free" for a run that re-extracts every session at full price. That is
    exactly the combination whose cost the flag exists to reveal.
    """

    _make_transcript(tmp_path, "2025-03-26_RF_abc")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    _seed_extract_cache(tmp_path, "2025-03-26_RF_abc")

    assert _estimate(tmp_path) == 0
    assert "1 cached, 0 to call" in capsys.readouterr().out

    assert _estimate(tmp_path, "--reextract") == 0
    out = capsys.readouterr().out
    assert "0 cached, 1 to call" in out, (
        "--reextract ignores the extract cache, so every session is a call"
    )
    assert "this run is free" not in out


def _capture_extract_model(monkeypatch) -> dict:
    """Record the model _extract_all is actually handed, without calling out."""

    from pnp_okf.models import SessionExtraction

    seen: dict[str, str] = {}

    def _fake(transcript, cfg, cache_dir, *, client=None, force=False):
        seen["model"] = cfg.model
        return SessionExtraction(recap="r", entities=[])

    monkeypatch.setattr("pnp_okf.cli.extract_session", _fake)
    return seen


def test_extract_and_dedup_use_the_same_tier_as_run(tmp_path: Path, monkeypatch):
    """All three commands must agree on the extraction model.

    cmd_extract and cmd_dedup handed _extract_all the untiered cfg while
    _run_pipeline passed for_tier("extract"), so with DEEPSEEK_EXTRACT_MODEL
    set they keyed the cache on a different model: `pnp extract` populated a
    cache `pnp run` never reads, and `pnp dedup` -- documented as running on
    cached extractions and never re-reading transcripts -- silently paid for
    a complete re-extraction.
    """

    _make_transcript(tmp_path, "2025-03-26_RF_abc")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("DEEPSEEK_EXTRACT_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr("pnp_okf.cli.propose", lambda *a, **k: [])

    common = [
        "--transcripts", str(tmp_path),
        "--bundle", str(tmp_path / "bundle"),
        "--cache", str(tmp_path / "cache"),
    ]

    seen = _capture_extract_model(monkeypatch)
    assert main(["extract", *common]) == 0
    assert seen["model"] == "deepseek-v4-flash", "pnp extract ignored the extract tier"

    (tmp_path / "bundle").mkdir(exist_ok=True)
    (tmp_path / "bundle" / "entity_rules.yaml").write_text("merge: []\n", encoding="utf-8")
    seen = _capture_extract_model(monkeypatch)
    main(["dedup", *common])
    assert seen["model"] == "deepseek-v4-flash", "pnp dedup ignored the extract tier"
