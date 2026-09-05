"""Token accounting: the ledger, and that the client wrapper actually feeds it.

Offline — no network, no LLM. The point of the wrapper test is that counting
happens at the choke point (``build_client``) rather than at each call site, so
a call site added later is counted without anyone remembering to.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pnp_okf.llm_client import CountingClient
from pnp_okf.usage import LEDGER, UsageLedger


def _usage(prompt: int, completion: int):
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)


def test_records_calls_and_tokens_per_model():
    led = UsageLedger()
    led.record("deepseek-v4-pro", _usage(100, 20))
    led.record("deepseek-v4-pro", _usage(50, 10))
    led.record("deepseek-v4-flash", _usage(7, 3))

    snap = led.snapshot()
    assert snap["llm_calls"] == 3
    assert snap["tokens"] == {"prompt": 157, "completion": 33}
    assert snap["by_model"]["deepseek-v4-pro"]["calls"] == 2
    assert snap["by_model"]["deepseek-v4-flash"]["prompt_tokens"] == 7


@pytest.mark.parametrize("model,usage", [(None, _usage(1, 1)), ("m", None)])
def test_missing_model_or_usage_is_ignored_not_fatal(model, usage):
    """A cached or stubbed response carries no usage. That must not break a run."""

    led = UsageLedger()
    led.record(model, usage)
    assert led.snapshot()["llm_calls"] == 0


def test_cost_is_absent_unless_prices_are_configured(monkeypatch):
    """Unpriced must be distinguishable from free — never a guessed number."""

    monkeypatch.delenv("PNP_PRICE_IN_DEEPSEEK_V4_PRO", raising=False)
    monkeypatch.delenv("PNP_PRICE_OUT_DEEPSEEK_V4_PRO", raising=False)
    led = UsageLedger()
    led.record("deepseek-v4-pro", _usage(1_000_000, 1_000_000))

    snap = led.snapshot()
    assert "cost" not in snap
    assert "cost" not in snap["by_model"]["deepseek-v4-pro"]


def test_cost_computed_per_million_tokens_when_priced(monkeypatch):
    monkeypatch.setenv("PNP_PRICE_IN_DEEPSEEK_V4_PRO", "2.0")
    monkeypatch.setenv("PNP_PRICE_OUT_DEEPSEEK_V4_PRO", "8.0")
    monkeypatch.setenv("PNP_PRICE_CURRENCY", "EUR")
    led = UsageLedger()
    led.record("deepseek-v4-pro", _usage(1_000_000, 500_000))

    snap = led.snapshot()
    assert snap["by_model"]["deepseek-v4-pro"]["cost"] == pytest.approx(6.0)
    assert snap["cost"] == pytest.approx(6.0)
    assert snap["cost_currency"] == "EUR"


def test_client_wrapper_counts_without_call_site_changes():
    """The wrapper must record usage and still return the completion untouched."""

    completion = SimpleNamespace(usage=_usage(11, 5), choices=["ok"])
    inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: completion)),
        other_attr="delegated",
    )
    LEDGER.reset()
    client = CountingClient(inner)

    got = client.chat.completions.create(model="deepseek-v4-flash", messages=[])

    assert got is completion, "wrapper must not replace the response object"
    assert client.other_attr == "delegated", "non-chat attributes pass through"
    snap = LEDGER.snapshot()
    assert snap["by_model"]["deepseek-v4-flash"]["prompt_tokens"] == 11
    LEDGER.reset()
