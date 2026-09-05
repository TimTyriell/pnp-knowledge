"""The structured-outputs probe fires once per run, not once per session.

DeepSeek's endpoint rejects strict json_schema mode, so _call_llm probes it,
eats a 400, and falls back to the JSON prompt. The probe uploads the whole
transcript before being rejected at validation, and the answer cannot change
mid-run -- so before this was memoised a 66-session cold run paid 66 identical
wasted round trips.
"""

import json

import pytest
from pnp_okf.config import DeepSeekConfig
from pnp_okf import extract as extract_mod
from pnp_okf.extract import _call_llm

PAYLOAD = {
    "recap": "Eine Sitzung.",
    "entities": [{"name": "Lindo Laut", "type": "Character", "note": "Ein Barde.", "citation_ts": "00:12:34", "subtype": ""}],
}
MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


class _FakeClient:
    """Refuses structured outputs, serves the JSON-prompt path."""

    def __init__(self):
        self.probes = 0
        self.json_calls = 0
        beta_chat = type("bc", (), {})()
        beta_chat.completions = self
        beta = type("b", (), {})()
        beta.chat = beta_chat
        self.beta = beta
        chat = type("chat", (), {})()
        chat.completions = self
        self.chat = chat

    def parse(self, **kwargs):          # client.beta.chat.completions.parse
        self.probes += 1
        raise RuntimeError("structured outputs unsupported")

    def create(self, **kwargs):         # client.chat.completions.create
        self.json_calls += 1
        message = type("m", (), {"content": json.dumps(PAYLOAD)})()
        return type("c", (), {"choices": [type("ch", (), {"message": message})()]})()


@pytest.fixture(autouse=True)
def _clear_memo():
    extract_mod._NO_STRUCTURED_OUTPUTS.clear()
    yield
    extract_mod._NO_STRUCTURED_OUTPUTS.clear()


def _cfg(model="deepseek-v4-pro"):
    return DeepSeekConfig(api_key="x", model=model, base_url="https://example.invalid")


def _transcript():
    class _T:
        session_id, date, title, quality = "s1", "2026-01-01", "T", "ok"
        unsicher_ratio = 0.0

        def render_dialogue(self):
            return "[00:00:00] A: hallo"

    return _T()


def test_probe_fires_once_across_many_sessions():
    client, cfg, t = _FakeClient(), _cfg(), _transcript()
    for _ in range(5):
        _call_llm(client, cfg, t)
    assert client.probes == 1, "structured-outputs probe should be memoised per model"
    assert client.json_calls == 5, "every session still gets a real extraction"


def test_memo_is_per_model():
    client, t = _FakeClient(), _transcript()
    _call_llm(client, _cfg("deepseek-v4-pro"), t)
    _call_llm(client, _cfg("deepseek-v4-flash"), t)
    # for_tier() swaps the model, and a different endpoint/model may well
    # support what this one does not.
    assert client.probes == 2
