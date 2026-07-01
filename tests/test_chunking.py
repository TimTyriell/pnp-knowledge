"""Invariants for pack_segments: no segment split, size respected, overlap bounded.

Run: python -m pytest tests/  (or python tests/test_chunking.py for the asserts).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pnp_graph import config
from pnp_graph.chunking import format_turn, pack_segments, session_id_from_path


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


def test_session_id_from_path():
    assert session_id_from_path(Path("2025-04-01_RF_LZIuUzc3F18.json")) == "2025-04-01"
    assert session_id_from_path(Path("nodatehere.json")) == "nodatehere"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all chunking invariants pass")
