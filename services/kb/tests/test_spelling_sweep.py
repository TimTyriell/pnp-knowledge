"""Proof that `entity_rules.yaml`'s `spelling:` mechanism (links.py::apply_spellings,
wired through normalize_body) actually reaches the bundle, and that the rules
listed there stay well-formed as the bundle keeps changing underneath them.

Companion to `spelling_doctor.py` (a read-only report) and
`docs/audits/2026-08-30-spelling-sweep.md` (the triage it produced). Unlike
test_rules_applied.py's ratchets, most checks here are *hard*, not a ratchet:
a `spelling:` rule that doesn't fire, or names a concept that doesn't exist,
is a bug the moment it happens, not debt that can be paid down later.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spelling_doctor import (  # noqa: E402
    BUNDLE,
    REGISTRY,
    RULES,
    bundle_files,
    find_occurrences,
    is_shortened_reference,
    load_registry,
    looks_like_mishearing,
    pinned_concept_ids,
    prose_only,
)

pytestmark = pytest.mark.skipif(not REGISTRY.exists(), reason="no bundle checked out")


def _spelling_rules() -> dict[str, str]:
    data = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {} if RULES.exists() else {}
    return {str(k): str(v) for k, v in (data.get("spelling") or {}).items()}


def _bundle_prose() -> dict[Path, str]:
    """Body-only prose (frontmatter stripped, link labels flattened, `#
    Belege` on excluded) for every bundle file — the same view
    ``apply_spellings`` gets. The doctor's own ``prose_only`` does *not*
    strip frontmatter, so a rule key surviving only in frontmatter
    ``aliases:`` (by design, see Decision A in the branch's test plan) is
    correctly invisible here."""

    out = {}
    for path in bundle_files():
        text = path.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        body = parts[2] if len(parts) >= 3 else text
        out[path] = prose_only(body)
    return out


# --- hard gate: a rule that doesn't fire is a bug -----------------------


def test_no_spelling_rule_key_survives_in_prose():
    """Every ``spelling:`` key must be gone from bundle body prose after
    ``apply_spellings`` — if any survive, the rule's own mechanism (word
    boundary matching, `# Belege` exclusion, frontmatter exclusion) is not
    covering some real shape of occurrence."""

    rules = _spelling_rules()
    prose = _bundle_prose()
    violations: list[str] = []
    for key in rules:
        pattern = re.compile(rf"(?<!\w){re.escape(key)}(?!\w)")
        for path, text in prose.items():
            for line_no, line in enumerate(text.split("\n"), start=1):
                if pattern.search(line):
                    rel = path.relative_to(BUNDLE).as_posix()
                    violations.append(f"{key!r} still in {rel}:{line_no}: {line.strip()[:80]!r}")
    assert not violations, (
        "spelling: rule key(s) survive in bundle prose after apply_spellings "
        "should have removed them:\n" + "\n".join(violations)
    )


# --- hard gate: dead-rule guard ------------------------------------------


def test_spelling_values_name_a_real_concept():
    """Every replacement value must be a real, currently-used name — a
    substring (whole word run) of some entity's canonical_name or one of its
    aliases — never a value nobody in the registry actually uses. Mirrors
    test_audit_2026_08_29.py::test_important_pins_name_existing_concepts."""

    entities = load_registry()
    names: list[str] = []
    for e in entities:
        canonical = str(e.get("canonical_name") or "").strip()
        if canonical:
            names.append(canonical)
        names.extend(str(a).strip() for a in (e.get("aliases") or []) if str(a).strip())

    dead = []
    for value in set(_spelling_rules().values()):
        pattern = re.compile(rf"(?<!\w){re.escape(value)}(?!\w)")
        if not any(pattern.search(n) for n in names):
            dead.append(value)
    assert not dead, (
        f"spelling: value(s) matching no registry canonical_name/alias "
        f"(dead on arrival): {sorted(dead)}"
    )


# --- hard gate: rules must not shadow or re-dirty each other ------------


def test_no_spelling_rule_is_self_shadowing():
    """No key is also another rule's replacement value (would ping-pong),
    and no key is a whole-word run inside another rule's value (a later
    substitution pass could re-dirty text the first pass just fixed)."""

    rules = _spelling_rules()
    values = set(rules.values())
    bad = []
    for key in rules:
        if key in values:
            bad.append(f"{key!r} is both a spelling: key and another rule's value")
        for value in values:
            if value == rules[key]:
                continue
            if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", value):
                bad.append(f"key {key!r} recurs inside replacement value {value!r}")
    assert not bad, "\n".join(bad)


# Not every doctor finding gets a rule: docs/audits/2026-08-30-spelling-sweep.md
# manually triages the raw findings into A (rule it), B (phrase-scope it), and
# "excluded" (a legitimate shortened reference the fuzzy matcher over-flags,
# e.g. "Die Gilde" for "Die Gilde von Ehrenfels") — triage is a human step by
# design, so "finding has no rule" is not itself a defect. What IS checked
# above (test_spelling_doctor_findings_are_covered_by_a_rule doesn't exist for
# that reason) is that every rule that *was* written actually fires
# (test_no_spelling_rule_key_survives_in_prose) and names something real
# (test_spelling_values_name_a_real_concept). The raw noise floor itself is
# still watched below so a genuinely new mishearing doesn't hide in it.


# --- ratchets -------------------------------------------------------------

# spelling_doctor.py's own total, unfiltered — dominated by known-excluded
# false positives (legitimate shortened references like "Die Gilde" for "Die
# Gilde von Ehrenfels", 62 hits on its own; see docs/audits/2026-08-30-
# spelling-sweep.md's "Excluded" table). This is NOT "0 is the goal" — it is
# "this number should not silently grow", so a genuinely new mishearing gets
# noticed even though the noise floor never reaches zero. Measured 2026-08-30.
#
# 2026-08-30 review-fix branch: tightened 340 -> 305, re-measured after the
# regeneration. The drop is the arena/turnier_von_willauch renames (1.6b)
# plus emit_sessions finally running apply_spellings on the session index
# blurbs, which had bypassed the spelling map entirely.
SPELLING_DOCTOR_TOTAL_BASELINE = 305


def test_spelling_doctor_total_has_not_grown():
    entities = load_registry()
    pinned = pinned_concept_ids()
    files = bundle_files()
    texts = {p: prose_only(p.read_text(encoding="utf-8")) for p in files}

    total = 0
    for e in entities:
        concept_id = str(e.get("concept_id") or "").strip()
        if concept_id not in pinned:
            continue
        canonical = str(e.get("canonical_name") or "").strip()
        if not canonical:
            continue
        for variant in (str(a).strip() for a in (e.get("aliases") or [])):
            if not variant or variant == canonical or len(variant) < 4:
                continue
            if is_shortened_reference(variant, canonical):
                continue
            if not looks_like_mishearing(variant, canonical):
                continue
            # find_occurrences counts matching LINES, same as spelling_doctor.py's
            # own report — a repeated match on one line is one hit, not two.
            pattern = re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)")
            total += sum(len(find_occurrences(pattern, t)) for t in texts.values())

    assert total <= SPELLING_DOCTOR_TOTAL_BASELINE, (
        f"{total} raw doctor hits, baseline {SPELLING_DOCTOR_TOTAL_BASELINE} "
        f"— a new mishearing-shaped variant appeared. Run spelling_doctor.py "
        f"to see which, triage it (docs/audits/2026-08-30-spelling-sweep.md), "
        f"and only then lower this number."
    )


_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!\w+:)([^)\s]*?\.md)\)")

# Distinct (label, target) pairs where the label text is not the target
# concept's title or any of its aliases, once German inflection is filtered
# out (a trailing/missing genitive -s, or the label being a whole-word
# substring of the title — "Gnollen" of "Die Gnolle", say). What's left is
# every *other* label/target mismatch in the bundle. Measured 2026-08-30:
# corrected labels now pointing at a still-unmerged/stale slug (e.g. "Arena
# von Willauch" -> locations/arena_von_willau, "Berg Zebros" ->
# locations/berge_von_zebros) — not one is an actual mislink, but it is
# exactly the shape the Voras/Vora defect had, so it stays watched. Ratchet:
# may only go down.
#
# 2026-08-30 review-fix branch: tightened 20/26 -> 14/23, re-measured after
# the regeneration. The "Arena von Willauch" -> locations/arena_von_willau
# case named above is one of the pairs that went away: 1.6b gave that
# concept (and events/turnier_von_willauch) the canonical_name pin and
# merge: key the campaign-wide Willauch rename had never actually applied to
# them, so label and target agree now.
LABEL_TARGET_MISMATCH_BASELINE = 14
LABEL_TARGET_MISMATCH_OCCURRENCE_BASELINE = 23


def _title_and_aliases_by_concept() -> dict[str, tuple[str, list[str]]]:
    out = {}
    for path in bundle_files():
        text = path.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        if len(parts) < 3:
            continue
        fm = yaml.safe_load(parts[1]) or {}
        cid = str(path.relative_to(BUNDLE).with_suffix("")).replace("\\", "/")
        out[cid] = (str(fm.get("title") or "").strip(), [str(a).strip() for a in (fm.get("aliases") or [])])
    return out


def _is_benign_label(label: str, names: set[str]) -> bool:
    candidates = {label, label.rstrip("s"), label + "s"}
    if candidates & names:
        return True
    return any(
        re.search(rf"(?<!\w){re.escape(c)}(?!\w)", n) for c in candidates for n in names if n
    )


def test_label_target_mismatch_has_not_grown():
    by_concept = _title_and_aliases_by_concept()
    mismatches: set[tuple[str, str]] = set()
    occurrences = 0
    for path in bundle_files():
        text = path.read_text(encoding="utf-8")
        for label, target in _LINK_RE.findall(text):
            cid = target.lstrip("/").removesuffix(".md").replace("../", "")
            if cid not in by_concept:
                continue
            title, aliases = by_concept[cid]
            names = {title, *aliases}
            if _is_benign_label(label, names):
                continue
            mismatches.add((label, cid))
            occurrences += 1

    assert len(mismatches) <= LABEL_TARGET_MISMATCH_BASELINE, (
        f"{len(mismatches)} distinct label/target mismatches, baseline "
        f"{LABEL_TARGET_MISMATCH_BASELINE}: {sorted(mismatches)}"
    )
    assert occurrences <= LABEL_TARGET_MISMATCH_OCCURRENCE_BASELINE, (
        f"{occurrences} mismatch occurrences, baseline "
        f"{LABEL_TARGET_MISMATCH_OCCURRENCE_BASELINE}"
    )
