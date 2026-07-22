"""Invariants for the pure prompt-building helper in summarize.py
(docs/evolution/13, WP13.4). No LLM, no Neo4j — summarize_entities() itself
talks to both and is verified live, same precedent as embed.py/retrieve.py.

Run: python -m pytest tests/  (or python tests/test_summarize.py for the asserts).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pnp_graph.summarize import _build_prompt


def test_build_prompt_includes_existing_summary_and_notes():
    prompt = _build_prompt("Spielt oft Musik.", ["misstraut Fremden"])
    assert "Bisherige Zusammenfassung: Spielt oft Musik." in prompt
    assert "- misstraut Fremden" in prompt


def test_build_prompt_omits_existing_summary_when_none():
    prompt = _build_prompt(None, ["singt gern"])
    assert "Bisherige Zusammenfassung" not in prompt
    assert "- singt gern" in prompt


def test_build_prompt_lists_every_note():
    prompt = _build_prompt(None, ["a", "b", "c"])
    assert "- a" in prompt and "- b" in prompt and "- c" in prompt


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all summarize invariants pass")
