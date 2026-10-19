"""is_retryable: retry transient and malformed-output failures only (A2)."""

from __future__ import annotations

import json

import httpx
import openai
import pydantic
import pytest
from pnp_okf.config import DeepSeekConfig
from pnp_okf.llm_client import EmptyModelOutput, is_retryable
from pnp_okf.models import CanonicalEntity, EntityType
from pnp_okf.synthesize import _call_llm

_REQ = httpx.Request("POST", "https://example.invalid/v1/chat/completions")


def _status(cls, code):
    return cls("x", response=httpx.Response(code, request=_REQ), body=None)


@pytest.mark.parametrize("exc", [
    openai.APIConnectionError(request=_REQ),
    openai.APITimeoutError(request=_REQ),
    _status(openai.RateLimitError, 429),
    _status(openai.InternalServerError, 500),
    _status(openai.APIStatusError, 503),
    EmptyModelOutput("no entities"),
    json.JSONDecodeError("x", "", 0),
])
def test_retryable(exc):
    assert is_retryable(exc)


@pytest.mark.parametrize("exc", [
    _status(openai.AuthenticationError, 401),
    _status(openai.BadRequestError, 400),
    _status(openai.NotFoundError, 404),
    ValueError("bug"),
    KeyError("bug"),
])
def test_not_retryable(exc):
    assert not is_retryable(exc)


def test_validation_error_is_retryable():
    class M(pydantic.BaseModel):
        x: int

    with pytest.raises(pydantic.ValidationError) as info:
        M.model_validate({"x": "nope"})
    assert is_retryable(info.value)


def test_empty_output_is_still_a_runtime_error():
    assert issubclass(EmptyModelOutput, RuntimeError)


class _AuthFailingClient:
    """Fake client whose only call fails with 401; counts the calls it gets."""

    def __init__(self):
        self.calls = 0
        chat = type("chat", (), {})()
        chat.completions = self
        self.chat = chat

    def create(self, **kwargs):
        self.calls += 1
        raise _status(openai.AuthenticationError, 401)


def test_auth_error_is_not_retried():
    # Goes through the real @retry decorator (no __wrapped__): a non-retryable
    # error must reraise on the first attempt, with no backoff sleep and no
    # network call -- the fake client never leaves the process.
    client = _AuthFailingClient()
    cfg = DeepSeekConfig(api_key="x", model="m", base_url="https://example.invalid")
    entity = CanonicalEntity(
        concept_id="characters/held",
        type=EntityType.CHARACTER,
        canonical_name="Held",
    )
    with pytest.raises(openai.AuthenticationError):
        _call_llm(client, cfg, entity, sources="", excerpts="")
    assert client.calls == 1
