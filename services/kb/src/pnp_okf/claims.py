"""Claim-level evaluation helpers (docs/plans/B3-claim-level-eval.md).

A *claim* is one sentence from an entity body. `split_claims` cuts the body
into those sentences; `score` turns human verdicts into supported rates.
Deterministic and offline: the sampler that feeds it lives in
services/kb/claim_sampler.py.
"""

from __future__ import annotations

import re
from collections import defaultdict

VERDICTS = ("supported", "unsupported", "misattributed", "claimed_not_observed", "unclear")
MIN_WORDS = 6

# German abbreviations whose full stop must not end a sentence. Without this,
# "z. B. mit einer Axt" splits into two claims and the second is a fragment a
# labeller cannot judge. Matched with their dots; the dots are protected before
# splitting and restored after.
_ABBREV = re.compile(
    r"\b(?:z\. ?B|z\. ?T|d\. ?h|u\. ?a|v\. ?a|bzw|ca|Nr|usw|bspw|vgl|ggf|evtl|inkl|etc|Dr|St|Hr|Fr)\."
)
# A sentence ends at . ! ? … (optionally closed by a quote or bracket) and the
# next sentence starts with a capital, an opening quote or a bracket.
_BOUNDARY = re.compile(r"[.!?…][”“\"»)]*\s+(?=[A-ZÄÖÜ„“\"(\[*])")
_PROTECTED_DOT = "\x00"


def _plain(line: str) -> str:
    """Strip markdown the sentence splitter should not see: heading and bullet
    markers, link targets (keep the link text), bold markers."""

    line = re.sub(r"^\s*(?:#+\s*|[-*]\s+|\d+\.\s+)", "", line)
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
    return line.replace("**", "").strip()


def split_claims(body: str) -> list[str]:
    """Sentences of an entity body that are long enough to be a claim.

    Stops at the ``# Belege`` / ``## Belege`` section: the citation list is bookkeeping, not
    something a labeller should judge. Sentences under MIN_WORDS words are
    dropped (fragments, interjections, headings).
    """

    body = re.split(r"^#{1,2} Belege\s*$", body, flags=re.M)[0]
    claims: list[str] = []
    for line in body.splitlines():
        text = _plain(line)
        if not text:
            continue
        text = _ABBREV.sub(lambda m: m.group(0).replace(".", _PROTECTED_DOT), text)
        pos = 0
        for m in _BOUNDARY.finditer(text):
            claims.append(text[pos : m.end()])
            pos = m.end()
        claims.append(text[pos:])
    out = []
    for sentence in claims:
        sentence = sentence.replace(_PROTECTED_DOT, ".").strip()
        if len(sentence.split()) >= MIN_WORDS:
            out.append(sentence)
    return out


def _rate(rows: list[dict]) -> float | None:
    scored = [r for r in rows if r["verdict"] != "unclear"]
    if not scored:
        return None
    return sum(r["verdict"] == "supported" for r in scored) / len(scored)


def score(labels: list[dict]) -> dict:
    """Supported rate overall and per type and tier.

    ``labelled`` counts every non-empty verdict (the gate for "is there a file
    worth scoring"). ``n`` and the rates exclude ``unclear`` (a labeller who
    cannot tell is not evidence either way) and unlabelled rows. An unknown
    verdict raises: a typo must not silently fall out of the denominator.
    """

    rows = []
    for label in labels:
        verdict = str(label.get("verdict") or "").strip()
        if not verdict:
            continue
        if verdict not in VERDICTS:
            raise ValueError(f"unknown verdict {verdict!r} -- use one of {', '.join(VERDICTS)}")
        rows.append({**label, "verdict": verdict})

    by_type: dict[str, list[dict]] = defaultdict(list)
    by_tier: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["verdict"] != "unclear":
            by_type[r["type"]].append(r)
            by_tier[r["tier"]].append(r)

    def block(group: list[dict]) -> dict:
        return {"n": len(group), "supported_rate": _rate(group)}

    return {
        "labelled": len(rows),
        "n": sum(len(g) for g in by_type.values()),
        "supported_rate": _rate(rows),
        "by_type": {k: block(v) for k, v in sorted(by_type.items())},
        "by_tier": {k: block(v) for k, v in sorted(by_tier.items())},
    }
