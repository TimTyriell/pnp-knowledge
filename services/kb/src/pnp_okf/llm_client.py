from __future__ import annotations

import json

import openai
import pydantic
from openai import OpenAI

from pnp_okf.config import DeepSeekConfig
from pnp_okf.usage import LEDGER


class EmptyModelOutput(RuntimeError):
    """The model answered, but with nothing usable (no body, no entities).

    A RuntimeError subclass so existing ``pytest.raises(RuntimeError)``
    callers keep working; its own type so the retry predicate can tell it
    apart from a real bug.
    """


_TRANSIENT = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)


def is_retryable(exc: BaseException) -> bool:
    """True for failures a second attempt can plausibly fix.

    Retrying everything (the old catch-all ``Exception`` predicate)
    also retried a bad API key or a 400, four times each, with backoff --
    and a 400 for an oversized request is billed every time.
    """

    # Unpacked rather than `_TRANSIENT | EmptyModelOutput`: a tuple has no `|`,
    # so that form raises TypeError on the first retryable check.
    if isinstance(exc, (*_TRANSIENT, EmptyModelOutput)):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    return isinstance(exc, pydantic.ValidationError | json.JSONDecodeError)


class _CountingCompletions:
    """Passthrough around ``client.chat.completions`` that tallies usage.

    The wrapper sits here rather than at the call sites because every caller
    already routes through :func:`build_client` — extract, synthesize and
    dedup. Counting once at the choke point means no call site changes, and a
    call site added later is counted without anyone remembering to.
    """

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def create(self, *args, **kwargs):
        completion = self._inner.create(*args, **kwargs)
        LEDGER.record(kwargs.get("model"), getattr(completion, "usage", None))
        return completion

    def parse(self, *args, **kwargs):
        """Structured-outputs path. Counted for the same reason ``create`` is.

        The extraction probe calls this with the whole transcript in the
        prompt, so leaving it uncounted made every recorded cost an
        undercount -- silently, and in the flattering direction.
        """

        completion = self._inner.parse(*args, **kwargs)
        LEDGER.record(kwargs.get("model"), getattr(completion, "usage", None))
        return completion

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _CountingChat:
    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.completions = _CountingCompletions(inner.completions)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _CountingBeta:
    """``client.beta`` with its chat namespace counted, everything else passed on."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.chat = _CountingChat(inner.chat)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class CountingClient:
    """OpenAI client that records token usage into the process-wide ledger.

    Everything except ``.chat`` and ``.beta`` is delegated untouched, so this
    stays a drop-in for the real client.
    """

    def __init__(self, inner: OpenAI) -> None:
        self._inner = inner
        self.chat = _CountingChat(inner.chat)
        # Optional: test doubles and older clients need not carry `.beta`.
        beta = getattr(inner, "beta", None)
        if beta is not None and hasattr(beta, "chat"):
            self.beta = _CountingBeta(beta)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def build_client(cfg: DeepSeekConfig) -> CountingClient:
    """Create an OpenAI-compatible client pointed at the DeepSeek API."""
    return CountingClient(OpenAI(base_url=cfg.base_url, api_key=cfg.api_key))
