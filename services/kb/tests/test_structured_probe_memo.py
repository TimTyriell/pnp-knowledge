"""The structured-outputs probe fires once per run, not once per session.

DeepSeek's endpoint rejects strict json_schema mode, so _call_llm probes it,
eats a 400, and falls back to the JSON prompt. The probe uploads the whole
transcript before being rejected at validation, and the answer cannot change
mid-run -- so before this was memoised a 66-session cold run paid 66 identical
wasted round trips.
"""

import json
import threading
import time

import httpx
import openai
import pytest
from pnp_okf import extract as extract_mod
from pnp_okf.config import DeepSeekConfig
from pnp_okf.extract import _call_llm
from pnp_okf.models import SessionExtraction

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
    # Both memos, or a test that settles _PROBED leaks it into every later
    # file in the session -- the capability would read as already known.
    extract_mod._NO_STRUCTURED_OUTPUTS.clear()
    extract_mod._PROBED.clear()
    yield
    extract_mod._NO_STRUCTURED_OUTPUTS.clear()
    extract_mod._PROBED.clear()


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


class _ConnErrorClient(_FakeClient):
    """Structured-outputs probe fails with a transient network error, not a
    real "unsupported" response."""

    def parse(self, **kwargs):
        self.probes += 1
        raise openai.APIConnectionError(
            request=httpx.Request("POST", "https://example.invalid")
        )


def test_connection_error_does_not_poison_the_memo():
    """A dropped connection during the probe says nothing about whether the
    model supports structured outputs -- unlike a real capability rejection,
    it can succeed on the very next attempt. Memoising it anyway would
    silently degrade every remaining session in the run to the JSON-prompt
    path for no reason."""

    client, cfg, t = _ConnErrorClient(), _cfg(), _transcript()
    _call_llm(client, cfg, t)
    assert cfg.model not in extract_mod._NO_STRUCTURED_OUTPUTS
    assert client.json_calls == 1, "the call itself should still fall back and succeed"


def test_capability_error_still_populates_the_memo():
    client, cfg, t = _FakeClient(), _cfg(), _transcript()
    _call_llm(client, cfg, t)
    assert cfg.model in extract_mod._NO_STRUCTURED_OUTPUTS


def test_concurrent_workers_probe_only_once(monkeypatch):
    """Parallel extraction must not upload N transcripts to learn one boolean.

    The probe IS the first real call, so with --workers 8 up to eight threads
    raced past the memo and each uploaded a whole ~30k-token transcript before
    the first rejection landed. Measured at ~35% of a cold rebuild's tokens
    before the memo existed at all; the race is what is left of it.
    """

    import threading

    from pnp_okf.models import SessionTranscript

    extract_mod._PROBED.clear()
    client = _FakeClient()
    cfg = _cfg()
    transcript = SessionTranscript(
        session_id="2026-01-01_X_a", date="2026-01-01",
        url="https://youtu.be/x", title="T", segments=[],
    )

    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        _call_llm(client, cfg, transcript)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert client.probes == 1, (
        f"{client.probes} threads each uploaded a full transcript to discover "
        "the same unsupported-capability answer"
    )
    assert client.json_calls == 8


class _SupportedClient(_FakeClient):
    """An endpoint that *supports* structured outputs, and takes a moment.

    _FakeClient rejects the capability, so every thread after the first
    returns at the ``_NO_STRUCTURED_OUTPUTS`` check -- before reaching the
    code the probe lock actually guards. Only a supported endpoint runs that
    code, which is why the serialisation below is invisible to the rejection
    path's test.
    """

    def __init__(self, delay: float = 0.05):
        super().__init__()
        self.delay = delay
        self._lock = threading.Lock()
        self._inflight = 0
        self.max_inflight = 0

    def parse(self, **kwargs):
        with self._lock:
            self.probes += 1
            self._inflight += 1
            self.max_inflight = max(self.max_inflight, self._inflight)
        try:
            time.sleep(self.delay)
        finally:
            with self._lock:
                self._inflight -= 1
        message = type("m", (), {"parsed": SessionExtraction.model_validate(PAYLOAD)})()
        return type("c", (), {"choices": [type("ch", (), {"message": message})()]})()


def test_a_settled_capability_does_not_serialise_the_remaining_workers():
    """Only the probe may hold the lock -- not a full extraction.

    ``guard`` is chosen *before* the lock is taken, so with --workers 8 all
    eight threads commit to _PROBE_LOCK while the memo is still empty. The
    first probes and settles it; the rest then acquire in turn and, on the
    success path, run their whole structured call inside the lock, because
    nothing re-checks _PROBED after acquisition. The first eight sessions of
    a cold run extract strictly one at a time.
    """

    client, cfg, transcript = _SupportedClient(), _cfg(), _transcript()
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        _call_llm(client, cfg, transcript)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert client.probes == 8, "every worker still gets a real extraction"
    assert client.max_inflight > 1, (
        "the workers ran one at a time: after the probe settled the capability, "
        "the waiting threads still held _PROBE_LOCK for a full extraction"
    )
