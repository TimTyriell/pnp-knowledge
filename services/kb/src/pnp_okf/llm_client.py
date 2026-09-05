from __future__ import annotations

from openai import OpenAI

from pnp_okf.config import DeepSeekConfig
from pnp_okf.usage import LEDGER


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

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _CountingChat:
    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.completions = _CountingCompletions(inner.completions)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class CountingClient:
    """OpenAI client that records token usage into the process-wide ledger.

    Everything except ``.chat`` is delegated untouched, so this stays a
    drop-in for the real client.
    """

    def __init__(self, inner: OpenAI) -> None:
        self._inner = inner
        self.chat = _CountingChat(inner.chat)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def build_client(cfg: DeepSeekConfig) -> CountingClient:
    """Create an OpenAI-compatible client pointed at the DeepSeek API."""
    return CountingClient(OpenAI(base_url=cfg.base_url, api_key=cfg.api_key))
