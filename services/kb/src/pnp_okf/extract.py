from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pnp_okf.config import DeepSeekConfig
from pnp_okf.llm_client import build_client
from pnp_okf.models import SessionExtraction, SessionTranscript
from pnp_okf.prompts import (
    EXTRACT_SYSTEM,
    EXTRACT_USER_TEMPLATE,
    PROMPT_VERSION,
)

log = logging.getLogger(__name__)

# Models whose endpoint has already answered "no" to structured outputs.
# The probe in _call_llm costs a full transcript upload and is rejected at
# validation, and an endpoint's answer cannot change mid-run -- so learning it
# once per process turns one wasted round trip per uncached session into at
# most one per worker. Not locked: a lock here would serialise the first call
# of every worker to save a handful of probes on a run that makes hundreds of
# real calls. Keyed by model because for_tier() swaps the model per tier.
_NO_STRUCTURED_OUTPUTS: set[str] = set()


def _frozen_prompt_version(transcript: SessionTranscript) -> str:
    """Prompt version this session's cache key should use.

    A PROMPT_VERSION bump invalidates every cached extraction at once, so
    editing one constant re-derives the whole back catalogue: ~10M tokens and
    ~$8 on a 66-session corpus (docs/architecture/MIGRATION-prompt-v6.md).
    Worse, re-extraction resamples entity *names*, and names derive concept
    ids -- so the back catalogue's ids churn even though its transcripts have
    not changed by a word.

    Freezing pins already-ingested sessions to the version they were built
    with, so a bump only re-extracts sessions recorded after the cutoff:

        PNP_EXTRACT_FREEZE_BEFORE=2026-09-06   # session date, exclusive
        PNP_EXTRACT_FREEZE_VERSION=6           # version they are pinned to

    Both must be set; either alone is ignored, so the default stays
    "re-extract everything" and freezing is always a deliberate act.

    Caveat: this pins the prompt only. ``cfg.model`` is still in the key, so
    changing the model re-extracts frozen sessions too -- deliberately, since a
    new model rewords names and the frozen ids would not match what it makes.
    """

    before = os.environ.get("PNP_EXTRACT_FREEZE_BEFORE", "").strip()
    version = os.environ.get("PNP_EXTRACT_FREEZE_VERSION", "").strip()
    if not before or not version:
        return PROMPT_VERSION
    return version if str(transcript.date) < before else PROMPT_VERSION


def _cache_key(transcript: SessionTranscript, cfg: DeepSeekConfig) -> str:
    payload = "\n".join(
        [
            _frozen_prompt_version(transcript),
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


def _call_llm_structured(client, cfg: DeepSeekConfig, messages: list) -> SessionExtraction:
    """Attempt extraction via OpenAI structured-outputs (beta.parse).

    DeepSeek's OpenAI-compatible endpoint doesn't reliably support strict
    json_schema mode (per pnp-graph-service's experience); raises an
    exception (caught by the caller) so `_call_llm` falls back to the
    JSON-prompt path below.

    Deliberately *not* retried: an unsupported endpoint answers 400 every
    time, so retrying only multiplies the probe cost by four on every
    session before the fallback runs. Transient failures are still covered
    by the retry on the fallback path.
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
    parsed = SessionExtraction.model_validate_json(_extract_json_block(raw))
    # A session that produced a recap but no entities is a silent failure, not
    # a result: the model spent its budget on the prose and dropped the list.
    # Raising here lets the retry above take another sample instead of caching
    # a hole in the bundle.
    if parsed.recap.strip() and not parsed.entities:
        raise RuntimeError("Extraction returned a recap but zero entities")
    return parsed


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
    if cfg.model in _NO_STRUCTURED_OUTPUTS:
        return _call_llm_json_prompt(client, cfg, messages)
    try:
        return _call_llm_structured(client, cfg, messages)
    except Exception as exc:
        _NO_STRUCTURED_OUTPUTS.add(cfg.model)
        log.info(
            "[extract] structured-outputs not available for %s (%s); using the "
            "JSON prompt for the rest of this run",
            cfg.model,
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
