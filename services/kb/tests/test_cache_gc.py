from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from pnp_okf.cache_gc import (
    LEDGER_NAME,
    latest_session_tag,
    load_ledger,
    sweep,
    write_ledger,
)

A, B, C, D = ("a" * 16, "b" * 16, "c" * 16, "d" * 16)


def _entry(cache: Path, rel: str) -> Path:
    path = cache / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def _ledger_path(cache: Path) -> Path:
    return cache / LEDGER_NAME


def test_live_entry_is_never_touched(tmp_path: Path) -> None:
    rel = f"extract/s1/{A}.json"
    path = _entry(tmp_path, rel)
    write_ledger(tmp_path, {rel: "s1"})

    sweep(tmp_path, live={rel}, tag="s9")

    assert path.exists()
    assert rel not in load_ledger(tmp_path)


def test_new_stale_entry_is_stamped_with_current_tag(tmp_path: Path) -> None:
    rel = f"synth/s1/{A}.json"
    path = _entry(tmp_path, rel)

    sweep(tmp_path, live=set(), tag="s5")

    assert load_ledger(tmp_path) == {rel: "s5"}
    assert path.exists()


def test_deleted_only_after_keep_tags(tmp_path: Path) -> None:
    rel = f"extract/s1/{A}.json"
    path = _entry(tmp_path, rel)
    sibling = f"extract/s1/{B}.json"
    _entry(tmp_path, sibling)  # live sibling: 1 of 2 due stays under the 50% guard
    write_ledger(tmp_path, {rel: "s5"})

    kept = sweep(tmp_path, live={sibling}, tag="s6")
    assert kept.waiting == 1
    assert path.exists()

    sweep(tmp_path, live={sibling}, tag="s7")
    assert not path.exists()
    assert rel not in load_ledger(tmp_path)


def test_keep_is_configurable(tmp_path: Path) -> None:
    rel = f"extract/s1/{A}.json"
    path = _entry(tmp_path, rel)
    sibling = f"extract/s1/{B}.json"
    _entry(tmp_path, sibling)  # live sibling: 1 of 2 due stays under the 50% guard
    write_ledger(tmp_path, {rel: "s5"})

    sweep(tmp_path, live={sibling}, tag="s6", keep=1)

    assert not path.exists()


def test_relive_entry_leaves_ledger(tmp_path: Path) -> None:
    rel = f"extract/s1/{A}.json"
    path = _entry(tmp_path, rel)
    write_ledger(tmp_path, {rel: "s5"})

    sweep(tmp_path, live={rel}, tag="s6")

    assert load_ledger(tmp_path) == {}
    assert path.exists()


def test_no_tag_never_deletes(tmp_path: Path) -> None:
    rel = f"extract/s1/{A}.json"
    path = _entry(tmp_path, rel)
    write_ledger(tmp_path, {rel: "s1"})

    sweep(tmp_path, live=set(), tag=None)

    assert path.exists()


def test_null_stamp_gets_first_tag(tmp_path: Path) -> None:
    rel = f"extract/s1/{A}.json"
    path = _entry(tmp_path, rel)
    write_ledger(tmp_path, {rel: None})

    sweep(tmp_path, live=set(), tag="s3")

    assert load_ledger(tmp_path) == {rel: "s3"}
    assert path.exists()


def test_foreign_files_never_touched(tmp_path: Path) -> None:
    foreign = [
        "state/s1/x.json",
        "extract/s1/notakey.json",
        "ledger_report.md",
        "extract/flat.json",
    ]
    paths = [_entry(tmp_path, rel) for rel in foreign]

    sweep(tmp_path, live=set(), tag="s1")
    sweep(tmp_path, live=set(), tag="s9")

    assert all(p.exists() for p in paths)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    rel = f"extract/s1/{A}.json"
    path = _entry(tmp_path, rel)
    sibling = f"extract/s1/{B}.json"
    _entry(tmp_path, sibling)  # live sibling: 1 of 2 due stays under the 50% guard
    write_ledger(tmp_path, {rel: "s1"})
    before = _ledger_path(tmp_path).read_bytes()

    report = sweep(tmp_path, live={sibling}, tag="s9", dry_run=True)

    assert path.exists()
    assert _ledger_path(tmp_path).read_bytes() == before
    assert report.deleted == [rel]


def test_empty_entity_dir_removed(tmp_path: Path) -> None:
    gone = _entry(tmp_path, f"synth/x/{A}.json")
    kept_sibling = _entry(tmp_path, f"synth/y/{B}.json")
    write_ledger(tmp_path, {
        f"synth/x/{A}.json": "s1",
        f"synth/y/{B}.json": "s1",
    })
    live = {f"synth/y/{B}.json"}

    sweep(tmp_path, live=live, tag="s9")

    assert not gone.exists()
    assert not (tmp_path / "synth" / "x").exists()
    assert kept_sibling.exists()
    assert (tmp_path / "synth" / "y").is_dir()


def test_mass_guard_blocks_per_kind(tmp_path: Path) -> None:
    rels = [f"extract/s1/{k}.json" for k in (A, B, C)]
    paths = [_entry(tmp_path, rel) for rel in rels]
    write_ledger(tmp_path, {rel: "s1" for rel in rels})
    live = {rels[2]}  # 2 of 3 extract entries are due

    report = sweep(tmp_path, live=live, tag="s9")

    assert all(p.exists() for p in paths)
    assert len(report.blocked) == 2
    # Blocked entries stay in the ledger so the next sweep can still age them.
    assert set(load_ledger(tmp_path)) == {rels[0], rels[1]}

    sweep(tmp_path, live=live, tag="s9", allow_mass=True)

    assert not paths[0].exists()
    assert not paths[1].exists()
    assert paths[2].exists()


def test_mass_guard_is_per_kind(tmp_path: Path) -> None:
    synth_rels = [f"synth/s1/{k}.json" for k in (A, B, C, D)]
    extract_rels = [f"extract/s1/{k}.json" for k in (A, B, C, D)]
    synth_paths = [_entry(tmp_path, rel) for rel in synth_rels]
    extract_paths = [_entry(tmp_path, rel) for rel in extract_rels]
    write_ledger(tmp_path, {rel: "s1" for rel in synth_rels + extract_rels})
    # 1 of 4 synth due (fine), 3 of 4 extract due (over 50%, blocked).
    live = {synth_rels[1], synth_rels[2], synth_rels[3], extract_rels[3]}

    report = sweep(tmp_path, live=live, tag="s9")

    assert not synth_paths[0].exists()
    assert all(p.exists() for p in synth_paths[1:])
    assert all(p.exists() for p in extract_paths)
    assert sorted(report.blocked) == sorted(extract_rels[:3])


def test_none_live_set_raises(tmp_path: Path) -> None:
    rel = f"extract/s1/{A}.json"
    path = _entry(tmp_path, rel)
    write_ledger(tmp_path, {rel: "s1"})

    with pytest.raises(ValueError):
        sweep(tmp_path, live=None, tag="s9")  # type: ignore[arg-type]

    assert path.exists()


def test_bad_ledger_schema_raises(tmp_path: Path) -> None:
    _ledger_path(tmp_path).write_text('{"schema": 2, "stale_since": {}}', encoding="utf-8")

    with pytest.raises(ValueError):
        sweep(tmp_path, live=set(), tag="s1")


def test_ledger_is_sorted_lf_and_stable(tmp_path: Path) -> None:
    for rel in (f"synth/s1/{B}.json", f"extract/s1/{A}.json"):
        _entry(tmp_path, rel)

    sweep(tmp_path, live=set(), tag="s1")
    first = _ledger_path(tmp_path).read_bytes()
    sweep(tmp_path, live=set(), tag="s1")
    second = _ledger_path(tmp_path).read_bytes()

    assert first == second
    assert b"\r" not in first
    assert first.index(b"extract/") < first.index(b"synth/")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_tag_ordering_is_numeric(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = dict(check=True, cwd=repo)
    subprocess.run(["git", "init", "-q"], **run)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], **run)
    subprocess.run(["git", "config", "user.name", "test"], **run)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], **run)
    for tag in ("s9", "s10", "s2", "v1"):
        subprocess.run(["git", "tag", tag], **run)

    assert latest_session_tag(repo) == "s10"

    nogit = tmp_path / "nogit"
    nogit.mkdir()
    # Stop git from walking up out of tmp_path and finding some parent repo.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert latest_session_tag(nogit) is None
