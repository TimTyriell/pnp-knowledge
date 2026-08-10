"""Episode lookup and citation relabelling (pnp_okf.episodes)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from pnp_okf.episodes import Episodes, citation_labels, relabel_citations, video_id

URL_A = "https://www.youtube.com/watch?v=umGyKLkefJI"
URL_B = "https://www.youtube.com/watch?v=0HyPHao8s_k"
URL_UNKNOWN = "https://www.youtube.com/watch?v=zzzzzzzzzzz"

EPISODES = Episodes(
    [
        {"video_id": "umGyKLkefJI", "id": "S1-01-A", "title": "Aufbruch", "season": "1"},
        {"video_id": "0HyPHao8s_k", "id": "S1-03-B", "title": "", "season": "1"},
    ]
)


def test_video_id_from_url():
    assert video_id(URL_A) == "umGyKLkefJI"
    assert video_id("https://youtube.com/watch?list=x&v=abc123") == "abc123"
    assert video_id("") is None


def test_lookup_by_url():
    assert EPISODES.id_for_url(URL_A) == "S1-01-A"
    assert EPISODES.id_for_url(URL_UNKNOWN) is None


def test_labels_are_all_or_nothing():
    assert citation_labels([URL_A, URL_B], EPISODES) == ["S1-01-A", "S1-03-B"]
    # One unknown session must not leave a body half numeric, half episode id.
    assert citation_labels([URL_A, URL_UNKNOWN], EPISODES) is None
    assert citation_labels([], EPISODES) is None


def test_repeated_session_gets_a_suffix():
    labels = citation_labels([URL_A, URL_B, URL_A], EPISODES)
    assert labels == ["S1-01-Aa", "S1-03-B", "S1-01-Ab"]


def test_relabel_inline_refs_and_belege_list():
    body = textwrap.dedent(
        """\
        Belorus zog ab [1]. Später kehrte er zurück [1, 2].

        # Belege

        [1] Session 2026-07-29 @ 00:10:00 (https://x)
        [2] Session 2026-08-06 @ 00:20:00 (https://y)
        """
    )
    out = relabel_citations(body, ["S1-01-A", "S1-03-B"])
    assert "[S1-01-A]." in out
    assert "[S1-01-A, S1-03-B]." in out
    assert "[S1-01-A] Session 2026-07-29 @ 00:10:00 (https://x)" in out
    assert "[1]" not in out


def test_relabel_leaves_markdown_links_alone():
    body = "Siehe [1](/npcs/belorus.md) und Beleg [1]."
    out = relabel_citations(body, ["P-08"])
    assert out == "Siehe [1](/npcs/belorus.md) und Beleg [P-08]."


def test_relabel_keeps_numbers_it_has_no_label_for():
    # The model occasionally cites past the end of its evidence list.
    assert relabel_citations("Fakt [3].", ["P-01"]) == "Fakt [3]."


def test_relabel_handles_the_brief_tier_list_style():
    body = "Text [1].\n\n# Belege\n\n1. Session 2026-07-29 @ 00:10:00 (https://x)"
    out = relabel_citations(body, ["S1-01-A"])
    assert "[S1-01-A] Session 2026-07-29" in out


def test_missing_file_is_not_fatal():
    episodes = Episodes.load(Path("does/not/exist/episodes.yaml"))
    assert len(episodes) == 0
    assert episodes.id_for_url(URL_A) is None


def test_load_reads_the_real_campaign_list():
    path = Path(__file__).resolve().parents[3] / "knowledge" / "episodes.yaml"
    if not path.is_file():  # a free-standing checkout of services/kb
        return
    episodes = Episodes.load(path)
    assert len(episodes) >= 61
    assert episodes.id_for_url("https://www.youtube.com/watch?v=ROCKGeeRUFw") == "P-01"
