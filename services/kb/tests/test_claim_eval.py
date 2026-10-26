"""Supported rate of the bundle's claims, against human-labelled claim files (B3).

test_extraction_quality.py measures whether the right *names* were extracted.
This measures whether the bundle's *statements* are true: a human reads each
sampled claim against the transcript window around its citation and marks it
supported / unsupported / misattributed / claimed_not_observed / unclear.

Files live in tests/data/claims/ and are committed scrubbed (player first names
replaced in speaker labels, see claim_sampler.scrub_speaker). An unlabelled
draft is an intentional skip, not a pass: only a file with >= 50 non-empty
verdicts is scored.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pnp_okf.claims import score

CLAIMS_DIR = Path(__file__).resolve().parent / "data" / "claims"
MIN_LABELLED = 50

# Set from the first human-labelled run (docs/plans/B3-claim-level-eval.md,
# step 5), not yet. Until then the test skips even with labels present: a
# baseline guessed before anyone has read a claim would be a number nobody
# measured. Once set, comment the origin and the noise margin (n=60 is about
# +-12pp), and only ever raise it.
CLAIM_SUPPORTED_BASELINE: float | None = None


def _labelled_files() -> list[Path]:
    """Claim files with enough non-empty verdicts to be scored at all."""

    if not CLAIMS_DIR.is_dir():
        return []
    out = []
    for path in sorted(CLAIMS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = data.get("claims") or []
        if sum(1 for c in rows if str(c.get("verdict") or "").strip()) >= MIN_LABELLED:
            out.append(path)
    return out


def test_claim_supported_rate_has_not_regressed():
    files = _labelled_files()
    if not files:
        pytest.skip(
            "no human-labelled claim file: tests/data/claims/ has no file with "
            f">= {MIN_LABELLED} non-empty verdicts. Label the sampled claims by hand "
            "(docs/plans/B3-claim-level-eval.md, step 5). This is a missing "
            "measurement, not a passing test."
        )
    if CLAIM_SUPPORTED_BASELINE is None:
        pytest.skip(
            "CLAIM_SUPPORTED_BASELINE is unset: a labelled file exists, but the "
            "baseline is set from the first human-labelled run, not guessed."
        )

    rows = []
    for path in files:
        rows += yaml.safe_load(path.read_text(encoding="utf-8"))["claims"]
    result = score(rows)
    print(
        f"\nclaims scored: {result['n']} | supported rate: {result['supported_rate']:.3f}"
    )
    assert result["supported_rate"] >= CLAIM_SUPPORTED_BASELINE
