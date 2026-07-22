from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pnp_okf.llm_client import build_client
from pnp_okf.config import DeepSeekConfig
from pnp_okf.models import CanonicalEntity
from pnp_okf.prompts import PROMPT_VERSION, SYNTH_SYSTEM, SYNTH_USER_TEMPLATE

log = logging.getLogger(__name__)


def _render_mentions(entity: CanonicalEntity) -> str:
    lines = []
    for i, m in enumerate(entity.mentions, start=1):
        lines.append(
            f"[{i}] Session {m.date} @ {m.citation_ts} ({m.url})\n    {m.note}"
        )
    return "\n".join(lines)


def _cache_key(entity: CanonicalEntity, cfg: DeepSeekConfig) -> str:
    payload = json.dumps(
        {
            "v": PROMPT_VERSION,
            "model": cfg.model,
            "entity": entity.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _cache_path(cache_dir: Path, entity: CanonicalEntity) -> Path:
    safe = entity.concept_id.replace("/", "__")
    return cache_dir / "synth" / f"{safe}.json"


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(Exception),
)
def _call_llm(client, cfg: DeepSeekConfig, entity: CanonicalEntity) -> str:
    user = SYNTH_USER_TEMPLATE.format(
        name=entity.canonical_name,
        type=entity.type.value,
        concept_id=entity.concept_id,
        aliases=", ".join(entity.aliases) or "-",
        mentions=_render_mentions(entity),
    )
    completion = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": SYNTH_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
    )
    body = completion.choices[0].message.content
    if not body:
        raise RuntimeError("Model returned empty synthesis body")
    return body.strip()


def synthesize_entity_body(
    entity: CanonicalEntity,
    cfg: DeepSeekConfig,
    cache_dir: Path,
    *,
    client=None,
    force: bool = False,
) -> str:
    """Produce the German markdown body for one canonical entity (cached)."""

    key = _cache_key(entity, cfg)
    path = _cache_path(cache_dir, entity)
    if not force and path.exists():
        blob = json.loads(path.read_text(encoding="utf-8"))
        if blob.get("_key") == key:
            log.info("[synth] cache hit: %s", entity.concept_id)
            return blob["body"]

    log.info("[synth] calling DeepSeek: %s", entity.concept_id)
    client = client or build_client(cfg)
    body = _call_llm(client, cfg, entity)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_key": key, "body": body}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return body
