"""An extraction with a recap but no entities is a failure, not a result.

One session came back that way in the v5 run: the model spent its budget on
the prose and returned ``entities: []``. The JSON parses, so nothing raised and
the hole was cached — the session simply contributed no knowledge until someone
noticed. The guard turns it into an exception the existing retry can act on.
"""

import json

import pytest
from pnp_okf.config import DeepSeekConfig
from pnp_okf.extract import _call_llm_json_prompt


class _FakeClient:
    """Minimal stand-in for the OpenAI client: returns a canned payload."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0
        chat = type("chat", (), {})()
        chat.completions = self
        self.chat = chat

    def create(self, **kwargs):
        self.calls += 1
        message = type("m", (), {"content": json.dumps(self._payload)})()
        return type("c", (), {"choices": [type("ch", (), {"message": message})()]})()


def _cfg():
    return DeepSeekConfig(
        api_key="x", model="deepseek-v4-flash", base_url="https://example.invalid"
    )


MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]

# Call past the retry decorator: the guard is what's under test, and the real
# backoff would add ~14s to the suite for no extra coverage.
_call = _call_llm_json_prompt.__wrapped__


def test_recap_without_entities_raises():
    client = _FakeClient({"recap": "Eine lange Zusammenfassung.", "entities": []})
    with pytest.raises(RuntimeError):
        _call(client, _cfg(), MESSAGES)


def test_entities_present_is_accepted():
    payload = {
        "recap": "Eine lange Zusammenfassung.",
        "entities": [
            {
                "name": "Dodo",
                "type": "Character",
                "note": "Tat etwas.",
                "citation_ts": "00:01:00",
                "subtype": "",
            }
        ],
    }
    result = _call(_FakeClient(payload), _cfg(), MESSAGES)
    assert [e.name for e in result.entities] == ["Dodo"]
