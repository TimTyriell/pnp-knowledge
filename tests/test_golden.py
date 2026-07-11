"""Golden-file regression (docs/evolution/08, WP10): a fixed synthetic
transcript + a canned LLM extraction, run through the real deterministic
layers (chunking -> cast -> resolve), compared against tests/golden_resolved.json.

Fails on schema drift, duplicate creation, off-vocab predicates leaking
through, or missing provenance — no LLM, no Neo4j.

Regenerate the golden after an INTENTIONAL change:
    python tests/test_golden.py --update
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pnp_graph.resolve as resolve_mod
from pnp_graph.chunking import session_cast
from pnp_graph.resolve import Resolver, resolve_graph
from pnp_graph.schema import (Character, Decision, Event, GraphExtraction, Item,
                              Quest, Relationship, RollEvent, RuleEntity)
from pnp_graph.srd import SrdIndex

GOLDEN = Path(__file__).parent / "golden_resolved.json"

_SEGMENTS = [
    {"start": 0, "end": 5, "speaker": "Deniz (GM)", "text": "Ihr steht vor dem Wald."},
    {"start": 6, "end": 10, "speaker": "Tim (Lindo Laut)", "text": "Ich singe ein Lied."},
    {"start": 11, "end": 15, "speaker": "Marco (Dodo)", "text": "Ich greife das Monster an!"},
    {"start": 16, "end": 20, "speaker": "Celin (Cookie)", "text": "Ich schieße mit dem Bogen."},
]

_EXTRACTION = GraphExtraction(
    characters=[
        Character(name="Lindo Laut", type="PC"),
        Character(name="der Schleichfurz", type="NPC"),
        Character(name="Schleichfurz ", type="NPC"),  # variant — must collapse
    ],
    items=[Item(name="Bogen", owner="Cookie", status="used")],
    quests=[Quest(name="Monsterjagd", status="open")],
    events=[Event(title="Monster greift an", summary="", participants=["Dodo", "Lindo"],
                  location=None)],
    rule_entities=[RuleEntity(name="Barde", subtype="Class")],
    roll_events=[RollEvent(name="Dodo Angriffswurf", roller="Dodo", trait_or_action="attack",
                           outcome="success_with_fear", target="der Schleichfurz",
                           confidence="high")],
    decisions=[Decision(name="Monster provozieren", decided_by="Lindo Laut",
                        quote="ich singe", consequence="Monster greift an",
                        confidence="medium")],
    relationships=[
        Relationship(subject="Lindo Laut", predicate="HAS_CLASS", object="Barde",
                     confidence="high"),
        Relationship(subject="Monster provozieren", predicate="TRIGGERED",
                     object="Monster greift an", confidence="high"),
        Relationship(subject="Dodo", predicate="BEST_BUDDY", object="Cookie",  # off-vocab
                     confidence="low"),
        Relationship(subject="Unbekannt", predicate="KNOWS", object="Dodo",  # dropped
                     confidence="low"),
    ],
)

_EVIDENCE = {
    ("characters", "Lindo Laut"): [1],
    ("characters", "der Schleichfurz"): [1, 2],
    ("characters", "Schleichfurz "): [2],
    ("items", "Bogen"): [2],
    ("quests", "Monsterjagd"): [1],
    ("events", "Monster greift an"): [2],
    ("rule_entities", "Barde"): [1],
    ("roll_events", "Dodo Angriffswurf"): [2],
    ("decisions", "Monster provozieren"): [1],
    ("relationships", ("Lindo Laut", "HAS_CLASS", "Barde")): [1],
    ("relationships", ("Monster provozieren", "TRIGGERED", "Monster greift an")): [2],
    ("relationships", ("Dodo", "BEST_BUDDY", "Cookie")): [2],
}


def _run_pipeline() -> dict:
    resolve_mod.STATE_DIR = Path(tempfile.mkdtemp())
    seed = Path(__file__).resolve().parents[1] / "data" / "alias_registry.json"
    tmp = Path(tempfile.mkdtemp()) / "alias_registry.json"
    tmp.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")
    resolver = Resolver(tmp)
    cast_info = resolver.bootstrap_cast(session_cast(_SEGMENTS))
    resolved = resolve_graph(resolver, _EXTRACTION, "2025-03-26", cast_info, seq=1,
                             evidence=_EVIDENCE, srd_index=SrdIndex())
    # stable ordering for comparison; drop volatile bits (none currently)
    return {
        "entities": sorted(resolved["entities"], key=lambda e: e["id"]),
        "edges": sorted(resolved["edges"],
                        key=lambda e: (e["start_id"], e["type"], e["end_id"])),
        "dropped": resolved["dropped"],
    }


def test_golden():
    actual = json.loads(json.dumps(_run_pipeline()))  # normalize tuples etc.
    assert GOLDEN.exists(), f"golden file missing — run: python {__file__} --update"
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert actual == expected, (
        "resolved output drifted from golden. If intentional, regenerate with "
        f"python {__file__} --update")


if __name__ == "__main__":
    if "--update" in sys.argv:
        GOLDEN.write_text(json.dumps(_run_pipeline(), ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"golden written: {GOLDEN}")
    else:
        test_golden()
        print("ok  test_golden")
