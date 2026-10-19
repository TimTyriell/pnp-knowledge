# A5 — Citation-grounding ratchet, and fix the known-wrong gold label

| | |
|---|---|
| Branch | `test/citation-grounding` |
| Base | `origin/main` (after A4 merged) |
| Depends on | A4 (stable cache keys, so the measurement reads the right cache) |
| Cost | $0. Reads cached extractions only |
| Size | S |
| Gate | The gold-label change needs **human confirmation** (step 5) |

## Goal

1. Add a deterministic, cheap correctness signal for extraction. For each
   cached mention, check whether the entity's name actually occurs in the
   transcript **near its cited timestamp**.
   - Measured 2026-10-18 over 1896 mentions: 75% near, 20% only elsewhere in
     the session, 4.4% nowhere. Events: 60 / 29 / 11.
   - Pin it as a ratchet that may only go up.
2. Correct `tests/data/gold/2025-03-26.yaml`.
   - "Esterossa" @ 01:46:53 is marked `ok`, but Esterossa never appears in
     that transcript. The note describes Cookie (the frog ranger).
   - The label set scores a hallucination as correct, so its precision
     1.000 is not evidence of anything.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c test/citation-grounding origin/main
```

### 2. Pure function: `services/kb/src/pnp_okf/grounding.py` (new)

```python
"""Is an extracted entity's name actually spoken near the moment it cites?

A cheap, deterministic correctness signal for extraction (docs/plans/A5).
It cannot prove a note is true, but a name that never occurs within the
cited window -- or nowhere in the session -- is a strong hint the model
invented the citation or the entity. Coined event names score low by
nature, so they are reported separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pnp_okf.context import _parse_ts
from pnp_okf.models import EntityType, SessionExtraction, SessionTranscript

WINDOW_S = 120.0
MIN_TOKEN = 4
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def name_tokens(name: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(name) if len(t) >= MIN_TOKEN}


@dataclass
class GroundingCounts:
    near: int = 0
    elsewhere: int = 0
    nowhere: int = 0
    unscorable: int = 0   # no token >= MIN_TOKEN, or unparseable timestamp

    @property
    def scored(self) -> int:
        return self.near + self.elsewhere + self.nowhere

    @property
    def near_ratio(self) -> float:
        return self.near / self.scored if self.scored else 0.0


def ground_session(
    transcript: SessionTranscript, extraction: SessionExtraction, window: float = WINDOW_S
) -> dict[str, GroundingCounts]:
    """Counts keyed by "all" and by entity type value (e.g. "Event")."""

    segs = [(s.start, s.text.lower()) for s in transcript.segments]
    whole = " ".join(t for _, t in segs)
    out: dict[str, GroundingCounts] = {"all": GroundingCounts()}
    for m in extraction.entities:
        bucket = out.setdefault(m.type.value, GroundingCounts())
        tokens = name_tokens(m.name)
        ts = _parse_ts(m.citation_ts)
        if not tokens or ts is None:
            out["all"].unscorable += 1
            bucket.unscorable += 1
            continue
        near_text = " ".join(t for start, t in segs if abs(start - ts) <= window)
        if any(tok in near_text for tok in tokens):
            kind = "near"
        elif any(tok in whole for tok in tokens):
            kind = "elsewhere"
        else:
            kind = "nowhere"
        for c in (out["all"], bucket):
            setattr(c, kind, getattr(c, kind) + 1)
    return out
```

Substring matching (`tok in text`) is deliberate. German inflects names
("Lindos", "Rotunas'"), and Whisper splits compounds.

### 3. Unit tests: `services/kb/tests/test_grounding.py` (new)

Build a `SessionTranscript` with segments at 0s ("Wir treffen Rotunas"),
300s ("Lange Pause"), 900s ("Nox lacht"). Build an extraction with:

- Rotunas @ 00:00:30 → near;
- Nox @ 00:00:30 → elsewhere (only at 900s);
- Esterossa @ 00:00:30 → nowhere;
- "Ox" (no token ≥ 4) → unscorable;
- a Rotunas mention with timestamp "kaputt" → unscorable.

Assert all five counts, `near_ratio`, and the per-type bucket for an Event
mention.

### 4. Corpus ratchet: append to `tests/test_extraction_quality.py`

Reuse that file's `needs_corpus` marker, `TRANSCRIPT_DIR` and `CACHE_DIR`,
and its `_cfg` pattern (`DeepSeekConfig.from_env().for_tier("extract")`).
Note that `from_env` needs `DEEPSEEK_API_KEY` set; the existing tests
already assume `.env` locally.

```python
# Citation grounding (A5): share of scorable mentions whose name occurs within
# +-120 s of the cited timestamp. Measured 2026-10-18: <ALL>% overall, <EV>% for
# Events (1896 mentions). A ratchet -- only ever raise these, with a comment.
GROUNDED_NEAR_BASELINE = <ALL - 1 point, as a fraction>
GROUNDED_NOWHERE_CEILING = <NOWHERE + 1 point, as a fraction>


@needs_corpus
def test_citations_are_grounded_in_their_window():
    from pnp_okf.grounding import GroundingCounts, ground_session

    cfg = DeepSeekConfig.from_env().for_tier("extract")
    total = GroundingCounts()
    for t in load_transcripts(TRANSCRIPT_DIR):
        ex = load_cached_extraction(CACHE_DIR, t, cfg)
        if ex is None:
            continue
        c = ground_session(t, ex)["all"]
        total.near += c.near
        total.elsewhere += c.elsewhere
        total.nowhere += c.nowhere
    assert total.scored > 1000, "too few cached mentions -- wrong cache or model?"
    assert total.near_ratio >= GROUNDED_NEAR_BASELINE
    assert total.nowhere / total.scored <= GROUNDED_NOWHERE_CEILING
```

Measure the numbers first with a throwaway snippet calling the same code,
and print `near`, `elsewhere`, `nowhere` overall and for Events. Set the
baselines **one percentage point below** (near) or **above** (nowhere) the
measurement, so noise doesn't flap the test. The file's own comments explain
why.

Also print the 20 "nowhere" mentions with the highest confidence of being
wrong (non-Event types). Paste that list into the PR body for the human. It
is a free hallucination shortlist.

### 5. Gold fix: STOP for human confirmation

Show the human this evidence in the PR description:

- Transcript `2025-03-26_RF_ROCKGeeRUFw` (pnp-crawl `transcripts_final`):
  `grep -ci esterossa` → 0. Paste the speakers seen near 01:46:53.
- The extracted note for "Esterossa" (from `make_gold_stub.py 2025-03-26`
  output).

Proposed change in `tests/data/gold/2025-03-26.yaml`:

```yaml
  - name: 'Esterossa'
    type: Character
    citation_ts: '01:46:53'
    verdict: wrong
    # Never spoken in this session; the note describes Cookie (frog
    # ranger). Hallucinated attribution -- found by A5 citation grounding.
```

Also add to the file's header comment: "2026-10-xx: one `ok` corrected to
`wrong` after a transcript check (A5). The AI-drafted labels were not
human-reviewed per entity, see test_extraction_quality.py."

After the human confirms:
- re-run `test_extraction_quality.py`;
- precision drops to ~0.986;
- per that file's own rule, **re-set both baselines** with a comment ("label
  improvement, not a regression").

### 6. Verify, commit, PR

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q tests/test_grounding.py tests/test_extraction_quality.py && .venv/Scripts/python.exe -m pytest -q
cd ../.. && ruff check .
```

Commits:
1. `test(kb): measure citation grounding of cached extractions`
2. `test(kb): correct a hallucinated gold label and re-baseline` (after the
   human OK)

## Done when

- [ ] The grounding ratchet runs locally and skips in CI (no corpus).
- [ ] The hallucination shortlist is in the PR.
- [ ] Gold corrected and baselines re-set, with the human's OK recorded.
