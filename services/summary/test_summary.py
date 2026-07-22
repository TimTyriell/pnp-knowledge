"""Offline tests: prompt assembly + grounding contract (no HTTP, no LLM)."""

from __future__ import annotations

from summary import build_messages, sources_footer


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
