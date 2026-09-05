"""Glossar read model — joins entity_registry.yaml + entity_rules.yaml with
literal name-occurrence counts over the pnp-crawl transcripts.

Pure functions + two loaders, same style as merge.py. Nothing here writes
anything; that's rules_edit.py.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC
from pathlib import Path
from typing import Any

import yaml

# \w is unicode-aware in Python's re, so ä/ö/ü/ß are word chars. Apostrophes
# and hyphens split a name on both sides ("Vhar'Zul" -> ("vhar","zul")), so a
# transcript spelling "Vhar Zul" still matches — deliberate, not a bug.
TOKEN = re.compile(r"\w+", re.UNICODE)


def name_key(name: str) -> tuple[str, ...]:
    return tuple(TOKEN.findall(name.lower()))


def load_registry(registry_path: Path) -> list[dict[str, Any]]:
    if not registry_path.is_file():
        return []
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return list(data.get("entities") or [])


def load_rules(rules_path: Path) -> dict[str, Any]:
    if not rules_path.is_file():
        return {}
    return yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}


def entity_name_sources(
    entities: list[dict[str, Any]], rules: dict[str, Any]
) -> dict[str, list[tuple[str, str]]]:
    """concept_id -> [(name, source)], source in canonical|merge|registry.

    Precedence when the same name_key would appear twice: canonical > merge >
    registry — this controls which "source" tag the UI shows, which in turn
    controls whether deleting that alias needs the un-fold warning.
    """
    merge_by_cid: dict[str, list[str]] = {}
    for name, cid in (rules.get("merge") or {}).items():
        merge_by_cid.setdefault(str(cid).strip(), []).append(str(name).strip())

    out: dict[str, list[tuple[str, str]]] = {}
    for entry in entities:
        cid = str(entry.get("concept_id", "")).strip()
        if not cid:
            continue
        seen: set[tuple[str, ...]] = set()
        names: list[tuple[str, str]] = []

        canonical = str(entry.get("canonical_name", "")).strip()
        if canonical:
            names.append((canonical, "canonical"))
            seen.add(name_key(canonical))

        for name in merge_by_cid.get(cid, []):
            k = name_key(name)
            if name and k not in seen:
                names.append((name, "merge"))
                seen.add(k)

        for name in entry.get("aliases") or []:
            name = str(name).strip()
            k = name_key(name)
            if name and k not in seen:
                names.append((name, "registry"))
                seen.add(k)

        out[cid] = names
    return out


def _transcript_fingerprint(crawl_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not crawl_dir.is_dir():
        return ()
    return tuple(
        sorted(
            (p.name, p.stat().st_mtime_ns, p.stat().st_size)
            for p in crawl_dir.glob("*.json")
        )
    )


def count_names(crawl_dir: Path, keys: set[tuple[str, ...]]) -> Counter[tuple[str, ...]]:
    """Literal, case-insensitive, whole-word occurrence count per name_key.

    One pass per file: tokenize once, then for every n-gram length present in
    `keys` slide a window over the token list and look the n-gram up in the
    key set. Cheaper than one regex per name (1594 names x 61 files) because
    the transcripts are only tokenized once total.
    """
    counts: Counter[tuple[str, ...]] = Counter()
    if not keys or not crawl_dir.is_dir():
        return counts
    lengths = sorted({len(k) for k in keys})

    for path in crawl_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        text = " ".join(seg.get("text", "") for seg in data.get("segments") or [])
        toks = TOKEN.findall(text.lower())
        for n in lengths:
            if n > len(toks):
                continue
            for i in range(len(toks) - n + 1):
                gram = tuple(toks[i : i + n])
                if gram in keys:
                    counts[gram] += 1
    return counts


_CACHE: dict[str, Any] = {"tfp": None, "nfp": None, "counts": None}


def _cached_counts(crawl_dir: Path, keys: set[tuple[str, ...]]) -> Counter[tuple[str, ...]]:
    tfp = _transcript_fingerprint(crawl_dir)
    nfp = hash(frozenset(keys))
    if _CACHE["tfp"] != tfp or _CACHE["nfp"] != nfp:
        _CACHE["counts"] = count_names(crawl_dir, keys)
        _CACHE["tfp"] = tfp
        _CACHE["nfp"] = nfp
    return _CACHE["counts"]


def build(knowledge_dir: Path, crawl_dir: Path) -> dict[str, Any]:
    registry_path = knowledge_dir / "entity_registry.yaml"
    rules_path = knowledge_dir / "entity_rules.yaml"

    entities = load_registry(registry_path)
    rules = load_rules(rules_path)
    sources = entity_name_sources(entities, rules)

    keys: set[tuple[str, ...]] = set()
    for names in sources.values():
        for name, _src in names:
            k = name_key(name)
            if k:
                keys.add(k)
    counts = _cached_counts(crawl_dir / "transcripts_final", keys)

    types: set[str] = set()
    out_entities = []
    for entry in entities:
        cid = str(entry.get("concept_id", "")).strip()
        if not cid:
            continue
        etype = str(entry.get("type", "")).strip()
        types.add(etype)
        aliases = []
        total = 0
        for name, src in sources.get(cid, []):
            c = counts.get(name_key(name), 0)
            total += c
            aliases.append({"name": name, "count": c, "source": src})
        out_entities.append(
            {
                "concept_id": cid,
                "type": etype,
                "canonical_name": str(entry.get("canonical_name", "")).strip(),
                "pinned": cid in (rules.get("canonical_name") or {}),
                "important": bool(entry.get("important")),
                "mention_count": int(entry.get("mention_count", 0)),
                "total_count": total,
                "aliases": aliases,
            }
        )

    stale = False
    rules_mtime = registry_mtime = None
    if rules_path.is_file():
        rules_mtime = rules_path.stat().st_mtime
    if registry_path.is_file():
        registry_mtime = registry_path.stat().st_mtime
    if rules_mtime is not None and registry_mtime is not None:
        stale = rules_mtime > registry_mtime

    def _iso(ts: float | None) -> str | None:
        if ts is None:
            return None
        from datetime import datetime

        return datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    return {
        "stale": stale,
        "rules_mtime": _iso(rules_mtime),
        "registry_mtime": _iso(registry_mtime),
        "types": sorted(types),
        "entities": out_entities,
    }
