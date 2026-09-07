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
`rename` (and give the corrected name in `should_be:`), and add what the model
missed with `missed`. Around 3-5 sessions clears the ~30-example floor that
makes a precision/recall number meaningful at all; note even ~100 labels
carries roughly +-8pp of noise, so treat the result as directional, not as an
SLA.

The score is a set comparison between the labels and the *current* cached
extraction, not a tally of the verdict column: a number derived from the
labels alone cannot move when the extractor moves, which would leave the
model question it exists to answer unanswerable. The corollary is that the
labels have to come from somewhere other than the extraction -- a stub the
model graded for itself agrees with itself by construction.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from pnp_okf.config import DeepSeekConfig
from pnp_okf.extract import load_cached_extraction
from pnp_okf.ingest import load_transcripts
from pnp_okf.okf import slugify

GOLD_DIR = Path(__file__).resolve().parent / "data" / "gold"
# PNP_CACHE_DIR wins, as it does for the pipeline; the fallback is anchored on
# this file rather than the CWD, because pytest runs from the repo root.
CACHE_DIR = Path(
    os.environ.get("PNP_CACHE_DIR") or Path(__file__).resolve().parents[1] / ".cache"
)
TRANSCRIPT_DIR = Path(__file__).resolve().parents[4] / "pnp-crawl" / "transcripts_final"

GOLD_FILES = sorted(GOLD_DIR.glob("*.yaml")) if GOLD_DIR.is_dir() else []

# Only the scoring test needs the corpus; it is a decorator rather than a
# module-level pytestmark so the truth-set unit test below still runs in CI,
# where pnp-crawl and .cache are absent. The two reasons are separate because
# they call for different responses: write the labels, vs check out the corpus.
needs_labels = pytest.mark.skipif(
    not GOLD_FILES,
    reason=(
        "no hand-labelled sessions in tests/data/gold -- run make_gold_stub.py "
        "and correct the output. This is a missing measurement, not a passing test."
    ),
)
needs_corpus = pytest.mark.skipif(
    not TRANSCRIPT_DIR.is_dir(),
    reason="no local transcript corpus (pnp-crawl is a separate repo, absent in CI)",
)

# Measured 2026-09-07 over 3 labelled sessions, 71 entities:
#   precision 1.000  (70 true positives, 0 hallucinated)
#   recall    0.986  (one miss: no faction for the besieging undead on 2026-01-20)
#
# The baselines sit BELOW those measurements on purpose, and not out of
# timidity. With 71 samples and zero precision errors, the rule of three puts
# the 95% upper bound on the true error rate near 3/71 ~ 4%, so the honest
# floor is ~0.96, not 1.00. Pinning a baseline to a point estimate that the
# sample size cannot support produces a test that fails on noise, and a test
# that fails on noise gets deleted.
#
# ⚠ These numbers are only valid for THIS label set. Recall is a function of
# how complete the labels are, so ADDING a `missed` entry lowers measured
# recall without the pipeline having changed. That is a label improvement, not
# a regression: re-measure and re-set both baselines when the labels change,
# and say so in the commit. Growing the label set is the main way these
# numbers get more trustworthy.
#
# ⚠⚠ The current labels were AI-drafted from the same extraction they score
# (de135e1, marked `reviewed: true` by 2af4886). A model checking its own
# output agrees with itself by construction, so precision 1.000 is what that
# arrangement has to produce and carries no information about the extractor.
# Until a human has actually read these files, treat both numbers as evidence
# that the harness RUNS, not as a quality result -- and expect the first
# human-reviewed measurement to be lower. That is the ratchet finally being
# set from reality, not a regression.
PRECISION_BASELINE = 0.96
RECALL_BASELINE = 0.95


def _gold(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        # Hand-edited labels; a stray comma or a missing space after a colon
        # should name the file, not surface as a composer traceback.
        pytest.fail(f"{path.name} is not valid YAML: {exc}")


def _extracted_names(session_id: str) -> set[str]:
    # for_tier("extract"), or DEEPSEEK_EXTRACT_MODEL changes the cache key and
    # every session reads as uncached -- and the model swap is the question
    # this test exists to answer.
    cfg = DeepSeekConfig.from_env().for_tier("extract")
    for t in load_transcripts(TRANSCRIPT_DIR):
        if t.session_id != session_id:
            continue
        extraction = load_cached_extraction(CACHE_DIR, t, cfg)
        if extraction is None:
            pytest.skip(f"no cached extraction for {session_id}")
        return {slugify(m.name) for m in extraction.entities}
    pytest.skip(f"no transcript for {session_id}")
    return set()


def _truth_names(gold: dict, where: str) -> set[str]:
    """Slugified names the extraction *should* have produced for one session.

    ``wrong`` is deliberately absent: a hallucination belongs in neither the
    truth set nor the score's numerator, and if the extractor still emits it,
    the set difference puts it in fp on its own. ``rename`` contributes the
    corrected name, which is what makes ``should_be:`` load-bearing rather
    than a comment.
    """

    names: set[str] = set()
    for entity in gold.get("entities") or []:
        verdict = str(entity.get("verdict", "ok")).strip().lower()
        name = str(entity.get("name") or "").strip()
        if verdict in ("ok", "missed"):
            names.add(slugify(name))
        elif verdict == "rename":
            should_be = str(entity.get("should_be") or "").strip()
            assert should_be, (
                f"{where}: {name!r} is marked `rename` but carries no "
                "`should_be:` -- the corrected name is what gets scored"
            )
            names.add(slugify(should_be))
        elif verdict != "wrong":
            raise AssertionError(
                f"{where}: unknown verdict {verdict!r} -- use "
                "ok / wrong / rename / missed"
            )
    return names


@needs_labels
@needs_corpus
def test_extraction_precision_and_recall_have_not_regressed():
    tp = fp = fn = 0
    scored = 0
    unreviewed = []
    for path in GOLD_FILES:
        gold = _gold(path)
        # A freshly generated stub marks every entity `ok`, so scoring one
        # would report perfect precision and recall from labels nobody has
        # read -- the same failure as an eval suite that passes by skipping.
        if not gold.get("reviewed"):
            unreviewed.append(path.name)
            continue
        # The score is a comparison, not a tally of the labels: the number has
        # to move when the extraction moves, or it cannot answer whether the
        # extractor may change.
        actual = _extracted_names(gold["session_id"])
        truth = _truth_names(gold, path.name)
        tp += len(actual & truth)
        fp += len(actual - truth)
        fn += len(truth - actual)
        scored += 1

    if not scored:
        pytest.skip(
            "no reviewed gold files yet ("
            + ", ".join(unreviewed)
            + " are unreviewed stubs). Correct them by hand, then set "
            "`reviewed: true`."
        )
    if unreviewed:
        print(f"\nnote: skipping unreviewed stub(s): {', '.join(unreviewed)}")

    assert tp + fp, "no labelled entities -- the gold files are empty"
    precision = tp / (tp + fp)
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    print(
        f"\nscored sessions: {scored} of {len(GOLD_FILES)} | entities: {tp + fp + fn}"
        f"\nprecision: {precision:.3f}  recall: {recall:.3f}"
    )
    assert precision >= PRECISION_BASELINE
    assert recall >= RECALL_BASELINE


def test_the_truth_set_is_what_should_have_been_extracted():
    """The verdicts have to mean something against a real extraction.

    Scoring used to add up the verdict column, so the result was a property of
    the label file: change the extractor and the number did not move. It is a
    set comparison now, and this pins what each verdict contributes -- in
    particular that `wrong` is *absent* from the truth set (so an extractor
    still emitting it scores a false positive) and that `rename` contributes
    `should_be`, not the name the model produced.
    """

    gold = {
        "entities": [
            {"name": "Lindo Laut", "verdict": "ok"},
            {"name": "Ritualplatz", "should_be": "Ritualplatz im Wald", "verdict": "rename"},
            {"name": "Der Erzähler", "verdict": "wrong"},
            {"name": "Beschwörungskessel", "verdict": "missed"},
        ]
    }

    assert _truth_names(gold, "x.yaml") == {
        "lindo_laut",
        "ritualplatz_im_wald",
        "beschwoerungskessel",
    }

    with pytest.raises(AssertionError, match="should_be"):
        _truth_names({"entities": [{"name": "A", "verdict": "rename"}]}, "x.yaml")

    with pytest.raises(AssertionError, match="unknown verdict"):
        _truth_names({"entities": [{"name": "A", "verdict": "vielleicht"}]}, "x.yaml")
