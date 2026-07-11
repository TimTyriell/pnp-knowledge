"""Invariants for the two-pass extraction wiring (docs/evolution/06, WP7).
No LLM, no Neo4j — extractors are fakes that record what prompt they saw.

Run: python -m pytest tests/  (or python tests/test_extract.py for the asserts).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pnp_graph.extract import apply_event_consolidation, extract_chunk, propose_event_groups
from pnp_graph.schema import (Character, EntityExtraction, Event, EventConsolidation, EventExtraction,
                              EventGroup, GraphExtraction, Location, Relationship, RuleEntity)


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

    result = extract_chunk((entity_extractor, event_extractor, None), "chunk text", 3,
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

    result = extract_chunk((entity_extractor, event_extractor, None), "chunk text", 1)

    assert result.characters == entities.characters
    assert len(entity_extractor.prompts) == 2  # first raised, retry succeeded
    assert len(event_extractor.prompts) == 2


def test_propose_event_groups_skips_llm_under_two_events():
    extractor = _FakeExtractor([EventConsolidation(groups=[])])
    graph = GraphExtraction(events=[Event(title="Only One")])
    result = propose_event_groups(extractor, graph)
    assert result.groups == []
    assert extractor.prompts == []  # never called — nothing to consolidate


def test_apply_event_consolidation_merges_near_duplicates():
    graph = GraphExtraction(
        events=[
            Event(title="Monster's Last Breath", summary="a", participants=["Dodo"]),
            Event(title="Monster's Final Breath", summary="b", participants=["Cookie"], location="Wald"),
            Event(title="Dodo moves the Pott", summary="unrelated", participants=["Dodo"]),
        ],
        relationships=[
            Relationship(subject="Dodo", predicate="PARTICIPATED_IN",
                        object="Monster's Last Breath", confidence="high"),
            Relationship(subject="Cookie", predicate="PARTICIPATED_IN",
                        object="Monster's Final Breath", confidence="high"),
        ],
    )
    evidence = {
        ("events", "Monster's Last Breath"): [3],
        ("events", "Monster's Final Breath"): [4],
        ("relationships", ("Dodo", "PARTICIPATED_IN", "Monster's Last Breath")): [3],
        ("relationships", ("Cookie", "PARTICIPATED_IN", "Monster's Final Breath")): [4],
    }
    consolidation = EventConsolidation(groups=[
        EventGroup(canonical_title="Monster Dies", summary="the monster dies",
                  member_titles=["Monster's Last Breath", "Monster's Final Breath"]),
        EventGroup(canonical_title="Dodo moves the Pott", summary="unrelated",
                  member_titles=["Dodo moves the Pott"]),
    ])
    apply_event_consolidation(graph, evidence, consolidation)

    titles = {e.title for e in graph.events}
    assert titles == {"Monster Dies", "Dodo moves the Pott"}
    merged = next(e for e in graph.events if e.title == "Monster Dies")
    assert set(merged.participants) == {"Dodo", "Cookie"}
    assert merged.location == "Wald"  # pulled from a member that had one

    rel_objects = {r.object for r in graph.relationships}
    assert rel_objects == {"Monster Dies"}  # both rewritten, no duplicate

    assert evidence[("events", "Monster Dies")] == [3, 4]
    assert ("relationships", ("Dodo", "PARTICIPATED_IN", "Monster Dies")) in evidence
    assert ("relationships", ("Cookie", "PARTICIPATED_IN", "Monster Dies")) in evidence


def test_apply_event_consolidation_safety_net_keeps_uncovered_titles():
    # if the model drops a title from every group (schema drift), it survives
    # as its own singleton rather than vanishing from the graph.
    graph = GraphExtraction(events=[
        Event(title="A", summary=""), Event(title="B", summary=""), Event(title="C", summary=""),
    ])
    consolidation = EventConsolidation(groups=[
        EventGroup(canonical_title="A", summary="", member_titles=["A"]),
    ])
    apply_event_consolidation(graph, {}, consolidation)
    assert {e.title for e in graph.events} == {"A", "B", "C"}


def test_apply_event_consolidation_noop_on_empty_groups():
    graph = GraphExtraction(events=[Event(title="A"), Event(title="B")])
    apply_event_consolidation(graph, {}, EventConsolidation(groups=[]))
    assert {e.title for e in graph.events} == {"A", "B"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all extract invariants pass")
