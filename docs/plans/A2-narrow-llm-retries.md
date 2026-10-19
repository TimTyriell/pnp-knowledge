# A2 — Retry only what a retry can fix

| | |
|---|---|
| Branch | `fix/narrow-llm-retries` |
| Base | `origin/main` |
| Depends on | — |
| Cost | $0 (and it saves money: no paid retries on auth or 400 errors) |
| Size | S |

## Goal

`extract._call_llm_json_prompt` and `synthesize._call_llm` retry on
`retry_if_exception_type(Exception)`, 4 attempts. A wrong API key, an
invalid request (400) or a model-not-found error gets retried with backoff,
and a 400 caused by an oversized request is **billed** each time. Replace
that with one shared predicate, `is_retryable`, in `llm_client.py`.

## What must stay retryable

| Exception | Why |
|---|---|
| `openai.APIConnectionError`, `openai.APITimeoutError` | transient network |
| `openai.RateLimitError` (429) | backoff fixes it |
| `openai.InternalServerError`, any `openai.APIStatusError` with `status_code >= 500` | provider side |
| `pydantic.ValidationError`, `json.JSONDecodeError` | the model returned malformed JSON; a resample usually fixes it |
| our own "empty output" guards | deliberate: `extract.py` raises on "recap but zero entities" so the retry takes another sample (see that function's comment) |

Everything else (`AuthenticationError`, `PermissionDeniedError`,
`BadRequestError`, `NotFoundError`, `UnprocessableEntityError`, programming
errors) fails fast.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c fix/narrow-llm-retries origin/main
```

### 2. `services/kb/src/pnp_okf/llm_client.py`

Add below the imports:

```python
import json

import openai
import pydantic


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

    Retrying everything (the old ``retry_if_exception_type(Exception)``)
    also retried a bad API key or a 400, four times each, with backoff --
    and a 400 for an oversized request is billed every time.
    """

    if isinstance(exc, _TRANSIENT | EmptyModelOutput):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    return isinstance(exc, pydantic.ValidationError | json.JSONDecodeError)
```

`isinstance` with a `|` union works on Python 3.10+ (the project needs
3.11). Check the order: `openai.RateLimitError` and `InternalServerError`
are `APIStatusError` subclasses, and the tuple check catches them first.

### 3. Raise `EmptyModelOutput` at the three guard sites

- `extract.py` `_call_llm_structured`: `raise RuntimeError("Model returned
  no parsed extraction")` → `raise EmptyModelOutput(...)`.
  - This one is **not** under retry; it is caught by the probe logic. Keep
    behaviour identical: the probe catches `Exception`, and
    `EmptyModelOutput` is one.
- `extract.py` `_call_llm_json_prompt`: the "recap but zero entities" raise
  → `EmptyModelOutput`.
- `synthesize.py` `_call_llm`: the "empty synthesis body" raise →
  `EmptyModelOutput`.

### 4. Swap the decorators

In both `extract.py` and `synthesize.py`:

```python
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from pnp_okf.llm_client import EmptyModelOutput, build_client, is_retryable
...
@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception(is_retryable),
)
```

Remove the now-unused `retry_if_exception_type` import (ruff will flag it).

`dedup.py` has no tenacity retry (it uses `CALL_TIMEOUT_S`); leave it.

### 5. Tests: `services/kb/tests/test_llm_retry.py` (new)

```python
"""is_retryable: retry transient and malformed-output failures only (A2)."""

from __future__ import annotations

import json

import httpx
import openai
import pydantic
import pytest
from pnp_okf.llm_client import EmptyModelOutput, is_retryable

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
```

If an `openai` exception constructor signature differs in the installed
version, check `openai/_exceptions.py` in the venv and adapt the helper. The
constructors take `(message, *, response, body)` for status errors and
`(*, request)` / `(request=)` for connection errors in openai ≥1.40.

Also add one integration-style test: a fake client whose `create` raises
`AuthenticationError` once. Call `synthesize._call_llm` (with retry) and
assert the fake was called **once** (no retries). Use the fake-client
pattern from `tests/test_extract_guard.py`.

### 6. Verify, commit, PR

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
```

Message: `fix(kb): retry only transient and malformed-output LLM failures`

## Done when

- [ ] No `retry_if_exception_type(Exception)` left in `services/kb/src`
      (`grep -rn "retry_if_exception_type" services/kb/src` → empty).
- [ ] Tests green; `test_extract_guard.py` unchanged and green.
