"""Diagnose dead entity_rules.yaml rules left by the 2026-08 mass-rename.

Read-only, no LLM calls: everything comes from entity_registry.yaml,
entity_rules.yaml, the live bundle, and the (already cached) extract JSON.
A rule is "dead" if its target concept id no longer exists in the bundle.
Within that:

- inert: the rule's source text isn't extracted anywhere any more either,
  so the rule can never fire again -- safe to delete.
- needs a decision: the source text (or, for never_merge/important, the
  rule itself) is still live -- something a human has to resolve, because
  the correct successor concept isn't determinable from text alone.

    python rules_doctor.py
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent  # services/kb
KNOWLEDGE = ROOT.parent.parent / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
RULES = KNOWLEDGE / "entity_rules.yaml"
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"
CACHE_EXTRACT = ROOT / ".cache" / "extract"


def bundle_concepts(bundle: Path) -> set[str]:
    return {
        str(p.relative_to(bundle).with_suffix("")).replace("\\", "/")
        for p in bundle.rglob("*.md")
        if p.name not in ("index.md", "log.md")
    }


def known_names(reg: dict) -> set[str]:
    """Every canonical_name/alias currently attached to a live concept."""

    known: set[str] = set()
    for e in reg.get("entities") or []:
        known.add(str(e.get("canonical_name", "")).strip().lower())
        known |= {str(a).strip().lower() for a in (e.get("aliases") or [])}
    known.discard("")
    return known


def name_to_concept(reg: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in reg.get("entities") or []:
        cid = str(e.get("concept_id", "")).strip()
        if not cid:
            continue
        for n in [e.get("canonical_name", ""), *(e.get("aliases") or [])]:
            n = str(n).strip().lower()
            if n:
                out.setdefault(n, cid)
    return out


def session_names(session_key: str, cache_dir: Path) -> set[str]:
    """Names in that session's cached extraction (no cache-key check --
    freshness doesn't matter for a diagnostic, only current content)."""

    matches = sorted(cache_dir.glob(f"{session_key}*.json"))
    names: set[str] = set()
    for path in matches:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for entity in blob.get("extraction", {}).get("entities", []):
            n = str(entity.get("name", "")).strip().lower()
            if n:
                names.add(n)
    return names


def classify(
    registry_path: Path = REGISTRY,
    rules_path: Path = RULES,
    bundle_dir: Path = BUNDLE,
    cache_dir: Path = CACHE_EXTRACT,
) -> dict[str, object]:
    """Return the classification without printing -- used by the test."""

    reg = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {} if registry_path.exists() else {}
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {} if rules_path.exists() else {}
    concepts = bundle_concepts(bundle_dir) if bundle_dir.exists() else set()
    known = known_names(reg)
    byname = name_to_concept(reg)

    merge = {**(reg.get("merge") or {}), **(rules.get("merge") or {})}
    dead_merge = {n: c for n, c in merge.items() if c not in concepts}
    inert_merge = {n: c for n, c in dead_merge.items() if n.strip().lower() not in known}
    live_merge = {n: c for n, c in dead_merge.items() if n not in inert_merge}

    cn = rules.get("canonical_name") or {}
    dead_cn = {c: v for c, v in cn.items() if c not in concepts}
    cn_successors = {
        c: byname[str(v).strip().lower()]
        for c, v in dead_cn.items()
        if str(v).strip().lower() in byname
    }
    inert_cn = {c: v for c, v in dead_cn.items() if c not in cn_successors}

    splits = rules.get("split") or []
    dead_split = [r for r in splits if str(r.get("concept_id", "")).strip() not in concepts]
    inert_split = [r for r in dead_split if str(r.get("name", "")).strip().lower() not in known]
    live_split = [r for r in dead_split if r not in inert_split]

    nm = rules.get("never_merge") or []
    dead_nm = [g for g in nm if sum(c in concepts for c in g) < 2]

    important = rules.get("important") or []
    dead_important = [c for c in important if c not in concepts]

    return {
        "concepts": concepts,
        "merge": {"total": len(merge), "dead": dead_merge, "inert": inert_merge, "live": live_merge},
        "canonical_name": {
            "total": len(cn), "dead": dead_cn, "successors": cn_successors, "inert": inert_cn,
        },
        "split": {"total": len(splits), "dead": dead_split, "inert": inert_split, "live": live_split},
        "never_merge": {"total": len(nm), "dead": dead_nm},
        "important": {"total": len(important), "dead": dead_important},
    }


def main() -> int:
    result = classify()
    print(f"bundle concepts: {len(result['concepts'])}\n")

    m = result["merge"]
    print(f"merge: {m['total']} total, {len(m['dead'])} dead "
          f"({len(m['inert'])} inert, {len(m['live'])} need a decision)")
    for name, cid in sorted(m["live"].items()):
        print(f"   NEEDS DECISION  {name!r} -> {cid}  (source name still extracted)")

    cn = result["canonical_name"]
    print(f"\ncanonical_name: {cn['total']} total, {len(cn['dead'])} dead "
          f"({len(cn['inert'])} inert, {len(cn['successors'])} need a decision)")
    for cid, successor in sorted(cn["successors"].items()):
        print(f"   NEEDS DECISION  {cid} (pin {cn['dead'][cid]!r}) -> propose {successor}")

    sp = result["split"]
    print(f"\nsplit: {sp['total']} total, {len(sp['dead'])} dead "
          f"({len(sp['inert'])} inert, {len(sp['live'])} need a decision)")
    for r in sp["live"]:
        session = str(r.get("session", "")).strip()
        current = session_names(session, CACHE_EXTRACT)
        print(f"   NEEDS DECISION  {r['name']!r}@{session} -> {r['concept_id']} (dead)"
              + (f"; session currently extracts: {sorted(current)}" if current
                 else "; no cached extraction found for that session"))

    nm = result["never_merge"]
    print(f"\nnever_merge: {nm['total']} total, {len(nm['dead'])} dead "
          "(always needs a decision -- a ruling that two things are distinct "
          "just went silently unenforced)")
    for g in nm["dead"]:
        present = [c for c in g if c in result["concepts"]]
        print(f"   NEEDS DECISION  {g} (still present: {present})")

    imp = result["important"]
    print(f"\nimportant: {imp['total']} total, {len(imp['dead'])} dead "
          "(always needs a decision -- no name signal to auto-resolve)")
    for cid in imp["dead"]:
        print(f"   NEEDS DECISION  {cid}")

    total_dead = (
        len(m["dead"]) + len(cn["dead"]) + len(sp["dead"]) + len(nm["dead"]) + len(imp["dead"])
    )
    total_inert = len(m["inert"]) + len(cn["inert"]) + len(sp["inert"])
    print(f"\ntotal dead: {total_dead}  |  inert (safe to delete): {total_inert}  "
          f"|  needs a decision: {total_dead - total_inert}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
