"""LLM identity adjudication invariants (audit v6) — no LLM, no Neo4j; the
adjudicator is a fake returning canned verdicts.

Run: python -m pytest tests/  (or python tests/test_adjudicate.py for the asserts).
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pnp_graph.adjudicate as adjudicate_mod
import pnp_graph.resolve as resolve_mod
from pnp_graph.adjudicate import MergeVerdict, MergeVerdicts, adjudicate_session
from pnp_graph.resolve import Resolver, resolve_graph
from pnp_graph.schema import Character, GraphExtraction


def _empty_resolver(seed: dict | None = None) -> Resolver:
    tmp = Path(tempfile.mkdtemp()) / "reg.json"
    tmp.write_text(json.dumps(seed or {}, ensure_ascii=False), encoding="utf-8")
    return Resolver(tmp)


def _tmp_state() -> Path:
    d = Path(tempfile.mkdtemp())
    adjudicate_mod.STATE_DIR = d
    resolve_mod.STATE_DIR = d
    return d


class _FakeAdjudicator:
    def __init__(self, verdicts, fail=False):
        self._verdicts = verdicts
        self._fail = fail
        self.prompts: list[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        if self._fail:
            raise ValueError("boom")
        return MergeVerdicts(verdicts=self._verdicts)


def test_gray_band_mint_queues_candidate():
    r = _empty_resolver()
    a = r.resolve("Breska", "Location")
    b = r.resolve("Breschka", "Location")  # 0.86 — below 0.9 auto-merge, in gray band
    assert a != b
    cands = r.drain_candidates()
    assert len(cands) == 1
    assert cands[0]["new_id"] == b and cands[0]["existing_id"] == a
    assert r.drain_candidates() == []  # drained


def test_merge_verdict_rewrites_registry_and_resolved():
    state = _tmp_state()
    r = _empty_resolver()
    a = r.resolve("Breska", "Location")
    b = r.resolve("Breschka", "Location")
    resolved = {
        "entities": [{"id": b, "type": "Location",
                      "props": {"name": "Breschka", "session_id": "2025-04-09",
                                "confidence": "medium", "evidence_chunks": [2]}}],
        "edges": [{"start_id": "EVT_Angriff", "end_id": b, "type": "AT_LOCATION",
                   "props": {"session_id": "2025-04-09", "confidence": "high"}}],
    }
    fake = _FakeAdjudicator([MergeVerdict(candidate_index=0, same_entity=True,
                                          reasoning="ASR-Variante desselben Dorfs")])
    remap = adjudicate_session(r, resolved, "2025-04-09", adjudicator=fake)

    assert remap == {b: a}
    # registry: provisional entry folded into the established one as alias
    assert b not in r.registry["locations"]
    assert "Breschka" in r.registry["locations"][a]["aliases"]
    # resolved dict: id + name remapped to the kept canonical, edge re-pointed
    assert resolved["entities"][0]["id"] == a
    assert resolved["entities"][0]["props"]["name"] == "Breska"
    assert resolved["edges"][0]["end_id"] == a
    # review trail written with the reasoning
    trail = (state / "review" / "2025-04-09" / "adjudications.jsonl").read_text(encoding="utf-8")
    assert "ASR-Variante" in trail
    # candidate context (both names) reached the LLM prompt
    assert "Breska" in fake.prompts[0] and "Breschka" in fake.prompts[0]


def test_distinct_verdict_memoized_never_reasked():
    _tmp_state()
    r = _empty_resolver()
    a = r.resolve("Breska", "Location")
    b = r.resolve("Breschka", "Location")
    resolved = {"entities": [], "edges": []}
    fake = _FakeAdjudicator([MergeVerdict(candidate_index=0, same_entity=False,
                                          reasoning="zwei verschiedene Orte")])
    remap = adjudicate_session(r, resolved, "2025-04-09", adjudicator=fake)
    assert remap == {}
    assert a in r.registry["locations"] and b in r.registry["locations"]  # both kept
    assert a in r.registry["locations"][b]["adjudicated_distinct"]
    # the pair never re-enters the queue
    assert r._gray_candidates("locations", b, "Breschka") == []


def test_alias_conflict_distinct_strips_alias():
    _tmp_state()
    # Timrell (the child) is known; the model wrongly folds it into Tindrail
    r = _empty_resolver({"characters": {
        "NPC_Timrell": {"canonical": "Timrell", "aliases": []}}})
    cast_info = {"players": {}, "characters": {}, "plays": {}}
    extraction = GraphExtraction(characters=[
        Character(name="Tindrail", role="NPC", is_named_character=True,
                  aliases=["Timrell"])])
    resolved = resolve_graph(r, extraction, "2025-04-09", cast_info, seq=1)
    cands = [c for c in r.drain_candidates() if c.get("source") == "alias-conflict"]
    assert cands and cands[0]["surface"] == "Timrell"
    r.pending_candidates = cands  # adjudicate exactly this candidate
    fake = _FakeAdjudicator([MergeVerdict(candidate_index=0, same_entity=False,
                                          reasoning="Grabwächter vs fliehendes Kind")])
    adjudicate_session(r, resolved, "2025-04-09", adjudicator=fake)
    tindrail = next(e for e in resolved["entities"] if e["id"].startswith("NPC_Tindrail"))
    assert "Timrell" not in tindrail["props"].get("aliases", [])  # wrong merge undone
    assert "NPC_Timrell" in r.registry["characters"]              # child survives


def test_adjudication_failure_leaves_everything_unmerged():
    _tmp_state()
    r = _empty_resolver()
    a = r.resolve("Breska", "Location")
    b = r.resolve("Breschka", "Location")
    resolved = {"entities": [], "edges": []}
    fake = _FakeAdjudicator([], fail=True)
    remap = adjudicate_session(r, resolved, "2025-04-09", adjudicator=fake)
    assert remap == {}
    assert a in r.registry["locations"] and b in r.registry["locations"]


def test_no_candidates_no_llm_call():
    _tmp_state()
    r = _empty_resolver()
    fake = _FakeAdjudicator([])
    assert adjudicate_session(r, {"entities": [], "edges": []}, "s", adjudicator=fake) == {}
    assert fake.prompts == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all adjudicate invariants pass")
