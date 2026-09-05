"""Every hand-authored rule in entity_rules.yaml must have an observable
effect on the real bundle — otherwise it is a decision that was made and then
silently stopped working.

A rule going dead is not hypothetical: entity_rules.yaml has 615 rules
accumulated over the campaign, and extraction is not deterministic across
full rebuilds (state/history.jsonl shows entity counts swinging by dozens
between runs of the same pipeline). When an entity a rule refers to drops out
of one rebuild, the rule keeps existing but points at nothing, and nobody is
told. This is the mechanism behind "I fixed this once, why is it back" for
identity rules (as opposed to conflict rulings, covered by
test_no_conflict_regression.py and test_canon_decisions.py).

Each rule kind is checked against its *observable effect*, not re-parsed and
trusted: a merge rule is applied if its target exists as a concept, not if
the YAML line exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from pnp_okf.okf import slugify
from pnp_okf.resolve import (
    RULES_FILENAME,
    _load_alias_blocks,
    _load_ignored,
    _load_important,
    _load_never_merge_pairs,
    _load_splits,
)

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
RULES = KNOWLEDGE / RULES_FILENAME
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"

pytestmark = pytest.mark.skipif(not REGISTRY.exists(), reason="no bundle checked out")

# Dead rules found when this test was written (services/kb/tests, branch
# test/okf-bundle-quality). Was 37; the 2026-08-29 bundle-quality audit's
# merges/important:-pin fixes plus a real `pnp run` brought it to 15. This
# is a ratchet, not a target: it may only go down as dead rules are
# repaired by re-running the pipeline or editing entity_rules.yaml, and
# must never be raised to make a new regression pass.
DEAD_RULES_BASELINE = 15


def _bundle_concepts() -> set[str]:
    return {
        str(p.relative_to(BUNDLE).with_suffix("")).replace("\\", "/")
        for p in BUNDLE.rglob("*.md")
        if p.name not in ("index.md", "log.md")
    }


def _merge_rules() -> dict[str, str]:
    data: dict = {}
    if REGISTRY.exists():
        data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    if RULES.exists():
        rules = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {}
        data = {**data, **{k: v for k, v in rules.items() if k != "entities"}}
    return data.get("merge") or {}


def _title_for(concept_id: str) -> str | None:
    path = BUNDLE / f"{concept_id}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    fm = (text.split("---\n", 2)[1:2] or [""])[0]
    data = yaml.safe_load(fm) or {}
    return str(data.get("title") or "").strip() or None


def _registry_entities() -> list[dict]:
    if not REGISTRY.exists():
        return []
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return data.get("entities") or []


def test_merge_targets_exist():
    concepts = _bundle_concepts()
    dead = sorted(
        f"{name!r} -> {cid}" for name, cid in _merge_rules().items() if cid not in concepts
    )
    assert not dead or len(dead) <= DEAD_RULES_BASELINE, (
        f"merge rules pointing at a concept that no longer exists ({len(dead)}): {dead}"
    )


def test_never_merge_pairs_are_both_present():
    concepts = _bundle_concepts()
    pairs = _load_never_merge_pairs(REGISTRY)
    half_dead = sorted(
        " / ".join(sorted(pair)) for pair in pairs if sum(c in concepts for c in pair) < 2
    )
    assert not half_dead or len(half_dead) <= DEAD_RULES_BASELINE, (
        f"never_merge pairs where a side no longer exists (rule is a no-op): {half_dead}"
    )


def test_ignore_rules_are_honoured():
    # This one is not a ratchet: a concept under `ignore:` appearing in the
    # bundle is not "the rule went dead", it is the rule being violated by
    # the pipeline right now, which is a different and worse failure mode.
    concepts = _bundle_concepts()
    ignored = _load_ignored(REGISTRY)
    violated = sorted(ignored & concepts)
    assert not violated, f"ignored concepts still present in the bundle: {violated}"


def test_split_targets_exist():
    concepts = _bundle_concepts()
    splits = _load_splits(REGISTRY)
    dead = sorted(
        f"{name!r}@{session} -> {cid}"
        for (name, session), cid in splits.items()
        if cid not in concepts
    )
    assert not dead or len(dead) <= DEAD_RULES_BASELINE, (
        f"split rules pointing at a concept that no longer exists ({len(dead)}): {dead}"
    )


def test_canonical_names_are_applied():
    # Values sourced from `entities:` are the generated inventory's own
    # recollection of itself, so they trivially match; only rules that came
    # from entity_rules.yaml (the hand-authored pins) can meaningfully fail.
    pinned: dict[str, str] = {}
    if RULES.exists():
        rules = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {}
        pinned = {str(k).strip(): str(v).strip() for k, v in (rules.get("canonical_name") or {}).items()}

    dead, mismatched = [], []
    for cid, wanted in pinned.items():
        title = _title_for(cid)
        if title is None:
            dead.append(cid)
        elif title != wanted:
            mismatched.append(f"{cid}: want {wanted!r}, got {title!r}")

    assert not mismatched, f"canonical_name pinned but title differs: {mismatched}"
    assert not dead or len(dead) <= DEAD_RULES_BASELINE, (
        f"canonical_name pins for concepts that no longer exist ({len(dead)}): {dead}"
    )


def test_important_pins_point_at_a_live_concept():
    # Only the dead-pin half: `important:` needs no persistence in the
    # generated registry to work. resolve_entities() calls _load_important(),
    # which reads entity_rules.yaml directly (test_rules_pins.py covers that
    # union), so a pin takes effect on the next run whether or not a previous
    # run happened to bake `important: true` into entity_registry.yaml.
    # Asserting the persisted copy only made every new pin fail the suite
    # until a full (paid) run had regenerated the file.
    important = _load_important(REGISTRY)
    dead = sorted(cid for cid in important if cid not in _bundle_concepts())
    assert not dead or len(dead) <= DEAD_RULES_BASELINE, (
        f"important: pins for concepts that no longer exist ({len(dead)}): {dead}"
    )


def test_alias_blocks_are_honoured():
    # Not a ratchet: an alias that is supposed to be suppressed but is still
    # shown is the rule failing right now, not a stale target.
    blocks = _load_alias_blocks(REGISTRY)
    violations = []
    for cid, blocked in blocks.items():
        path = BUNDLE / f"{cid}.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        fm = (text.split("---\n", 2)[1:2] or [""])[0]
        data = yaml.safe_load(fm) or {}
        aliases = {str(a).strip().lower() for a in (data.get("aliases") or [])}
        leaked = blocked & aliases
        if leaked:
            violations.append(f"{cid}: {sorted(leaked)}")
    assert not violations, f"alias_block violated — blocked alias still shown: {violations}"


def test_dead_rule_count_has_not_grown():
    """One combined ratchet, so a regression is visible even if it is spread
    thinly across several rule kinds instead of piling up in one."""

    concepts = _bundle_concepts()
    dead = 0
    dead += sum(1 for cid in _merge_rules().values() if cid not in concepts)
    dead += sum(1 for p in _load_never_merge_pairs(REGISTRY) if sum(c in concepts for c in p) < 2)
    dead += sum(1 for cid in _load_splits(REGISTRY).values() if cid not in concepts)
    if RULES.exists():
        rules = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {}
        dead += sum(1 for cid in (rules.get("canonical_name") or {}) if cid not in concepts)
    dead += sum(1 for cid in _load_important(REGISTRY) if cid not in concepts)

    assert dead <= DEAD_RULES_BASELINE, (
        f"{dead} dead rules, baseline is {DEAD_RULES_BASELINE} — a rule newly "
        f"lost its target. Investigate before raising the baseline; the fix "
        f"is usually a re-run or an entity_rules.yaml edit, not a bigger number."
    )


# --- article variants slip past ignore:/merge: ---------------------------
#
# 2026-08-29 bundle-quality audit's Question 2/3 finding: entity_rules.yaml
# targets exact strings, so a German article added or dropped produces a
# second, un-ruled concept living right next to the one a rule already
# handles — "npcs/kinder" lives on beside the ignored "npcs/die_kinder",
# "factions/fluechtlinge" beside the merged "die flüchtlinge". This is the
# structural version of that bug: it doesn't fix today's instances (those are
# named individually in Teil 2 of the audit and in test_audit_2026_08_29.py),
# it stops the *next* one from slipping past unnoticed.

_LEADING_ARTICLE_RE = re.compile(r"^(der|die|das|den|dem|des)_(.+)$")
_GERMAN_ARTICLES = ("der", "die", "das")

# Was 12 before entity_rules.yaml Teil 2 (A/F); after a real `pnp run`
# re-extraction surfaced 3 *new* instances of the exact same pattern for
# concepts already ignored bare (der_nebel/die_hoehle/die_falle beside
# nebel/hoehle/falle) -- folded in too, landing at 5. The remaining 5 are
# pre-existing and outside this audit's original 22-duplicate list. Ratchet:
# may only go down.
ARTICLE_VARIANT_BASELINE = 5


def _article_variants(slug: str) -> set[str]:
    """The other German-article spelling(s) of a concept slug: the article
    stripped if the slug has a leading one, or each article prefixed if it
    doesn't — the exact shape of the kinder/die_kinder duplication."""

    m = _LEADING_ARTICLE_RE.match(slug)
    if m:
        return {m.group(2)}
    return {f"{a}_{slug}" for a in _GERMAN_ARTICLES}


def test_article_variant_does_not_slip_past_a_rule():
    concepts = _bundle_concepts()
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {} if RULES.exists() else {}
    merge = rules.get("merge") or {}
    ignore = rules.get("ignore") or []

    bad = []
    for name, target_cid in merge.items():
        etype_dir = target_cid.split("/", 1)[0]
        for variant in _article_variants(slugify(name)):
            variant_cid = f"{etype_dir}/{variant}"
            if variant_cid in concepts and variant_cid != target_cid:
                bad.append(f"merge {name!r} -> {target_cid}, but {variant_cid} also lives in the bundle")
    for cid in ignore:
        etype_dir, slug = cid.split("/", 1)
        for variant in _article_variants(slug):
            variant_cid = f"{etype_dir}/{variant}"
            if variant_cid in concepts and variant_cid != cid:
                bad.append(f"ignore {cid}, but {variant_cid} also lives in the bundle")

    assert len(bad) <= ARTICLE_VARIANT_BASELINE, (
        f"{len(bad)} article-variant duplicate(s) slipped past ignore:/merge: "
        f"(baseline {ARTICLE_VARIANT_BASELINE}): {sorted(bad)}"
    )
