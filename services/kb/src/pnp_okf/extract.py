from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pnp_okf.llm_client import build_client
from pnp_okf.config import DeepSeekConfig
from pnp_okf.models import SessionExtraction, SessionTranscript
from pnp_okf.prompts import (
    EXTRACT_SYSTEM,
    EXTRACT_USER_TEMPLATE,
    PROMPT_VERSION,
)

log = logging.getLogger(__name__)


def _cache_key(transcript: SessionTranscript, cfg: DeepSeekConfig) -> str:
    payload = "\n".join(
        [
            PROMPT_VERSION,
            cfg.model,
            transcript.session_id,
            transcript.render_dialogue(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _cache_path(cache_dir: Path, transcript: SessionTranscript) -> Path:
    return cache_dir / "extract" / f"{transcript.session_id}.json"


def _load_cached(path: Path, key: str) -> SessionExtraction | None:
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if blob.get("_key") != key:
        return None
    return SessionExtraction.model_validate(blob["extraction"])


def _store_cache(path: Path, key: str, extraction: SessionExtraction) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {"_key": key, "extraction": extraction.model_dump(mode="json")}
    path.write_text(
        json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _extract_json_block(text: str) -> str:
    """Pull the first ```json … ``` fenced block, or the raw text if none."""
    m = re.search(r"```json\s*([\s\S]*?)```", text)
    return m.group(1).strip() if m else text.strip()


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(Exception),
)
def _call_llm_structured(client, cfg: DeepSeekConfig, messages: list) -> SessionExtraction:
    """Attempt extraction via OpenAI structured-outputs (beta.parse).

    DeepSeek's OpenAI-compatible endpoint doesn't reliably support strict
    json_schema mode (per pnp-graph-service's experience); raises an
    exception (caught by the caller) so `_call_llm` falls back to the
    JSON-prompt path below.
    """
    completion = client.beta.chat.completions.parse(
        model=cfg.model,
        messages=messages,
        response_format=SessionExtraction,
        temperature=0.2,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Model returned no parsed extraction")
    return parsed


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(Exception),
)
def _call_llm_json_prompt(client, cfg: DeepSeekConfig, messages: list) -> SessionExtraction:
    """JSON-prompt fallback for models that don't support structured outputs.

    Instructs the model to reply with a raw JSON object matching the schema
    and parses the response with Pydantic.
    """
    schema = SessionExtraction.model_json_schema()
    messages = list(messages)  # shallow copy
    messages[-1] = dict(messages[-1])
    messages[-1]["content"] = (
        messages[-1]["content"]
        + f"\n\nAntworte AUSSCHLIESSLICH mit einem JSON-Objekt gemäß diesem Schema "
        f"(kein Prosa, keine Codeblöcke):\n{json.dumps(schema, ensure_ascii=False)}"
    )
    completion = client.chat.completions.create(
        model=cfg.model,
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or ""
    return SessionExtraction.model_validate_json(_extract_json_block(raw))


def _call_llm(client, cfg: DeepSeekConfig, transcript: SessionTranscript) -> SessionExtraction:
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {
            "role": "user",
            "content": EXTRACT_USER_TEMPLATE.format(
                session_id=transcript.session_id,
                date=transcript.date,
                title=transcript.title,
                quality=transcript.quality,
                unsicher_pct=f"{transcript.unsicher_ratio:.0%}",
                dialogue=transcript.render_dialogue(),
            ),
        },
    ]
    try:
        return _call_llm_structured(client, cfg, messages)
    except Exception as exc:
        log.info(
            "[extract] structured-outputs not available (%s); falling back to JSON prompt",
            type(exc).__name__,
        )
        return _call_llm_json_prompt(client, cfg, messages)


def extract_session(
    transcript: SessionTranscript,
    cfg: DeepSeekConfig,
    cache_dir: Path,
    *,
    client=None,
    force: bool = False,
) -> SessionExtraction:
    """Extract a recap + entity mentions for one session (cached)."""

    key = _cache_key(transcript, cfg)
    path = _cache_path(cache_dir, transcript)
    if not force:
        cached = _load_cached(path, key)
        if cached is not None:
            log.info("[extract] cache hit: %s", transcript.session_id)
            return cached

    log.info(
        "[extract] calling DeepSeek (%s, %d words): %s",
        cfg.model,
        transcript.word_count,
        transcript.session_id,
    )
    client = client or build_client(cfg)
    extraction = _call_llm(client, cfg, transcript)
    _store_cache(path, key, extraction)
    return extraction
