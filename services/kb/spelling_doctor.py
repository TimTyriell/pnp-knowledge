"""Diagnose name-spelling drift in the OKF bundle's synthesized prose.

Read-only, no LLM calls. `entity_rules.yaml`'s `canonical_name:` pins a
concept's *title* only -- nothing rewrites the body, so a Whisper mishearing
that made it into the prose survives every re-run untouched. This script
finds every place a *non-canonical* alias spelling still appears in bundle
prose (never in a link target, never past the ``# Belege`` heading) so it can
be triaged into a `spelling:` rule.

Scope is deliberately narrow, on two axes:

1. Only concepts with an explicit `canonical_name:` pin in `entity_rules.yaml`
   are checked. A pin means a human already ruled one spelling correct -- so
   any other alias still in prose is unambiguous drift. Without this filter
   the report drowns in legitimate alternate names that were never ruled on
   (e.g. "Abyssalis"/"Splitterwelt", both campaign-canon, 322 hits).
2. Of a pinned concept's aliases, only ones that look like a *mishearing* of
   the canonical name are reported -- a fuzzy match against one of its words,
   after excluding aliases that are simply a shortened reference (a whole
   word of the canonical name used alone, e.g. "Gilde" for "Die Gilde von
   Ehrenfels", or "Voras" for "Voras der Heilige") or an unrelated nickname
   (e.g. "Moorhexe Hack" for "Landra, die Hag"). Neither of those is a
   spelling error, and treating them as one would produce a `spelling:` rule
   that mangles perfectly good German prose.

    python spelling_doctor.py
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent  # services/kb
KNOWLEDGE = ROOT.parent.parent / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
RULES = KNOWLEDGE / "entity_rules.yaml"
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"

_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!\w+:)([^)\s]*?\.md\))")
_URL_RE = re.compile(r"https?://\S+")
_BELEGE_HEADING_RE = re.compile(r"^#{1,6}\s*Belege\s*$", re.IGNORECASE | re.MULTILINE)
_MIN_ALIAS_LEN = 4  # matches synthesize.py::link_targets' own floor


def prose_only(text: str) -> str:
    """Body text scannable for name drift: link labels kept, targets and
    URLs dropped, everything from `# Belege` on excluded."""

    match = _BELEGE_HEADING_RE.search(text)
    head = text[: match.start()] if match else text
    head = _LINK_RE.sub(lambda m: m.group(1), head)
    head = _URL_RE.sub("", head)
    return head


def load_registry() -> list[dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return data.get("entities") or []


def pinned_concept_ids() -> set[str]:
    data = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {}
    return set((data.get("canonical_name") or {}).keys())


_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_SIMILARITY_FLOOR = 0.55


def is_shortened_reference(variant: str, canonical: str) -> bool:
    """True if ``variant`` is just one of ``canonical``'s own words used
    alone -- a legitimate shortened reference, not a misspelling."""

    canon_words = {w.lower() for w in _WORD_RE.findall(canonical)}
    return variant.lower() in canon_words


def looks_like_mishearing(variant: str, canonical: str) -> bool:
    """True if ``variant`` is a close fuzzy match to some word of
    ``canonical`` -- the shape of a Whisper mishearing -- rather than an
    unrelated nickname or epithet."""

    canon_words = _WORD_RE.findall(canonical)
    best = max(
        (SequenceMatcher(None, variant.lower(), w.lower()).ratio() for w in canon_words),
        default=0.0,
    )
    return best >= _SIMILARITY_FLOOR


def bundle_files() -> list[Path]:
    return [p for p in BUNDLE.rglob("*.md") if p.name not in ("index.md", "log.md")]


def find_occurrences(pattern: re.Pattern, prose: str) -> list[int]:
    """1-indexed line numbers where ``pattern`` matches ``prose``."""

    lines = prose.split("\n")
    return [i + 1 for i, line in enumerate(lines) if pattern.search(line)]


def main() -> None:
    entities = load_registry()
    pinned = pinned_concept_ids()
    files = bundle_files()
    file_prose = {p: prose_only(p.read_text(encoding="utf-8")) for p in files}

    findings: list[tuple[int, str, str, str, list[tuple[Path, int]]]] = []

    for e in entities:
        concept_id = str(e.get("concept_id") or "").strip()
        if concept_id not in pinned:
            continue
        canonical = str(e.get("canonical_name") or "").strip()
        aliases = [str(a).strip() for a in (e.get("aliases") or [])]
        if not canonical:
            continue

        for variant in aliases:
            if not variant or variant == canonical or len(variant) < _MIN_ALIAS_LEN:
                continue
            if is_shortened_reference(variant, canonical):
                continue
            if not looks_like_mishearing(variant, canonical):
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)")
            hits: list[tuple[Path, int]] = []
            for path, prose in file_prose.items():
                for line_no in find_occurrences(pattern, prose):
                    hits.append((path, line_no))
            if hits:
                findings.append((len(hits), concept_id, canonical, variant, hits))

    findings.sort(key=lambda f: f[0], reverse=True)

    total = sum(f[0] for f in findings)
    print(f"# Spelling drift report — {len(findings)} variants, {total} prose occurrences\n")
    for count, concept_id, canonical, variant, hits in findings:
        print(f"## {concept_id}  (\"{variant}\" vs canonical \"{canonical}\") — {count} hit(s)")
        for path, line_no in hits:
            rel = path.relative_to(BUNDLE).as_posix()
            print(f"  {rel}:{line_no}")
        print()


if __name__ == "__main__":
    main()
