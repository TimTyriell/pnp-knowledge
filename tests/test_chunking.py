"""Invariants for pack_segments: no segment split, size respected, overlap bounded.

Run: python -m pytest tests/  (or python tests/test_chunking.py for the asserts).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pnp_graph import config
from pnp_graph.chunking import (
    format_turn, heuristic_segment, pack_segments, scene_chunks, session_id_from_path,
    split_passages,
)
from pnp_graph.schema import SceneBoundary


def _segments(n: int, text_len: int = 200, gap_every: int = 5):
    """n synthetic segments, each ~text_len chars, with a big silence gap every gap_every."""
    segs = []
    t = 0.0
    for i in range(n):
        dur = 10.0
        segs.append({"start": t, "end": t + dur, "speaker": f"S{i%3}", "text": "x" * text_len})
        # big gap periodically, tiny gap otherwise
        t = t + dur + (30.0 if (i + 1) % gap_every == 0 else 1.0)
    return segs


def test_format_turn_has_no_inline_timestamp():
    # audit_v7pro §8 #3: no [MM:SS] prefix in the LLM-facing turn text.
    seg = {"start": 754, "end": 760, "speaker": "Tim (Lindo Laut)", "text": "Hallo."}
    out = format_turn(seg)
    assert not re.search(r"\[\d\d:\d\d\]", out)
    assert out.startswith("Lindo Laut:")


def test_no_segment_is_split():
    segs = _segments(40)
    turns = {format_turn(s).strip() for s in segs}
    chunks = pack_segments(segs)
    # every turn's body must appear intact inside some chunk
    joined = "\n".join(chunks)
    for s in segs:
        assert s["text"] in joined


def test_chunks_cover_all_segments():
    segs = _segments(40)
    chunks = pack_segments(segs)
    # each speaker-turn header appears at least once
    for i, s in enumerate(segs):
        assert format_turn(s).strip() in "\n".join(chunks)
    assert len(chunks) >= 1


def test_size_budget_mostly_respected():
    segs = _segments(40, text_len=200)
    for c in pack_segments(segs):
        # a single oversized segment can exceed the budget, but our segments are small;
        # allow CHUNK_OVERLAP slack on top of CHUNK_SIZE
        assert len(c) <= config.CHUNK_SIZE + config.CHUNK_OVERLAP + 400


def test_empty():
    assert pack_segments([]) == []


def test_single_segment():
    segs = _segments(1)
    chunks = pack_segments(segs)
    assert len(chunks) == 1
    assert segs[0]["text"] in chunks[0]


def test_no_cascading_small_chunks_around_early_gap():
    # regression: a lone bigger-than-neighbors gap early in a long, fast-back-
    # and-forth run of short turns must not get re-selected as the break point
    # chunk after chunk (window-relative halfway let this cascade to a dozen
    # sub-500-char chunks before the fix; size-relative halfway must not).
    segs = []
    t = 0.0
    for i in range(80):
        dur = 1.0
        segs.append({"start": t, "end": t + dur, "speaker": f"S{i%3}", "text": "x" * 40})
        gap = 5.0 if i == 10 else 0.2  # one standout gap early, otherwise near-continuous
        t += dur + gap
    chunks = pack_segments(segs)
    small = [c for c in chunks if len(c) < config.CHUNK_SIZE // 2]
    assert len(small) <= 1  # at most the unavoidable final leftover chunk


def _distinct_segments(n: int):
    return [{"start": float(i), "end": i + 0.5, "speaker": "GM", "text": f"seg{i}"}
            for i in range(n)]


def test_scene_chunks_one_per_boundary():
    segs = _distinct_segments(9)
    boundaries = [
        SceneBoundary(start_segment=0, end_segment=2, label="A"),
        SceneBoundary(start_segment=3, end_segment=8, label="B"),
    ]
    chunks = scene_chunks(segs, boundaries)
    assert len(chunks) == 2
    assert "seg0" in chunks[0] and "seg2" in chunks[0]
    assert "seg3" in chunks[1] and "seg8" in chunks[1]
    assert "seg8" not in chunks[0] and "seg3" not in chunks[0]  # no leak across scenes


def test_heuristic_segment_covers_all_contiguously():
    # audit_v7pro §8 #2: deterministic scene boundaries cover every segment
    # exactly once, in order, with no gaps or overlaps, each within budget.
    segs = _segments(40, text_len=2000)  # ~80k chars total -> several scenes
    bounds = heuristic_segment(segs)
    assert bounds[0].start_segment == 0
    assert bounds[-1].end_segment == len(segs) - 1
    for prev, nxt in zip(bounds, bounds[1:]):
        assert nxt.start_segment == prev.end_segment + 1  # contiguous, no gap/overlap
    # each scene fits the char budget
    for b in bounds:
        size = sum(len(format_turn(s)) for s in segs[b.start_segment:b.end_segment + 1])
        assert size <= config.CHUNK_SIZE or b.start_segment == b.end_segment


def test_scene_chunks_clamps_out_of_range_and_falls_back():
    segs = _distinct_segments(4)
    # garbage boundary indices are clamped, not crashed -> last segment only
    chunks = scene_chunks(segs, [SceneBoundary(start_segment=99, end_segment=200)])
    assert len(chunks) == 1 and "seg3" in chunks[0] and "seg0" not in chunks[0]
    # no usable boundary -> one chunk of everything
    assert len(scene_chunks(segs, [])) == 1


def test_split_passages_covers_all_turns_within_budget():
    segs = _segments(30, text_len=100)
    scene_text = "".join(format_turn(s) for s in segs)
    passages = split_passages(scene_text, size=500, overlap=100)
    assert len(passages) > 1  # a 30-turn scene must not collapse to one giant passage
    joined = "".join(passages)
    for s in segs:
        assert s["text"] in joined
    for p in passages[:-1]:  # allow slack for a lone oversized turn, like pack_segments
        assert len(p) <= 500 + 400


def test_split_passages_empty_and_single_turn():
    assert split_passages("") == []
    one_turn = format_turn(_segments(1)[0])
    assert split_passages(one_turn, size=500, overlap=100) == [one_turn]


def test_split_passages_oversized_single_turn_kept_whole():
    huge = "[00:00] GM:\n  " + ("x" * 5000) + "\n\n"
    passages = split_passages(huge, size=500, overlap=100)
    assert len(passages) == 1 and passages[0] == huge


def test_session_id_from_path():
    assert session_id_from_path(Path("2025-04-01_RF_LZIuUzc3F18.json")) == "2025-04-01"
    assert session_id_from_path(Path("nodatehere.json")) == "nodatehere"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all chunking invariants pass")
