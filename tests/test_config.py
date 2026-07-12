"""PNP_PROFILE resolution self-check (no LLM, no Neo4j).

config.py resolves LLM_MODEL/CHUNK_SIZE/CHUNK_OVERLAP/PROVIDER from the
PNP_PROFILE env var at import time — reload under a patched env to prove both
profiles resolve, then restore the default so later tests see the local one.

Run: python -m pytest tests/  (or python tests/test_config.py for the asserts).
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pnp_graph.config as cfg


def _reload(monkeypatch, profile: str | None):
    if profile is None:
        monkeypatch.delenv("PNP_PROFILE", raising=False)
    else:
        monkeypatch.setenv("PNP_PROFILE", profile)
    importlib.reload(cfg)


def test_flagship_profile_resolves(monkeypatch):
    try:
        _reload(monkeypatch, "flagship")
        assert cfg.PROVIDER == "deepseek"
        # default flagship model (env-overridable via DEEPSEEK_MODEL)
        monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
        importlib.reload(cfg)
        assert cfg.LLM_MODEL == "deepseek-v4-flash"
        assert cfg.CHUNK_SIZE == 44000
    finally:
        _reload(monkeypatch, None)  # restore default so other tests see 'local'


def test_default_profile_is_local(monkeypatch):
    _reload(monkeypatch, None)
    assert cfg.PROVIDER == "ollama"
    assert cfg.LLM_MODEL == "qwen3:14b"
    assert cfg.CHUNK_SIZE == 4000


def test_unknown_profile_raises(monkeypatch):
    try:
        try:
            _reload(monkeypatch, "gpt5")
            assert False, "expected ValueError for unknown profile"
        except ValueError:
            pass
    finally:
        _reload(monkeypatch, None)


if __name__ == "__main__":
    class _MP:  # tiny stand-in so the file runs without pytest
        import os
        def setenv(self, k, v): self.os.environ[k] = v
        def delenv(self, k, raising=True): self.os.environ.pop(k, None)
    mp = _MP()
    test_flagship_profile_resolves(mp)
    test_default_profile_is_local(mp)
    test_unknown_profile_raises(mp)
    print("ok  config profile resolution")
