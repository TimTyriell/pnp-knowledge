"""Invariants for the pure formatting helpers in embed.py/retrieve.py
(docs/evolution/11, WP11). No LLM, no Neo4j — the DB-touching parts
(_top_k_entities, _expand, embed_entities) were verified live against a
real Neo4j + Ollama instead; see the WP11 implementation notes.

Run: python -m pytest tests/  (or python tests/test_retrieve.py for the asserts).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pnp_graph.embed import _entity_text
from pnp_graph.retrieve import _format_context


def test_entity_text_includes_traits_and_description():
    row = {"type": "Character", "name": "Lindo Laut", "aliases": ["Lindo"],
           "description": None, "summary": None}
    text = _entity_text(row, trait_names=["Spielt oft Musik"])
    assert text == "Character | Lindo Laut | Lindo | Spielt oft Musik"


def test_entity_text_skips_empty_fields():
    row = {"type": "Location", "name": "Wald", "aliases": [], "description": "", "summary": None}
    assert _entity_text(row, trait_names=[]) == "Location | Wald"


def test_format_context_renders_status_and_fact_bits():
    ctx = {
        "nodes": [{"id": "CHAR_Dodo", "type": "Character", "name": "Dodo", "status": "deceased"}],
        "edges": [{"a_name": "Lindo Laut", "rel": "TRUSTS", "b_name": "Dodo",
                   "session_id": "2025-03-26", "confidence": "high", "count": None,
                   "description": "beste Freunde"}],
    }
    text = _format_context(ctx)
    assert "CHAR_Dodo (Character): Dodo, status=deceased" in text
    assert "Lindo Laut -TRUSTS-> Dodo [session=2025-03-26, confidence=high, \"beste Freunde\"]" in text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all retrieve invariants pass")
