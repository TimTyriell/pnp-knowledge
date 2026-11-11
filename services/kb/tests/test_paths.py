"""Path resolution must never silently relocate the knowledge root.

Every knowledge path — the registry, entity_rules.yaml, sources/, conflicts/ —
is derived from the bundle directory (config.py::_knowledge_root). So one
wrong --bundle, or a stale PNP_BUNDLE_DIR, moves all of them together, and
nothing downstream can tell that apart from a legitimate first run: a missing
registry reads as an empty one and a missing rules file reads as no rules at
all. The run then regenerates the whole campaign from scratch, reports
success, and the rename/prune guards stay quiet because they diff against the
same empty registry.

That happened on 2026-08-30 (a `pnp run` from services/kb with the shipped
./bundle/... default) and cost a full run plus 32 unintended LLM calls. These
tests hold the two properties that would have stopped it: the default resolves
to the repo's own bundle, and resolving identities against a rules-less
registry raises instead of proceeding.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pnp_okf.config import Paths
from pnp_okf.resolve import require_rules


@pytest.fixture(autouse=True)
def clear_path_overrides(monkeypatch):
    for name in ("PNP_TRANSCRIPT_DIR", "PNP_BUNDLE_DIR", "PNP_KNOWLEDGE_DIR", "PNP_CACHE_DIR"):
        monkeypatch.delenv(name, raising=False)


def _knowledge(root: Path) -> Path:
    """A minimal repo-shaped knowledge/ tree under ``root``."""

    k = root / "knowledge"
    (k / "bundle" / "splitter_des_ewigen").mkdir(parents=True)
    (k / "entity_registry.yaml").write_text("entities: []\n", encoding="utf-8")
    return k


# --- require_rules ---------------------------------------------------------


def test_require_rules_raises_when_the_rules_file_is_missing(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text("entities: []\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError) as exc:
        require_rules(registry)

    # The message has to name the path it actually looked at — that is the
    # whole diagnostic, since the failure mode is "right filename, wrong root".
    assert "entity_rules.yaml" in str(exc.value)
    assert str(tmp_path / "entity_rules.yaml") in str(exc.value)


def test_require_rules_passes_when_the_rules_file_is_there(tmp_path: Path):
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text("entities: []\n", encoding="utf-8")
    (tmp_path / "entity_rules.yaml").write_text("merge: {}\n", encoding="utf-8")

    require_rules(registry)  # must not raise


# --- default bundle resolution ---------------------------------------------


def test_default_bundle_is_the_repos_own_from_a_nested_cwd(tmp_path: Path, monkeypatch):
    # The documented workflow is `cd services/kb && pnp run`, two levels below
    # the bundle — the exact case the old ./bundle/... default got wrong.
    _knowledge(tmp_path)
    nested = tmp_path / "services" / "kb"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv("PNP_BUNDLE_DIR", raising=False)

    paths = Paths.resolve()

    assert paths.bundle_dir == tmp_path / "knowledge" / "bundle" / "splitter_des_ewigen"
    assert paths.registry_path == tmp_path / "knowledge" / "entity_registry.yaml"
    assert paths.sources_dir == tmp_path / "knowledge" / "sources"


def test_an_explicit_bundle_still_wins(tmp_path: Path, monkeypatch):
    _knowledge(tmp_path)
    monkeypatch.chdir(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "bundle" / "x"

    paths = Paths.resolve(bundle_dir=elsewhere)

    assert paths.bundle_dir == elsewhere


def test_knowledge_dir_is_shared_root_below_bundle_overrides(tmp_path: Path, monkeypatch):
    shared = tmp_path / "shared-knowledge"
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    monkeypatch.setenv("PNP_KNOWLEDGE_DIR", str(shared))
    monkeypatch.setenv("PNP_BUNDLE_DIR", str(tmp_path / "bundle-override"))
    # Bundle-specific configuration has priority over the shared root.
    assert Paths.resolve().bundle_dir == tmp_path / "bundle-override"
    monkeypatch.delenv("PNP_BUNDLE_DIR")
    assert Paths.resolve().bundle_dir == shared / "bundle" / "splitter_des_ewigen"
    explicit = tmp_path / "argument-bundle"
    assert Paths.resolve(bundle_dir=explicit).bundle_dir == explicit


# --- default cache dir ----------------------------------------------------


def test_default_cache_is_knowledge_cache(tmp_path: Path, monkeypatch):
    k = _knowledge(tmp_path)
    monkeypatch.delenv("PNP_CACHE_DIR", raising=False)

    paths = Paths.resolve(bundle_dir=k / "bundle" / "splitter_des_ewigen")

    assert paths.cache_dir == k / "cache"


def test_env_cache_beats_default(tmp_path: Path, monkeypatch):
    k = _knowledge(tmp_path)
    monkeypatch.setenv("PNP_CACHE_DIR", str(tmp_path / "env-cache"))

    paths = Paths.resolve(bundle_dir=k / "bundle" / "splitter_des_ewigen")

    assert paths.cache_dir == tmp_path / "env-cache"


def test_explicit_cache_beats_env(tmp_path: Path, monkeypatch):
    k = _knowledge(tmp_path)
    monkeypatch.setenv("PNP_CACHE_DIR", str(tmp_path / "env-cache"))

    paths = Paths.resolve(
        bundle_dir=k / "bundle" / "splitter_des_ewigen",
        cache_dir=tmp_path / "arg-cache",
    )

    assert paths.cache_dir == tmp_path / "arg-cache"


def test_no_registry_falls_back_to_dot_cache(tmp_path: Path, monkeypatch):
    # A bundle with no entity_registry.yaml beside it is not a campaign
    # checkout, so the cache stays where it always was (cwd-relative).
    monkeypatch.delenv("PNP_CACHE_DIR", raising=False)
    bundle = tmp_path / "bundle" / "x"
    bundle.mkdir(parents=True)

    paths = Paths.resolve(bundle_dir=bundle)

    assert paths.cache_dir == Path("./.cache")


def test_legacy_cache_dir_points_at_services_kb():
    from pnp_okf.config import LEGACY_CACHE_DIR

    assert LEGACY_CACHE_DIR.name == ".cache"
    assert LEGACY_CACHE_DIR.parent.name == "kb"
    assert LEGACY_CACHE_DIR.parent.parent.name == "services"


# --- transcript dir -------------------------------------------------------


def test_default_transcript_dir_env_wins(monkeypatch, tmp_path):
    from pnp_okf.config import default_transcript_dir

    monkeypatch.setenv("PNP_TRANSCRIPT_DIR", str(tmp_path))
    assert default_transcript_dir() == tmp_path


def test_transcript_override_wins_in_standalone_platform(monkeypatch, tmp_path):
    import pnp_okf.config as config

    repo = tmp_path / "platform"
    (repo / "services" / "kb").mkdir(parents=True)
    monkeypatch.setattr(config, "__file__", str(repo / "services/kb/src/pnp_okf/config.py"))
    override = tmp_path / "external" / "transcripts"
    monkeypatch.setenv("PNP_TRANSCRIPT_DIR", str(override))
    assert config.default_transcript_dir() == override


def test_no_machine_specific_paths_in_scripts():
    # The scripts used to hardcode a checkout path that exists on no machine
    # that runs them; this grep is the regression guard. The prefix is split
    # so this file does not match its own search.
    kb = Path(__file__).resolve().parents[1]
    needle = "C:/dev/" "pnp/"
    offenders = [
        p.name for p in kb.glob("*.py")
        if needle in p.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders


if __name__ == "__main__":
    import sys
    import tempfile

    failures = 0
    for name, fn in list(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        args = fn.__code__.co_varnames[: fn.__code__.co_argcount]
        if "monkeypatch" in args:
            continue  # pytest-only fixture
        try:
            with tempfile.TemporaryDirectory() as d:
                fn(*[Path(d)][: len(args)])
            print(f"ok    {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
    sys.exit(1 if failures else 0)
