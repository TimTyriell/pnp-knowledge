"""Offline tests: prompt assembly + grounding contract (no HTTP, no LLM)."""

from __future__ import annotations

import httpx
from summary import (
    build_messages,
    fetch_open_threads,
    fetch_sessions,
    render_threads,
    sources_footer,
)


def _session(concept: str, title: str, body: str, quality: str = "hoch") -> dict:
    return {
        "concept": concept,
        "frontmatter": {
            "title": title,
            "quality": quality,
            "resource": f"https://youtu.be/{concept[-1]}",
        },
        "body_md": body,
    }


_SESSIONS = [
    _session("sessions/2025-09-30", "Session 25", "Die Gruppe erreicht die Mine."),
    _session("sessions/2025-10-07", "Session 26", "Kampf gegen den Golem.", "mittel"),
]


def test_messages_contain_only_kb_content():
    messages = build_messages(_SESSIONS, outlook_context=None)
    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "Die Gruppe erreicht die Mine." in user
    assert "Kampf gegen den Golem." in user
    assert "Qualität: mittel" in user
    assert "Ausblick" not in messages[0]["content"]


def test_outlook_context_is_in_prompt_only_when_given():
    messages = build_messages(_SESSIONS, outlook_context="Hinterhalt am Pass")
    assert "Hinterhalt am Pass" in messages[0]["content"]
    assert "## Ausblick" in messages[0]["content"]


def test_sources_footer_lists_every_session_and_as_of():
    footer = sources_footer(_SESSIONS, as_of="s26")
    assert "sessions/2025-09-30 @ s26" in footer
    assert "sessions/2025-10-07 @ s26" in footer
    assert footer.count("- sessions/") == len(_SESSIONS)


# --- T9: open threads from the KB -------------------------------------------

_THREAD_FM = {
    "title": "Evakuierung des Halblingshofs",
    "kind": "quest",
    "opened": "S1-02-B",
    "teams": ["B"],
}


def test_threads_go_to_the_model_and_system_prompt_writes_no_own_list():
    messages = build_messages(_SESSIONS, None, threads=[_THREAD_FM])
    assert "Evakuierung des Halblingshofs" in messages[1]["content"]
    assert "Offene Fäden laut Wissensbasis" in messages[1]["content"]
    assert "Stichpunktliste" not in messages[0]["content"]
    assert "KEINE eigene" in messages[0]["content"]


def test_sources_footer_lists_thread_concepts_too():
    footer = sources_footer(_SESSIONS, None, threads=[{"concept": "threads/evak"}])
    assert footer.endswith("- threads/evak")


def test_no_threads_leaves_the_user_content_unchanged():
    assert build_messages(_SESSIONS, None, threads=[]) == build_messages(_SESSIONS, None)


def test_render_threads_labels_kinds_in_german_and_is_empty_for_none():
    text = render_threads(
        [
            {"title": "Evakuierung", "kind": "quest", "opened": "S1-02-B", "concept": "threads/evak"},
            {"title": "Der Schlüssel", "kind": "mystery", "opened": None, "concept": "threads/schluessel"},
        ]
    )
    assert text.startswith("## Offene Fäden")
    assert "- Auftrag: Evakuierung (seit S1-02-B) — threads/evak" in text
    assert "- Rätsel: Der Schlüssel — threads/schluessel" in text
    assert render_threads([]) == ""


def _kb_handler(threads_rows, thread_details, sessions=None):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/concepts" and request.url.params.get("type") == "Thread":
            return httpx.Response(200, json=threads_rows)
        if path == "/concepts" and request.url.params.get("type") == "Session":
            return httpx.Response(200, json=[{"concept": s} for s, _ in sessions or []])
        if path.startswith("/concepts/"):
            cid = path[len("/concepts/"):]
            if cid in thread_details:
                return httpx.Response(200, json={"concept": cid, "frontmatter": thread_details[cid], "body_md": ""})
            for s, fm in sessions or []:
                if s == cid:
                    return httpx.Response(200, json={"concept": s, "frontmatter": fm, "body_md": f"Body {s}"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


_ROWS = [
    {"concept": "threads/evak", "kind": "quest", "thread_status": "open", "title": "Evakuierung"},
    {"concept": "threads/rotunas", "kind": "mystery", "thread_status": "open", "title": "Rotunas"},
]
_DETAILS = {
    "threads/evak": {"title": "Evakuierung", "kind": "quest", "opened": "S1-02-B", "teams": ["B"]},
    "threads/rotunas": {"title": "Rotunas", "kind": "mystery", "opened": "S1-01-A", "teams": ["A"]},
}


def test_fetch_open_threads_sorts_by_opened_and_keeps_all_without_team():
    transport = _kb_handler(_ROWS, _DETAILS)
    threads = fetch_open_threads("http://kb", None, None, transport=transport)
    assert [t["title"] for t in threads] == ["Rotunas", "Evakuierung"]


def test_fetch_open_threads_team_filter_drops_other_tables():
    transport = _kb_handler(_ROWS, _DETAILS)
    threads = fetch_open_threads("http://kb", None, "B", transport=transport)
    assert [t["title"] for t in threads] == ["Evakuierung"]


def test_fetch_open_threads_empty_kb_listing_is_empty_list():
    assert fetch_open_threads("http://kb", None, None, transport=_kb_handler([], {})) == []


def test_fetch_sessions_team_filter_applies_before_count():
    sessions = [
        ("sessions/2025-09-30", {"title": "A1", "team_letter": "A"}),
        ("sessions/2025-10-07", {"title": "B1", "team_letter": "B"}),
        ("sessions/2025-10-14", {"title": "A2", "team_letter": "A"}),
    ]
    transport = _kb_handler([], {}, sessions=sessions)
    got = fetch_sessions("http://kb", 1, None, team="B", transport=transport)
    assert [s["concept"] for s in got] == ["sessions/2025-10-07"]
