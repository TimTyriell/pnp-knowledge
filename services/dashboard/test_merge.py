"""Plain-assert tests for merge.py — pytest-collectible, no fixtures/mocks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import merge

NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def test_load_local_status_missing():
    missing = Path("does/not/exist/status.json")
    result = merge.load_local_status(missing, NOW)
    assert result["state"] == "missing"


def test_load_local_status_corrupt():
    scratch = Path(__file__).parent / "_test_scratch"
    scratch.mkdir(exist_ok=True)
    bad = scratch / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = merge.load_local_status(bad, NOW)
    assert result["state"] == "missing"
    bad.unlink()
    scratch.rmdir()


def test_staleness_ok_vs_stale():
    fresh = {"generated_at": _iso(NOW - timedelta(hours=1))}
    stale = {"generated_at": _iso(NOW - timedelta(hours=72))}
    assert merge._with_state(dict(fresh), NOW)["state"] == "ok"
    assert merge._with_state(dict(stale), NOW)["state"] == "stale"


def test_staleness_boundary():
    just_inside = {"generated_at": _iso(NOW - timedelta(hours=47, minutes=59))}
    just_outside = {"generated_at": _iso(NOW - timedelta(hours=48, minutes=1))}
    assert merge._with_state(dict(just_inside), NOW)["state"] == "ok"
    assert merge._with_state(dict(just_outside), NOW)["state"] == "stale"


def test_funnel_join_by_video_id():
    crawl = {"items": [
        {"video_id": "abc123", "video_date": "2026-01-01", "stem": "2026-01-01_Team-A_abc123",
         "downloaded": True, "transcribed": True, "mapped": True, "exported": True},
    ]}
    kb = {"items": [
        {"video_id": "abc123", "date": "2026-01-01", "committed_at": "2026-01-05T00:00:00+00:00"},
    ]}
    rows = merge.build_funnel(crawl, kb)
    assert len(rows) == 1
    row = rows[0]
    assert row["exported"] is True
    assert row["in_bundle"] is True
    assert row["lead_time_days"] == 4.0


def test_funnel_fallback_to_date_when_no_video_id():
    crawl = {"items": [{"video_id": None, "video_date": "2026-02-02", "stem": "s1",
                         "downloaded": True, "transcribed": False, "mapped": False, "exported": False}]}
    kb = {"items": [{"video_id": None, "date": "2026-02-02", "committed_at": None}]}
    rows = merge.build_funnel(crawl, kb)
    assert len(rows) == 1
    assert rows[0]["in_bundle"] is True


def test_funnel_session_only_on_one_side_still_shown():
    crawl = {"items": [{"video_id": "onlycrawl", "video_date": "2026-03-01", "stem": "s",
                         "downloaded": True, "transcribed": True, "mapped": True, "exported": True}]}
    kb = {"items": []}
    rows = merge.build_funnel(crawl, kb)
    assert len(rows) == 1
    assert rows[0]["in_bundle"] is False
    assert rows[0]["exported"] is True

    crawl2 = {"items": []}
    kb2 = {"items": [{"video_id": "onlykb", "date": "2026-03-02", "committed_at": "2026-03-02T00:00:00Z"}]}
    rows2 = merge.build_funnel(crawl2, kb2)
    assert len(rows2) == 1
    assert rows2[0]["downloaded"] is None
    assert rows2[0]["in_bundle"] is True


def test_funnel_attaches_episode_by_video_id():
    crawl = {"items": [
        {"video_id": "abc123", "video_date": "2026-01-01", "stem": "s", "downloaded": True},
        {"video_id": "unknown", "video_date": "2026-01-02", "stem": "s2", "downloaded": True},
    ]}
    episodes = merge.episodes_by_video(
        {"episodes": [{"video_id": "abc123", "id": "S1-01-A", "title": "Funken"}]}
    )
    rows = {r["video_id"]: r for r in merge.build_funnel(crawl, {}, episodes)}
    assert rows["abc123"]["episode"] == "S1-01-A"
    assert rows["abc123"]["episode_title"] == "Funken"
    # An episode nobody listed yet must not break the row.
    assert rows["unknown"]["episode"] is None


def test_load_episodes_missing_and_int_season_key():
    result = merge.load_episodes(Path("does/not/exist/episodes.yaml"))
    assert result["episodes"] == [] and result["error"]

    scratch = Path(__file__).parent / "_test_scratch"
    scratch.mkdir(exist_ok=True)
    path = scratch / "episodes.yaml"
    # Season 1 unquoted: YAML hands back an int, the episode says "1".
    path.write_text("seasons:\n  1:\n    label: Staffel 1\nepisodes: []\n", encoding="utf-8")
    assert list(merge.load_episodes(path)["seasons"]) == ["1"]
    path.unlink()


def test_inbox_concatenates_and_tags_service():
    crawl = {"actions": [{"kind": "unresolved_speaker", "label": "SPEAKER_02", "ref": "s1"}]}
    kb = {"actions": [{"kind": "conflict", "label": "X", "ref": "c1.md"}]}
    export = {"actions": []}
    inbox = merge.build_inbox(crawl, kb, export)
    assert len(inbox) == 2
    assert {a["service"] for a in inbox} == {"pnp-crawl", "pnp-kb"}
    assert all("kind" in a and "ref" in a for a in inbox)


if __name__ == "__main__":
    import sys

    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
    sys.exit(1 if failures else 0)
