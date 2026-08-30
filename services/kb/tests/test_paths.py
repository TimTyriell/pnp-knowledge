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

import os
from pathlib import Path

import pytest

from pnp_okf.config import Paths
from pnp_okf.resolve import require_rules


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
                fn(Path(d))
            print(f"ok    {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
    sys.exit(1 if failures else 0)
