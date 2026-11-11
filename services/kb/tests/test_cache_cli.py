from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from pathlib import Path

import pnp_okf.cli as cli
import pytest
from pnp_okf.cache_gc import LEDGER_NAME, load_ledger, write_ledger
from pnp_okf.config import DeepSeekConfig, Paths
from pnp_okf.extract import _cache_key, _cache_path, _store_cache
from pnp_okf.frozen import FrozenStore
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import EntityMention, EntityType, SessionExtraction, SessionTranscript

# 16 hex digits, so it matches the GC entry pattern, and it is never a real cache key.
STALE_KEY = "ffffffffffffffff"
NOW = "2026-11-11T00:00:00Z"


# Fixtures and helpers copied from test_cache_gc_live.py (not imported, so that file can change freely).

def _write_transcript_json(path: Path, date: str) -> None:
    path.write_text(
        json.dumps(
            {
                "video_date": date,
                "video_url": "https://youtu.be/x",
                "video_title": "Test",
                "language": "de",
                "segments": [{"start": 1.0, "end": 2.0, "speaker": "GM", "text": "Hallo Welt"}],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    for name in (
        "DEEPSEEK_MODEL",
        "DEEPSEEK_EXTRACT_MODEL",
        "PNP_EXTRACT_FREEZE_BEFORE",
        "PNP_EXTRACT_FREEZE_VERSION",
        "PNP_CACHE_DIR",
        "PNP_KNOWLEDGE_DIR",
        "PNP_BUNDLE_DIR",
        "PNP_TRANSCRIPT_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def _seed(cache: Path, transcript: SessionTranscript, extraction: SessionExtraction) -> None:
    """Put one session in the cache the way a real run would leave it."""
    cfg = DeepSeekConfig.from_env().for_tier("extract")
    key = _cache_key(transcript, cfg)
    _store_cache(_cache_path(cache, transcript, key), key, extraction)


def _by_id(transcripts: list[SessionTranscript], session_id: str) -> SessionTranscript:
    (t,) = [t for t in transcripts if t.session_id == session_id]
    return t


def _npc_extraction(name: str = "Wache Hans") -> SessionExtraction:
    return SessionExtraction(
        recap="Die Gruppe trifft einen NPC.",
        entities=[
            EntityMention(
                name=name,
                type=EntityType.NPC,
                note="Ein Wächter am Tor.",
                citation_ts="00:01:00",
            )
        ],
    )


def _empty_extraction() -> SessionExtraction:
    return SessionExtraction(recap="Eine Sitzung.", entities=[])


# CLI-specific helpers.

def _tree(tmp_path: Path, second: bool = False) -> tuple[Path, Path]:
    """Transcript dir and a knowledge root laid out like the real repo."""
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    _write_transcript_json(tdir / "2025-03-26_RF_a.json", "2025-03-26")
    if second:
        _write_transcript_json(tdir / "2025-04-02_RF_b.json", "2025-04-02")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "entity_rules.yaml").write_text("{}\n", encoding="utf-8")
    return tdir, knowledge


def _bundle(knowledge: Path) -> Path:
    return knowledge / "bundle" / "splitter_des_ewigen"


def _args(tmp_path: Path, tdir: Path, knowledge: Path, **over) -> argparse.Namespace:
    ns = argparse.Namespace(
        transcripts=str(tdir),
        bundle=str(knowledge / "bundle" / "campaign"),
        cache=str(tmp_path / "cache"),
        session=None,
        limit=None,
        force=False,
        reextract=False,
        workers=1,
        clean=False,
        allow_prune=False,
        allow_rename=False,
        thaw="",
    )
    ns.__dict__.update(over)
    return ns


def _tag_repo(tmp_path: Path, knowledge: Path, monkeypatch, tags=("s1", "s2", "s3")) -> None:
    """Make the knowledge root a git repo with session tags, so latest_session_tag sees them."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    # Stop git from finding an enclosing repo above the test tree.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(knowledge), "-c", "user.email=t@example.test",
             "-c", "user.name=test", "-c", "commit.gpgsign=false", *args],
            check=True, capture_output=True,
        )

    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "init")
    for t in tags:
        git("tag", t)


def _seed_stale(cache: Path, session_id: str, name: str = f"{STALE_KEY}.json") -> str:
    """An extract entry under a real session dir with a key the current config never reaches."""
    path = cache / "extract" / session_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path.relative_to(cache).as_posix()


def _warm_run(tmp_path: Path, monkeypatch, *, tags: bool = True, **over):
    """One seeded transcript, ready for _run_pipeline without any model call."""
    tdir, knowledge = _tree(tmp_path)
    if tags:
        _tag_repo(tmp_path, knowledge, monkeypatch)
    args = _args(tmp_path, tdir, knowledge, **over)
    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    transcripts = load_transcripts(paths.transcript_dir)
    for t in transcripts:
        _seed(paths.cache_dir, t, _npc_extraction())
    monkeypatch.setattr("pnp_okf.synthesize.build_client", lambda cfg: object())
    monkeypatch.setattr("pnp_okf.synthesize._call_llm", lambda *a, **k: "Text.")
    return args, paths, transcripts


def _gc_argv(tdir: Path, knowledge: Path, cache: Path, *extra: str) -> list[str]:
    return ["cache", "gc", *extra, "--transcripts", str(tdir),
            "--bundle", str(_bundle(knowledge)), "--cache", str(cache)]


# T4.1-T4.3: cache gc command.

def test_cache_gc_dry_run_deletes_nothing(tmp_path, env, monkeypatch, capsys):
    tdir, knowledge = _tree(tmp_path)
    _tag_repo(tmp_path, knowledge, monkeypatch)
    cache = tmp_path / "cache"
    t = load_transcripts(tdir)[0]
    _seed(cache, t, _npc_extraction())
    rel = _seed_stale(cache, t.session_id)
    write_ledger(cache, {rel: "s1"})

    rc = cli.main(_gc_argv(tdir, knowledge, cache, "--dry-run"))

    assert rc == 0
    assert f"would delete {rel}" in capsys.readouterr().out
    assert (cache / rel).exists()


def test_cache_gc_unknown_live_set_exits_2(tmp_path, env, monkeypatch):
    tdir, knowledge = _tree(tmp_path, second=True)
    _tag_repo(tmp_path, knowledge, monkeypatch)
    cache = tmp_path / "cache"
    transcripts = load_transcripts(tdir)
    _seed(cache, _by_id(transcripts, "2025-03-26_RF_a"), _empty_extraction())  # b is uncached

    rc = cli.main(_gc_argv(tdir, knowledge, cache))

    assert rc == 2
    assert not (cache / LEDGER_NAME).exists()


def test_cache_gc_blocked_exits_0_and_says_allow_mass(tmp_path, env, monkeypatch, capsys):
    tdir, knowledge = _tree(tmp_path)
    _tag_repo(tmp_path, knowledge, monkeypatch)
    cache = tmp_path / "cache"
    t = load_transcripts(tdir)[0]
    _seed(cache, t, _npc_extraction())  # 1 live extract entry
    rels = [_seed_stale(cache, t.session_id, f"{k}.json")
            for k in ("aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb")]  # 2 of 3 due: over 50%
    write_ledger(cache, {r: "s1" for r in rels})

    rc = cli.main(_gc_argv(tdir, knowledge, cache))

    out = capsys.readouterr().out
    assert rc == 0
    assert "--allow-mass" in out
    assert all((cache / r).exists() for r in rels)


# T4.4-T4.6: legacy trap (default cache, resolved from --bundle).

def _legacy_warm(tmp_path: Path, monkeypatch) -> Path:
    legacy = tmp_path / "legacy"
    (legacy / "extract" / "s" / "k.json").parent.mkdir(parents=True)
    (legacy / "extract" / "s" / "k.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "LEGACY_CACHE_DIR", legacy)
    return legacy


def test_legacy_trap_refuses_cold_default(tmp_path, env, monkeypatch, caplog):
    tdir, knowledge = _tree(tmp_path)
    (knowledge / "entity_registry.yaml").write_text("{}\n", encoding="utf-8")
    _legacy_warm(tmp_path, monkeypatch)  # default <knowledge>/cache stays empty

    rc = cli.main(["run", "--estimate", "--transcripts", str(tdir), "--bundle", str(_bundle(knowledge))])

    assert rc == 2
    assert "pnp cache migrate" in caplog.text


def test_legacy_trap_ignored_with_explicit_cache(tmp_path, env, monkeypatch, caplog):
    tdir, knowledge = _tree(tmp_path)
    (knowledge / "entity_registry.yaml").write_text("{}\n", encoding="utf-8")
    _legacy_warm(tmp_path, monkeypatch)

    cli.main(["run", "--estimate", "--transcripts", str(tdir), "--bundle", str(_bundle(knowledge)),
              "--cache", str(tmp_path / "explicit")])

    assert "pnp cache migrate" not in caplog.text


def test_legacy_trap_ignored_when_default_warm(tmp_path, env, monkeypatch, caplog):
    tdir, knowledge = _tree(tmp_path)
    (knowledge / "entity_registry.yaml").write_text("{}\n", encoding="utf-8")
    _legacy_warm(tmp_path, monkeypatch)
    default = knowledge / "cache"
    (default / "extract" / "s").mkdir(parents=True)
    (default / "extract" / "s" / "k.json").write_text("{}", encoding="utf-8")

    cli.main(["run", "--estimate", "--transcripts", str(tdir), "--bundle", str(_bundle(knowledge))])

    assert "pnp cache migrate" not in caplog.text


def test_legacy_trap_fires_when_only_synth_is_cold(tmp_path, env, monkeypatch, caplog):
    """One extract entry in the new location must not disarm the trap while the
    legacy synth half -- the pricier one -- would be re-bought."""
    tdir, knowledge = _tree(tmp_path)
    (knowledge / "entity_registry.yaml").write_text("{}\n", encoding="utf-8")
    legacy = _legacy_warm(tmp_path, monkeypatch)
    (legacy / "synth" / "c").mkdir(parents=True)
    (legacy / "synth" / "c" / "k.json").write_text("{}", encoding="utf-8")
    default = knowledge / "cache"
    (default / "extract" / "s").mkdir(parents=True)
    (default / "extract" / "s" / "k.json").write_text("{}", encoding="utf-8")

    rc = cli.main(["run", "--estimate", "--transcripts", str(tdir), "--bundle", str(_bundle(knowledge))])

    assert rc == 2
    assert "synth" in caplog.text and "pnp cache migrate" in caplog.text


# T4.7-T4.10: cache migrate.

def test_migrate_copies_and_never_deletes_source(tmp_path, env, capsys):
    src = tmp_path / "legacy"
    files = {
        "extract/s1/k1.json": '{"a": 1}\n',
        "synth/c1/k2.json": '{"b": 2}\n',
        "state/x/s.json": '{"c": 3}\n',
    }
    for rel, text in files.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(text, encoding="utf-8")
    dst = tmp_path / "cache"

    rc = cli.main(["cache", "migrate", "--from", str(src), "--cache", str(dst)])

    assert rc == 0
    assert "3 copied" in capsys.readouterr().out
    for rel, text in files.items():
        assert (dst / rel).read_text(encoding="utf-8") == text
        assert (src / rel).read_text(encoding="utf-8") == text


def test_migrate_skips_identical_and_crlf_equal(tmp_path, env, capsys):
    src, dst = tmp_path / "legacy", tmp_path / "cache"
    obj = {"entities": [1, 2, 3]}
    lf = (json.dumps(obj, indent=2) + "\n").encode("utf-8")
    same = b'{"same": true}\n'
    for base in (src, dst):
        (base / "extract" / "s").mkdir(parents=True)
    (src / "extract" / "s" / "a.json").write_bytes(same)
    (dst / "extract" / "s" / "a.json").write_bytes(same)
    (src / "extract" / "s" / "b.json").write_bytes(lf)
    (dst / "extract" / "s" / "b.json").write_bytes(lf.replace(b"\n", b"\r\n"))

    rc = cli.main(["cache", "migrate", "--from", str(src), "--cache", str(dst)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "2 identical" in out
    assert "0 conflict(s)" in out


def test_migrate_reports_conflict_exit_1(tmp_path, env, capsys):
    src, dst = tmp_path / "legacy", tmp_path / "cache"
    (src / "extract" / "s").mkdir(parents=True)
    (dst / "extract" / "s").mkdir(parents=True)
    (src / "extract" / "s" / "a.json").write_text('{"v": 1}\n', encoding="utf-8")
    (dst / "extract" / "s" / "a.json").write_text('{"v": 2}\n', encoding="utf-8")

    rc = cli.main(["cache", "migrate", "--from", str(src), "--cache", str(dst)])

    assert rc == 1
    assert "conflict (left untouched): extract/s/a.json" in capsys.readouterr().out
    assert (dst / "extract" / "s" / "a.json").read_text(encoding="utf-8") == '{"v": 2}\n'


def test_migrate_same_dir_exits_2(tmp_path, env, capsys):
    cache = tmp_path / "cache"
    (cache / "extract" / "s").mkdir(parents=True)
    (cache / "extract" / "s" / "a.json").write_text("{}", encoding="utf-8")

    rc = cli.main(["cache", "migrate", "--from", str(cache), "--cache", str(cache)])

    assert rc == 2
    assert "nothing to do" in capsys.readouterr().out


# T4.11-T4.13: post-run sweep, driven through _run_pipeline.

def test_run_sweeps_after_success(tmp_path, env, monkeypatch, caplog):
    args, paths, transcripts = _warm_run(tmp_path, monkeypatch)
    rel = _seed_stale(paths.cache_dir, transcripts[0].session_id)
    caplog.set_level(logging.INFO)

    assert cli._run_pipeline(args, NOW) == 0

    assert "cache gc (tag" in caplog.text
    assert rel in load_ledger(paths.cache_dir)


def test_partial_run_does_not_sweep(tmp_path, env, monkeypatch):
    args, paths, transcripts = _warm_run(tmp_path, monkeypatch, limit=1)
    _seed_stale(paths.cache_dir, transcripts[0].session_id)

    assert cli._run_pipeline(args, NOW) == 0

    assert not (paths.cache_dir / LEDGER_NAME).exists()


def test_sweep_error_does_not_fail_run(tmp_path, env, monkeypatch, caplog):
    args, _, _ = _warm_run(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "live_entries", boom)
    caplog.set_level(logging.WARNING)

    assert cli._run_pipeline(args, NOW) == 0
    assert "cache gc skipped: boom" in caplog.text


def test_run_sweep_passes_its_frozen_store(tmp_path, env, monkeypatch):
    args, _, _ = _warm_run(tmp_path, monkeypatch)
    calls: list[tuple[tuple, dict]] = []

    def spy(*a, **k):
        calls.append((a, k))
        return None  # unknown live set: the sweep stops here, nothing is deleted

    monkeypatch.setattr(cli, "live_entries", spy)

    assert cli._run_pipeline(args, NOW) == 0

    assert len(calls) == 1
    a, k = calls[0]
    frozen = a[3] if len(a) > 3 else k.get("frozen")
    assert isinstance(frozen, FrozenStore)


# T4.14-T4.15: check and parser.

def test_check_counts_nested_cache(tmp_path, env, capsys):
    tdir, _ = _tree(tmp_path)
    cache = tmp_path / "cache"
    (cache / "extract" / "s").mkdir(parents=True)
    (cache / "extract" / "s" / "k.json").write_text("{}", encoding="utf-8")
    (cache / "synth" / "c").mkdir(parents=True)
    (cache / "synth" / "c" / "k.json").write_text("{}", encoding="utf-8")

    cli.main(["check", "--transcripts", str(tdir), "--cache", str(cache)])

    out = capsys.readouterr().out
    assert "extract entries: 1" in out
    assert "synth entries:   1" in out


def test_cache_command_is_not_paid():
    # _legacy_cache_trap keys on command names in _CACHE_COMMANDS, and "cache" is not
    # in that set. `cache gc` is checked separately by is_gc, and `cache migrate` is
    # free, so the parser must accept both without a model call.
    gc = cli._build_parser().parse_args(["cache", "gc"])
    assert (gc.command, gc.cache_command) == ("cache", "gc")
    mig = cli._build_parser().parse_args(["cache", "migrate"])
    assert (mig.command, mig.cache_command) == ("cache", "migrate")
