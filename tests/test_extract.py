"""Invariants for the two-pass extraction wiring (docs/evolution/06, WP7;
capsule + scene segmentation, WP13). No LLM, no Neo4j — extractors are fakes
that record what prompt they saw.

Run: python -m pytest tests/  (or python tests/test_extract.py for the asserts).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pnp_graph.extract import extract_chunk, segment_session
from pnp_graph.schema import (Character, EntityExtraction, Event, EventExtraction,
                              GraphExtraction, Location, Relationship, RuleEntity,
                              SceneBoundary, SceneSegmentation)


def _event(title, **kw):
    # narrative_significance_reasoning is required (pay-to-mint, WP13.2)
    kw.setdefault("narrative_significance_reasoning", "state changed")
    return Event(title=title, **kw)


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


def test_extract_chunk_combines_both_passes_and_capsule_event():
    entities = EntityExtraction(
        characters=[Character(name="Lindo Laut", role="PC")],
        locations=[Location(name="Wald")],
        rule_entities=[RuleEntity(name="Barde", subtype="Class")],
    )
    events = EventExtraction(
        macro_scene_event=_event("Kampf gegen die Goblins", participants=["Lindo Laut"]),
        relationships=[Relationship(subject="Lindo Laut", predicate="HAS_CLASS",
                                    object="Barde", confidence="high")],
    )
    entity_extractor = _FakeExtractor([entities])
    event_extractor = _FakeExtractor([events])

    result = extract_chunk((entity_extractor, event_extractor), "chunk text", 3,
                           cast_names=["Lindo Laut"], rule_names=["Barde"])

    assert result.characters == entities.characters
    assert result.locations == entities.locations
    # capsule: exactly one macro event per scene chunk
    assert [e.title for e in result.events] == ["Kampf gegen die Goblins"]
    assert result.relationships == events.relationships
    assert result.relationships[0].evidence == 3  # stamped, not model-supplied

    assert "Lindo Laut" in entity_extractor.prompts[0]
    assert "Barde" in entity_extractor.prompts[0]
    event_prompt = event_extractor.prompts[0]
    assert "Lindo Laut" in event_prompt and "Wald" in event_prompt and "Barde" in event_prompt


def test_extract_chunk_retries_once_per_pass():
    entities = EntityExtraction(characters=[Character(name="Dodo", role="PC")])
    events = EventExtraction(macro_scene_event=_event("Szene"))
    entity_extractor = _FakeExtractor([entities], fail_first=True)
    event_extractor = _FakeExtractor([events], fail_first=True)

    result = extract_chunk((entity_extractor, event_extractor), "chunk text", 1)

    assert result.characters == entities.characters
    assert len(entity_extractor.prompts) == 2  # first raised, retry succeeded
    assert len(event_extractor.prompts) == 2


def test_segment_session_returns_llm_boundaries():
    segments = [{"speaker": "GM", "text": f"line {i}"} for i in range(6)]
    seg = SceneSegmentation(scenes=[
        SceneBoundary(start_segment=0, end_segment=2, title="A"),
        SceneBoundary(start_segment=3, end_segment=5, title="B"),
    ])
    fake = _FakeExtractor([seg])
    scenes = segment_session(fake, segments)
    assert [(s.start_segment, s.end_segment) for s in scenes] == [(0, 2), (3, 5)]
    assert "0: GM: line 0" in fake.prompts[0]  # line-numbered listing fed to the model


def test_segment_session_falls_back_to_one_scene_on_failure():
    segments = [{"speaker": "GM", "text": "x"}, {"speaker": "GM", "text": "y"}]
    fake = _FakeExtractor([], fail_first=True)  # raises, no canned result
    scenes = segment_session(fake, segments)
    assert len(scenes) == 1
    assert scenes[0].start_segment == 0 and scenes[0].end_segment == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all extract invariants pass")
