"""Offline evaluation of entity-name -> concept matchers against the 269
hand-written `merge:` rules in entity_rules.yaml, treated as a labelled
dataset -- implements docs/architecture/TESTPLAN-entity-matching.md.

No argparse, unlike the testplan's ask: matches the sibling scripts
rules_doctor.py/spelling_doctor.py (module constants, no flags anyone would
pass), and there is nothing here a flag would usefully gate.

    python eval_matching.py

Read-only, no LLM calls, no pipeline mutation. Imports pnp_okf.resolve for
its matching primitives (_sorted_slug, _registry_data, _load_*) so V0 is
provably the shipped baseline rather than a lookalike; never imports dedup
(the LLM client) or touches resolve.py itself.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

from pnp_okf import resolve
from pnp_okf.okf import slugify

ROOT = Path(__file__).resolve().parent  # services/kb
KNOWLEDGE = ROOT.parent.parent / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
CACHE_EXTRACT = ROOT / ".cache" / "extract"

THRESHOLDS = [t / 100 for t in range(60, 100, 5)]
VARIANTS = ["V0", "V1", "V2", "V3", "V4"]

# E2 gold: parent concept per (split name, session), read off entity_rules.yaml's
# split: comments and each target's own compound id (e.g. "...auf_dem_berg" ->
# locations/berg_heiligtum). Built by hand -- the testplan calls this a one-off
# manual step, not something to derive algorithmically. Rows with no parent
# named anywhere (id, comment) are left out of GOLD_PARENTS entirely; see
# DROPPED below for which and why. Three rows deliberately gold to a person
# (characters/npcs), not a location -- the heuristic can only propose a
# location, so these are expected, reported misses, not implementation bugs.
GOLD_PARENTS: dict[tuple[str, str], str] = {
    ("die taverne", "2026-04-09"): "locations/ehrenfels",
    ("mine", "2026-07-10"): "locations/heinrich_farm",
    ("die mine", "2026-07-10"): "locations/heinrich_farm",
    ("kapelle", "2025-09-02"): "locations/berg_heiligtum",
    ("die kapelle", "2025-09-02"): "locations/berg_heiligtum",
    ("sumpf", "2025-04-01"): "locations/goblin_dorf",
    ("der sumpf", "2025-04-01"): "locations/goblin_dorf",
    # Retargeted 2026-08-29 from the dead locations/sumpf_bei_nebelwacht (per
    # the rule's own comment) -- that dead id is where the parent comes from.
    ("sumpf", "2026-05-27"): "locations/nebelwacht",
    ("seelenstein", "2025-06-17"): "characters/rotunas",
    ("seelenstein", "2025-06-25"): "characters/rotunas",
    # Same session's own split rule says harald -> npcs/abisalis_harald.
    ("seelenstein", "2026-04-14"): "npcs/abisalis_harald",
    ("die bibliothek", "2026-03-03"): "locations/willauch",
    ("ende", "2026-03-18"): "locations/orkgebiet",
    ("das ende", "2025-10-07"): "locations/orkgebiet",
    ("die stadt", "2025-05-27"): "locations/ehrenfels",
}
DROPPED = [
    ("mine", "2025-10-07", "no parent named in id or rule comment"),
    ("die mine", "2025-10-07", "no parent named in id or rule comment"),
    ("sumpf", "2026-02-17", "rule comment explicitly says 'do not guess'"),
    ("seelenstein", "2026-01-13", "no owner/location named"),
    ("der grüne seelenstein", "2026-01-13", "no owner/location named"),
]
# Person-name split rows (holodarn/adeliga/adelia/hans/hendrik/harald/jen) are
# not generic nouns and are out of E2's scope entirely -- not in GOLD_PARENTS,
# not in DROPPED.


# --- V2: Koelner Phonetik (hand-written, no phonetic library is installed) --

_VOWELS = set("aeiouy")


def _koelner_code(word: str) -> str:
    codes: list[str] = []
    n = len(word)
    for i, ch in enumerate(word):
        prev = word[i - 1] if i > 0 else ""
        nxt = word[i + 1] if i + 1 < n else ""
        if ch in _VOWELS:
            code = "0"
        elif ch == "h":
            continue
        elif ch == "b":
            code = "1"
        elif ch == "p":
            code = "3" if nxt == "h" else "1"
        elif ch in "dt":
            code = "8" if nxt in "csz" else "2"
        elif ch in "fvw":
            code = "3"
        elif ch in "gkq":
            code = "4"
        elif ch == "c":
            if i == 0:
                code = "4" if nxt in "ahkloqrux" else "8"
            elif prev in "sz":
                code = "8"
            else:
                code = "4" if nxt in "ahkoqux" else "8"
        elif ch == "x":
            code = "8" if prev in "ckq" else "48"
        elif ch == "l":
            code = "5"
        elif ch in "mn":
            code = "6"
        elif ch == "r":
            code = "7"
        elif ch in "sz":
            code = "8"
        else:
            continue
        codes.append(code)
    out: list[str] = []
    for code in codes:
        for digit in code:
            if not out or out[-1] != digit:
                out.append(digit)
    return "".join(d for d in out if d != "0")


def koelner_slug(bare_slug: str) -> str:
    return "_".join(_koelner_code(tok) for tok in bare_slug.split("_"))


# --- V3: hand-written German equivalence classes ----------------------------

# ue-before-translate ordering matters: slugify() already turned any u-umlaut
# into the two ASCII characters "ue" (okf.py::slugify), so the y=i=ue class
# has to key on the two-character "ue" and must run before the single-char
# translate table below, or the "u" and "e" would each be remapped on their
# own by unrelated rules first and the digraph would never be seen intact.
_DIGRAPHS = [("ei", "ai"), ("ue", "i"), ("y", "i")]
_EQUIV = str.maketrans({"w": "v", "b": "v", "f": "v", "d": "t", "g": "k", "c": "k", "z": "s"})
_RUN_RE = re.compile(r"(.)\1+")


def v3_normalize(bare_slug: str) -> str:
    s = bare_slug
    for src, dst in _DIGRAPHS:
        s = s.replace(src, dst)
    s = s.translate(_EQUIV)
    return _RUN_RE.sub(r"\1", s)


# --- shared scoring machinery ------------------------------------------------


def _pairwise_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, resolve._sorted_slug(a), resolve._sorted_slug(b)).ratio()


def score_v0(name: str, candidate_bare: str) -> float:
    return _pairwise_ratio(slugify(name), candidate_bare)


def score_v2(name: str, candidate_bare: str) -> float:
    return _pairwise_ratio(koelner_slug(slugify(name)), koelner_slug(candidate_bare))


def score_v3(name: str, candidate_bare: str) -> float:
    return _pairwise_ratio(v3_normalize(slugify(name)), v3_normalize(candidate_bare))


def build_context(candidate_ids: list[str], entities: list[dict]) -> dict:
    """Precompute everything that does not depend on the query name, once,
    so the 269 x 1092(+aliases) scoring pass does not redo it per query."""

    def pool(transform):
        return {cid: resolve._sorted_slug(transform(cid.rsplit("/", 1)[-1])) for cid in candidate_ids}

    return {
        "candidate_ids": candidate_ids,
        "pool_v0": pool(lambda s: s),
        "pool_v2": pool(koelner_slug),
        "pool_v3": pool(v3_normalize),
        "rows_v1": build_alias_rows(entities, lambda s: s),
        "rows_v4": build_alias_rows(entities, v3_normalize),
    }


def build_alias_rows(entities: list[dict], transform) -> list[tuple[str, str | None, str, str]]:
    """One row per candidate's id-slug, plus one row per alias: (concept_id,
    alias_lower_or_None, variant_slug, precomputed_sorted_repr)."""

    rows: list[tuple[str, str | None, str, str]] = []
    for e in entities:
        cid = str(e.get("concept_id", "")).strip()
        if not cid:
            continue
        bare = cid.rsplit("/", 1)[-1]
        rows.append((cid, None, bare, resolve._sorted_slug(transform(bare))))
        for alias in e.get("aliases") or []:
            alias = str(alias).strip()
            if not alias:
                continue
            vslug = slugify(alias)
            rows.append((cid, alias.lower(), vslug, resolve._sorted_slug(transform(vslug))))
    return rows


def pool_scores(name: str, candidate_reprs: dict[str, str], transform=lambda s: s) -> dict[str, float]:
    q = resolve._sorted_slug(transform(slugify(name)))
    return {cid: SequenceMatcher(None, q, rep).ratio() for cid, rep in candidate_reprs.items()}


def closure_scores(name: str, rows: list[tuple[str, str | None, str, str]], transform=lambda s: s) -> dict[str, float]:
    # Leave-one-out: the registry's aliases were partly produced by the very
    # merges under test. A row whose wording IS the query name (or slugifies
    # to it) could only be here because some hand rule already folded it in --
    # scoring against it would let V1/V4 "find" the answer they are supposed
    # to be predicting. Applied to every candidate, not just the gold one: a
    # different concept's leaked alias would otherwise outrank gold and
    # manufacture a fake miss instead of a fake hit.
    name_l = name.strip().lower()
    name_slug = slugify(name)
    q = resolve._sorted_slug(transform(name_slug))
    best: dict[str, float] = {}
    for cid, alias_lower, variant_slug, rep in rows:
        if alias_lower == name_l or variant_slug == name_slug:
            continue
        ratio = SequenceMatcher(None, q, rep).ratio()
        if ratio > best.get(cid, -1.0):
            best[cid] = ratio
    return best


def variant_scores_for_name(variant: str, name: str, ctx: dict) -> dict[str, float]:
    if variant == "V0":
        return pool_scores(name, ctx["pool_v0"])
    if variant == "V2":
        return pool_scores(name, ctx["pool_v2"], koelner_slug)
    if variant == "V3":
        return pool_scores(name, ctx["pool_v3"], v3_normalize)
    if variant == "V1":
        return closure_scores(name, ctx["rows_v1"])
    if variant == "V4":
        return closure_scores(name, ctx["rows_v4"], v3_normalize)
    raise ValueError(variant)


def pair_score(variant: str, id_a: str, id_b: str, ctx: dict) -> float:
    """Score between two concept ids directly (never_merge check), on the
    concept-id slug -- same reasoning as resolve._tokens: a display pin must
    not move a matching decision."""

    bare_a, bare_b = id_a.rsplit("/", 1)[-1], id_b.rsplit("/", 1)[-1]
    if variant in ("V1", "V4"):
        s1 = variant_scores_for_name(variant, bare_a, ctx).get(id_b, -1.0)
        s2 = variant_scores_for_name(variant, bare_b, ctx).get(id_a, -1.0)
        return max(s1, s2)
    return variant_scores_for_name(variant, bare_a, ctx).get(id_b, -1.0)


# --- ground truth / cache loading -------------------------------------------


def load_ground_truth(registry_path: Path = REGISTRY) -> dict:
    data = resolve._registry_data(registry_path)
    merge = {str(k).strip().lower(): str(v).strip() for k, v in (data.get("merge") or {}).items()}
    entities = data.get("entities") or []
    candidate_ids = [str(e.get("concept_id", "")).strip() for e in entities if e.get("concept_id")]
    return {
        "merge": merge,
        "entities": entities,
        "candidate_ids": candidate_ids,
        "never_merge": resolve._load_never_merge_pairs(registry_path),
        "splits": resolve._load_splits(registry_path),
        "ignore_count": len(data.get("ignore") or []),
    }


def all_extracted_names(cache_dir: Path = CACHE_EXTRACT) -> set[str]:
    names: set[str] = set()
    for session_dir in sorted(p for p in cache_dir.iterdir() if p.is_dir()):
        for f in session_dir.glob("*.json"):
            try:
                blob = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for ent in blob.get("extraction", {}).get("entities", []):
                n = str(ent.get("name", "")).strip()
                if n:
                    names.add(n)
    return names


def live_stale_split(merge: dict[str, str], cache_dir: Path = CACHE_EXTRACT) -> tuple[dict, dict]:
    extracted = {n.lower() for n in all_extracted_names(cache_dir)}
    live = {n: c for n, c in merge.items() if n in extracted}
    stale = {n: c for n, c in merge.items() if n not in extracted}
    return live, stale


def trivial_positive_count(merge: dict[str, str]) -> int:
    """Merge keys whose slugify() already equals the target's own bare id
    slug -- ids that were renamed into the merged form, so V0 gets them for
    free regardless of any alias-closure or phonetic cleverness."""

    return sum(1 for n, c in merge.items() if slugify(n) == c.rsplit("/", 1)[-1])


# --- E1 sweep -----------------------------------------------------------------


def sweep(
    variant: str,
    gold_by_name: dict[str, str],
    live_names: set[str],
    never_merge: list[set[str]],
    split_names: list[str],
    ctx: dict,
    thresholds: list[float],
) -> list[dict]:
    per_name: dict[str, tuple[int | None, float]] = {}
    for name, gold in gold_by_name.items():
        scores = variant_scores_for_name(variant, name, ctx)
        ranked = sorted(scores, key=lambda c: (-scores[c], c))
        rank = ranked.index(gold) + 1 if gold in ranked else None
        per_name[name] = (rank, scores.get(gold, -1.0))

    pair_scores = []
    for group in never_merge:
        ids = sorted(group)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pair_scores.append(pair_score(variant, ids[i], ids[j], ctx))

    split_scores = {name: list(variant_scores_for_name(variant, name, ctx).values()) for name in split_names}

    def recall(names: list[str], t: float) -> tuple[float, float]:
        subset = [per_name[n] for n in names]
        if not subset:
            return 0.0, 0.0
        r1 = sum(1 for rank, gs in subset if rank == 1 and gs >= t) / len(subset)
        r3 = sum(1 for rank, gs in subset if rank is not None and rank <= 3 and gs >= t) / len(subset)
        return r1, r3

    stale_names = [n for n in gold_by_name if n not in live_names]
    all_names = list(gold_by_name)
    rows = []
    for t in thresholds:
        live_r1, live_r3 = recall(sorted(live_names), t)
        stale_r1, stale_r3 = recall(stale_names, t)
        all_r1, all_r3 = recall(all_names, t)
        false_links = sum(1 for s in pair_scores if s >= t)
        split_violations = sum(1 for vals in split_scores.values() if sum(1 for v in vals if v >= t) == 1)
        rows.append({
            "threshold": t,
            "live_r1": live_r1, "live_r3": live_r3,
            "stale_r1": stale_r1, "stale_r3": stale_r3,
            "all_r1": all_r1, "all_r3": all_r3,
            "false_links": false_links,
            "split_violations": split_violations,
        })
    return rows


def operating_points(rows: list[dict]) -> tuple[float | None, float | None]:
    zero_fl = [r["threshold"] for r in rows if r["false_links"] == 0]
    ge90 = [r["threshold"] for r in rows if r["live_r3"] >= 0.90]
    return (max(zero_fl) if zero_fl else None, min(ge90) if ge90 else None)


def sample_unruled_links(
    ctx: dict,
    merge: dict[str, str],
    splits: dict[tuple[str, str], str],
    variant: str,
    threshold: float,
    n: int = 30,
    seed: int = 0,
) -> list[tuple[str, str, float]]:
    split_name_set = {name for name, _ in splits}
    names = sorted({n.lower() for n in all_extracted_names()} - set(merge) - split_name_set)
    proposals = []
    for name in names:
        scores = variant_scores_for_name(variant, name, ctx)
        if not scores:
            continue
        best_cid = max(scores, key=lambda c: (scores[c], c))
        if scores[best_cid] >= threshold:
            proposals.append((name, best_cid, scores[best_cid]))
    return random.Random(seed).sample(proposals, min(n, len(proposals)))


# --- E2: generic-noun parent heuristic --------------------------------------


def predict_parent(
    session: str,
    cache_dir: Path,
    name_to_concept: dict[str, str],
    mention_counts: dict[str, int],
) -> str | None:
    session_dir = next((p for p in sorted(cache_dir.iterdir()) if p.name.startswith(session + "_")), None)
    if session_dir is None:
        return None
    candidates: list[str] = []
    for f in session_dir.glob("*.json"):
        try:
            blob = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for ent in blob.get("extraction", {}).get("entities", []):
            if ent.get("type") != "Location":
                continue
            cid = name_to_concept.get(str(ent.get("name", "")).strip().lower())
            if cid:
                candidates.append(cid)
    if not candidates:
        return None
    # sorted() first so a mention_count tie breaks on concept_id, not on
    # Python's hash-randomized set iteration order (which made this
    # non-deterministic across runs before this fix).
    return max(sorted(set(candidates)), key=lambda c: mention_counts.get(c, 0))


def evaluate_e2(gold_parents: dict[tuple[str, str], str], cache_dir: Path, entities: list[dict]) -> list[tuple]:
    name_to_concept: dict[str, str] = {}
    mention_counts: dict[str, int] = {}
    for e in entities:
        cid = str(e.get("concept_id", "")).strip()
        mention_counts[cid] = e.get("mention_count", 0)
        if not cid.startswith("locations/"):
            continue  # the extraction's own type tag already says Location;
            # matching it via an alias shared with a non-Location concept
            # would silently propose the wrong parent (e.g. an Event).
        for n in [e.get("canonical_name", ""), *(e.get("aliases") or [])]:
            n = str(n).strip().lower()
            if n:
                name_to_concept.setdefault(n, cid)

    results = []
    for (name, session), gold in sorted(gold_parents.items()):
        pred = predict_parent(session, cache_dir, name_to_concept, mention_counts)
        results.append((name, session, gold, pred, pred == gold))
    return results


def main() -> int:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()

    gt = load_ground_truth()
    merge, entities, candidate_ids = gt["merge"], gt["entities"], gt["candidate_ids"]
    never_merge, splits = gt["never_merge"], gt["splits"]
    live, stale = live_stale_split(merge)
    trivial = trivial_positive_count(merge)
    split_names = sorted({name for name, _ in splits})

    print(f"commit: {head or '(not a git checkout)'}")
    print(
        f"merge: {len(merge)} rules ({len(live)} live, {len(stale)} stale, "
        f"{trivial} trivial -- slugify(name) already == target slug)"
    )
    print(f"never_merge: {len(never_merge)} groups")
    print(f"split: {len(splits)} entries / {len(split_names)} distinct names")
    print(f"candidates: {len(candidate_ids)} entities (no retired:, no type filter -- "
          "a raw extracted name carries no reliable type)")
    print()

    ctx = build_context(candidate_ids, entities)
    live_names = set(live)

    all_rows: dict[str, list[dict]] = {}
    for variant in VARIANTS:
        rows = sweep(variant, merge, live_names, never_merge, split_names, ctx, THRESHOLDS)
        all_rows[variant] = rows
        print(f"=== {variant} ===")
        header = (
            f"{'t':>5} {'live@1':>7} {'live@3':>7} {'stale@1':>8} "
            f"{'stale@3':>8} {'all@1':>6} {'all@3':>6} "
            f"{'false':>6} {'splitviol':>9}"
        )
        print(header)
        for r in rows:
            print(
                f"{r['threshold']:5.2f} {r['live_r1']:7.3f} {r['live_r3']:7.3f} "
                f"{r['stale_r1']:8.3f} {r['stale_r3']:8.3f} {r['all_r1']:6.3f} "
                f"{r['all_r3']:6.3f} {r['false_links']:6d} {r['split_violations']:9d}"
            )
        best_fl, lowest90 = operating_points(rows)
        print(f"operating points -- highest t, 0 false_links: {best_fl}; "
              f"lowest t, live recall@3 >= 0.90: {lowest90}")
        print()

    print("=== unruled proposed links (observation, not a metric) ===")
    best_fl_v1 = operating_points(all_rows["V1"])[0] or max(THRESHOLDS)
    sample = sample_unruled_links(ctx, merge, splits, "V1", best_fl_v1)
    print(f"V1 @ t={best_fl_v1:.2f}, sampled {len(sample)} of the proposed links no rule covers:")
    for name, cid, score in sample:
        print(f"  {name!r} -> {cid}  ({score:.3f})")
    print()

    print("=== E2: generic-noun parent heuristic ===")
    print(f"gold: {len(GOLD_PARENTS)} rows; dropped {len(DROPPED)}:")
    for name, session, reason in DROPPED:
        print(f"  {name!r}@{session}: {reason}")
    e2 = evaluate_e2(GOLD_PARENTS, CACHE_EXTRACT, entities)
    for name, session, gold, pred, ok in e2:
        reason = ""
        if not ok:
            if gold.split("/")[0] in ("characters", "npcs"):
                reason = "  (gold parent is a person, not a place)"
            elif pred is None:
                reason = "  (no location found in session)"
            else:
                reason = "  (session's dominant location differs from gold)"
        mark = "OK  " if ok else "MISS"
        print(f"  {mark} {name!r}@{session}: predicted={pred} gold={gold}{reason}")
    correct = sum(1 for *_, ok in e2 if ok)
    print(f"accuracy@1: {correct}/{len(e2)} = {correct / len(e2):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
