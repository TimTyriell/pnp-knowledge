"""The state pass runner: sequential, cached, and cheap to estimate (T5 §3.4-3.5)."""

import json
from dataclasses import replace

from pnp_okf.config import DeepSeekConfig
from pnp_okf.models import Segment, SessionTranscript
from pnp_okf.state import render_glossary, run_state, state_cache_key

GLOSS = [{"type": "NPC", "name": "Xenia", "aliases": []}]


class _SeqClient:
    """Fake OpenAI client: returns the canned payloads in order, records each call."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls: list[dict] = []
        chat = type("chat", (), {})()
        chat.completions = self
        self.chat = chat

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("m", (), {"content": json.dumps(self._payloads.pop(0))})()
        return type("c", (), {"choices": [type("ch", (), {"message": message})()]})()


def _cfg():
    return DeepSeekConfig(api_key="x", model="m", base_url="https://example.invalid")


def _transcript(session_id, date):
    segs = [Segment(start=i, end=i + 1, speaker="A", text=f"Satz {i}") for i in range(3)]
    return SessionTranscript(session_id=session_id, date=date,
                             url=f"https://example.invalid/{session_id}", segments=segs)


def _thread(thread_id="NEU", title="Evakuierung", status="open"):
    return {"thread_id": thread_id, "title": title, "kind": "quest", "status": status,
            "note": "n", "citation_ts": "00:01:00"}


def _state(threads=()):
    return {"threads": list(threads), "status_changes": [], "attitudes": []}


def _two_sessions():
    return [_transcript("s1", "2026-01-01"), _transcript("s2", "2026-01-08")]


def test_threads_carry_forward_to_the_next_session(tmp_path):
    client = _SeqClient([_state([_thread()]), _state()])
    run = run_state(_two_sessions(), _cfg(), tmp_path, GLOSS, client=client)
    assert run.called == 2
    # The second session's prompt lists the thread minted from the first.
    assert "threads/evakuierung" in client.calls[1]["messages"][1]["content"]


def test_second_run_over_the_same_cache_makes_no_calls(tmp_path):
    run_state(_two_sessions(), _cfg(), tmp_path, GLOSS, client=_SeqClient([_state([_thread()]), _state()]))
    client2 = _SeqClient([])  # any call would pop from an empty list and raise
    run = run_state(_two_sessions(), _cfg(), tmp_path, GLOSS, client=client2)
    assert run.cached == 2 and run.called == 0
    assert client2.calls == []


def test_estimate_on_an_empty_cache_calls_nothing(tmp_path):
    client = _SeqClient([])
    run = run_state(_two_sessions(), _cfg(), tmp_path, GLOSS, estimate=True, client=client)
    assert client.calls == []
    assert run.uncached_estimate == 2


def test_editing_an_early_session_uncaches_every_later_one(tmp_path):
    run_state(_two_sessions(), _cfg(), tmp_path, GLOSS, client=_SeqClient([_state([_thread()]), _state()]))
    # Rewrite session 1's cached output under its own key: its key is unchanged,
    # but the thread list session 2 was keyed on is now different.
    s1_blob = next((tmp_path / "state" / "s1").glob("*.json"))
    blob = json.loads(s1_blob.read_text(encoding="utf-8"))
    blob["state"] = _state([_thread(title="Anderer Titel")])
    s1_blob.write_text(json.dumps(blob), encoding="utf-8")

    run = run_state(_two_sessions(), _cfg(), tmp_path, GLOSS, estimate=True, client=_SeqClient([]))
    assert run.cached == 1
    assert run.uncached_estimate == 1


def test_cache_key_changes_when_the_glossary_changes():
    t = _transcript("s1", "2026-01-01")
    cfg = _cfg()
    k1 = state_cache_key(t, cfg, render_glossary(GLOSS), "(keine offenen Fäden)")
    other = render_glossary([{"type": "NPC", "name": "Brim", "aliases": []}])
    k2 = state_cache_key(t, cfg, other, "(keine offenen Fäden)")
    assert k1 != k2


def test_state_tier_uses_the_state_model():
    cfg = replace(_cfg(), state_model="deepseek-v4-pro")
    assert cfg.for_tier("state").model == "deepseek-v4-pro"
