"""Invariants for the two-pass extraction wiring (docs/evolution/06, WP7).
No LLM, no Neo4j — extractors are fakes that record what prompt they saw.

Run: python -m pytest tests/  (or python tests/test_extract.py for the asserts).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pnp_graph.extract import extract_chunk
from pnp_graph.schema import (Character, EntityExtraction, EventExtraction, Location,
                              Relationship, RuleEntity)


class _FakeExtractor:
    """Stands in for a langchain structured-output runnable: records every
    prompt it was invoked with, returns canned results in order, and can be
    told to raise once (to exercise the retry path)."""

    def __init__(self, results, fail_first=False):
        self._results = list(results)
        self._fail_first = fail_first
        self.prompts: list[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        if self._fail_first:
            self._fail_first = False
            raise ValueError("boom")
        return self._results.pop(0)


def test_extract_chunk_combines_both_passes():
    entities = EntityExtraction(
        characters=[Character(name="Lindo Laut", type="PC")],
        locations=[Location(name="Wald")],
        rule_entities=[RuleEntity(name="Barde", subtype="Class")],
    )
    events = EventExtraction(
        relationships=[Relationship(subject="Lindo Laut", predicate="HAS_CLASS",
                                    object="Barde", confidence="high")],
    )
    entity_extractor = _FakeExtractor([entities])
    event_extractor = _FakeExtractor([events])

    result = extract_chunk((entity_extractor, event_extractor), "chunk text", 3,
                           cast_names=["Lindo Laut"], rule_names=["Barde"])

    assert result.characters == entities.characters
    assert result.locations == entities.locations
    assert result.relationships == events.relationships
    assert result.relationships[0].evidence == 3  # stamped, not model-supplied

    # entity pass got the cast/gazetteer lines; event pass got the entity
    # pass's own extracted names, not a free-form invitation to invent new ones
    assert "Lindo Laut" in entity_extractor.prompts[0]
    assert "Barde" in entity_extractor.prompts[0]
    event_prompt = event_extractor.prompts[0]
    assert "Lindo Laut" in event_prompt and "Wald" in event_prompt and "Barde" in event_prompt


def test_extract_chunk_retries_once_per_pass():
    entities = EntityExtraction(characters=[Character(name="Dodo", type="PC")])
    events = EventExtraction()
    entity_extractor = _FakeExtractor([entities], fail_first=True)
    event_extractor = _FakeExtractor([events], fail_first=True)

    result = extract_chunk((entity_extractor, event_extractor), "chunk text", 1)

    assert result.characters == entities.characters
    assert len(entity_extractor.prompts) == 2  # first raised, retry succeeded
    assert len(event_extractor.prompts) == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all extract invariants pass")
