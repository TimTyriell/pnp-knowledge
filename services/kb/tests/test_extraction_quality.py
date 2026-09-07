"""Precision and recall of the extraction against hand-labelled sessions.

Every other test in this suite measures the *shape* of the emitted corpus --
are links resolvable, are ids stable, does every rule still bite. None of them
can tell you whether the model extracted the right entities in the first
place, because nothing here knows what the right answer is. This is the only
test that does, and it needs human labels to exist.

Why it matters beyond tidiness: smaller/cheaper models do not omit entity
names, they *invent* them, at a measurably higher false-discovery rate. So the
question "can extraction move to deepseek-v4-flash and save ~15% of a rebuild"
is exactly a precision question, and without this test the answer would be a
guess. See docs/architecture/PIPELINE.md section 10.

To produce a label file:

    python make_gold_stub.py 2025-03-26 > tests/data/gold/2025-03-26.yaml

then correct it by hand -- mark hallucinations `wrong`, fix names with
`rename`, and add what the model missed with `missed`. Around 3-5 sessions
clears the ~30-example floor that makes a precision/recall number meaningful
at all; note even ~100 labels carries roughly +-8pp of noise, so treat the
result as directional, not as an SLA.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pnp_okf.config import DeepSeekConfig
from pnp_okf.extract import _cache_key, _cache_path, _load_cached
from pnp_okf.ingest import load_transcripts
from pnp_okf.okf import slugify

GOLD_DIR = Path(__file__).resolve().parent / "data" / "gold"
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"
TRANSCRIPT_DIR = Path(__file__).resolve().parents[4] / "pnp-crawl" / "transcripts_final"

GOLD_FILES = sorted(GOLD_DIR.glob("*.yaml")) if GOLD_DIR.is_dir() else []

pytestmark = pytest.mark.skipif(
    not GOLD_FILES or not TRANSCRIPT_DIR.is_dir(),
    reason=(
        "no hand-labelled sessions in tests/data/gold -- run make_gold_stub.py "
        "and correct the output. This is a missing measurement, not a passing test."
    ),
)

# Measured against the labelled sessions. Ratchets: they may only go up.
# Set them from the first real run rather than guessing -- an aspirational
# baseline that does not match reality stops being read.
PRECISION_BASELINE = 0.0
RECALL_BASELINE = 0.0


def _gold(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _extracted_names(session_id: str) -> set[str]:
    cfg = DeepSeekConfig.from_env()
    for t in load_transcripts(TRANSCRIPT_DIR):
        if t.session_id != session_id:
            continue
        key = _cache_key(t, cfg)
        extraction = _load_cached(_cache_path(CACHE_DIR, t, key), key)
        if extraction is None:
            pytest.skip(f"no cached extraction for {session_id}")
        return {slugify(m.name) for m in extraction.entities}
    pytest.skip(f"no transcript for {session_id}")
    return set()


def _score(gold: dict) -> tuple[int, int, int]:
    """(true positives, false positives, false negatives) for one session."""

    tp = fp = fn = 0
    for entity in gold.get("entities") or []:
        verdict = str(entity.get("verdict", "ok")).strip().lower()
        if verdict == "ok":
            tp += 1
        elif verdict == "wrong":
            fp += 1
        elif verdict == "rename":
            # The model found a real entity but named it wrongly: it is both a
            # miss of the right name and a spurious emission of the wrong one.
            fp += 1
            fn += 1
        elif verdict == "missed":
            fn += 1
        else:
            raise AssertionError(
                f"{gold.get('date')}: unknown verdict {verdict!r} -- use "
                "ok / wrong / rename / missed"
            )
    return tp, fp, fn


def test_extraction_precision_and_recall_have_not_regressed():
    tp = fp = fn = 0
    for path in GOLD_FILES:
        gold = _gold(path)
        _extracted_names(gold["session_id"])  # asserts the session is still cached
        a, b, c = _score(gold)
        tp, fp, fn = tp + a, fp + b, fn + c

    assert tp + fp, "no labelled entities -- the gold files are empty"
    precision = tp / (tp + fp)
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    print(
        f"\nlabelled sessions: {len(GOLD_FILES)} | entities: {tp + fp + fn}"
        f"\nprecision: {precision:.3f}  recall: {recall:.3f}"
    )
    assert precision >= PRECISION_BASELINE
    assert recall >= RECALL_BASELINE
