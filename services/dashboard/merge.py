"""Pure merge/join logic for the pnp-dashboard.

Reads the three producer status snapshots (two local files, one live HTTP
call) and folds them into the shape the frontend renders. No I/O side
effects beyond the explicit fetch/load calls — everything else here is a
pure function, so it's testable without a filesystem or network.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

STALE_AFTER_H = 48


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _with_state(status: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Annotate an already-parsed status snapshot with ok/stale."""
    generated_at = _parse_iso(status.get("generated_at"))
    if generated_at is None:
        status["state"] = "ok"
        return status
    age_h = (now - generated_at).total_seconds() / 3600
    status["state"] = "stale" if age_h > STALE_AFTER_H else "ok"
    return status


def load_local_status(path: Path, now: datetime | None = None) -> dict[str, Any]:
    """Read a producer's status.json, tolerating a missing or corrupt file."""
    now = now or _now()
    if not path.is_file():
        return {"state": "missing", "error": f"{path} does not exist"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"state": "missing", "error": str(exc)}
    return _with_state(data, now)


def fetch_kb_status(kb_url: str, now: datetime | None = None, timeout: float = 3.0) -> dict[str, Any]:
    """GET <kb_url>/status, tolerating the KB API being offline."""
    now = now or _now()
    try:
        resp = httpx.get(f"{kb_url.rstrip('/')}/status", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        return {"state": "offline", "error": str(exc)}
    return _with_state(data, now)


def _video_key(row: dict[str, Any]) -> str | None:
    vid = row.get("video_id")
    if vid:
        return f"id:{vid}"
    date = row.get("video_date") or row.get("date")
    return f"date:{date}" if date else None


def _lead_time_days(video_date: str | None, committed_at: str | None) -> float | None:
    d0 = _parse_iso(video_date + "T00:00:00Z") if video_date else None
    d1 = _parse_iso(committed_at)
    if d0 is None or d1 is None:
        return None
    return round((d1 - d0).total_seconds() / 86400, 1)


def build_funnel(crawl: dict[str, Any], kb: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per session, joined across crawl and kb by video_id (date fallback).

    Sessions present on only one side still get a row, with the missing
    side's fields left null — the gap itself is the point of this view.
    """
    crawl_items = crawl.get("items") or []
    kb_items = kb.get("items") or []

    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for row in crawl_items:
        key = _video_key(row)
        if key is None:
            continue
        by_key[key] = {
            "video_id": row.get("video_id"),
            "video_date": row.get("video_date"),
            "stem": row.get("stem"),
            "downloaded": row.get("downloaded", False),
            "transcribed": row.get("transcribed", False),
            "mapped": row.get("mapped", False),
            "exported": row.get("exported", False),
            "in_bundle": False,
            "committed_at": None,
            "lead_time_days": None,
        }
        order.append(key)

    for row in kb_items:
        key = _video_key(row)
        if key is None:
            continue
        if key not in by_key:
            by_key[key] = {
                "video_id": row.get("video_id"),
                "video_date": row.get("date"),
                "stem": None,
                "downloaded": None,
                "transcribed": None,
                "mapped": None,
                "exported": None,
                "in_bundle": False,
                "committed_at": None,
                "lead_time_days": None,
            }
            order.append(key)
        entry = by_key[key]
        entry["in_bundle"] = True
        entry["committed_at"] = row.get("committed_at")
        entry["lead_time_days"] = _lead_time_days(entry.get("video_date"), row.get("committed_at"))

    return [by_key[k] for k in order]


def build_inbox(crawl: dict[str, Any], kb: dict[str, Any], export: dict[str, Any]) -> list[dict[str, Any]]:
    """Concatenate actions[] from all three producers. No interpretation —
    each service already decided what belongs in its own actions list."""
    inbox: list[dict[str, Any]] = []
    for source, status in (("pnp-crawl", crawl), ("pnp-kb", kb), ("pnp-export-data", export)):
        for action in status.get("actions") or []:
            inbox.append({"service": source, **action})
    return inbox


def build(crawl_status_path: Path, export_status_path: Path, kb_url: str) -> dict[str, Any]:
    now = _now()
    crawl = load_local_status(crawl_status_path, now)
    kb = fetch_kb_status(kb_url, now)
    export = load_local_status(export_status_path, now)
    return {
        "crawl": crawl,
        "kb": kb,
        "export": export,
        "funnel": build_funnel(crawl, kb),
        "inbox": build_inbox(crawl, kb, export),
    }
