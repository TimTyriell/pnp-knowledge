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
from pnp_okf.models import CanonicalEntity
from pnp_okf.prompts import (
    PROMPT_VERSION,
    SYNTH_EXCERPTS_TEMPLATE,
    SYNTH_SOURCES_TEMPLATE,
    SYNTH_SYSTEM,
    SYNTH_TIER_GUIDANCE,
    SYNTH_USER_TEMPLATE,
)

log = logging.getLogger(__name__)


def _render_mentions(entity: CanonicalEntity) -> str:
    lines = []
    for i, m in enumerate(entity.mentions, start=1):
        marker = "" if m.quality == "hoch" else f" [Transkriptqualität: {m.quality}]"
        lines.append(
            f"[{i}] Session {m.date} @ {m.citation_ts} ({m.url}){marker}\n    {m.note}"
        )
    return "\n".join(lines)


def link_targets(entities: list[CanonicalEntity]) -> dict[str, str]:
    """``display name -> concept_id`` for deterministic cross-linking.

    On a name collision the better-attested entity wins, so a passing mention
    never steals a link from the concept the campaign actually revolves around.
    """

    best: dict[str, CanonicalEntity] = {}
    for entity in sorted(entities, key=lambda e: len(e.mentions)):
        for name in [entity.canonical_name, *entity.aliases]:
            name = name.strip()
            if len(name) >= 4:
                best[name] = entity
    return {name: e.concept_id for name, e in best.items()}


def _autolink(text: str, targets: dict[str, str], skip: str) -> str:
    """Link the first occurrence of each known entity name in ``text``."""

    linked: set[str] = set()
    # Longest names first, so "Lindo Laut" is not pre-empted by "Lindo".
    for name in sorted(targets, key=len, reverse=True):
        concept_id = targets[name]
        if concept_id == skip or concept_id in linked:
            continue
        # German runs names through the genitive ("Lindo Lauts Amulett"), so
        # allow a trailing -s and keep it inside the link label.
        tail = "" if name[-1] in "sßxz" else "s?"
        # Not inside a word, not inside an existing link label or url.
        match = re.search(rf"(?<![\w\[/]){re.escape(name)}{tail}(?![\w\]])", text)
        if match is None:
            continue
        label = match.group(0)
        text = f"{text[:match.start()]}[{label}]({concept_id}.md){text[match.end():]}"
        linked.add(concept_id)
    return text


def render_brief_body(
    entity: CanonicalEntity, targets: dict[str, str] | None = None
) -> str:
    """Body for a brief-tier entity, built locally with no LLM call.

    A brief entry's entire input is one 30-70 word note, and a model asked to
    turn that into a 50-word page only reformats it — no knowledge is added.
    For 862 of 1074 entries that was about half the cost and most of the wall
    time of a full run. Cross-links are matched against the concept index
    instead, which is also steadier than a model inventing them.
    """

    paragraphs = [m.note.strip() for m in entity.mentions if m.note.strip()]
    body = "\n\n".join(paragraphs)
    if targets:
        body = _autolink(body, targets, skip=entity.concept_id)
    lines = [body, "", "# Belege", ""]
    for i, m in enumerate(entity.mentions, start=1):
        marker = "" if m.quality == "hoch" else f" [Transkriptqualität: {m.quality}]"
        lines.append(f"{i}. Session {m.date} @ {m.citation_ts} ({m.url}){marker}")
    return "\n".join(lines)


def _cache_key(
    entity: CanonicalEntity, cfg: DeepSeekConfig, sources: str, excerpts: str
) -> str:
    payload = json.dumps(
        {
            "v": PROMPT_VERSION,
            "model": cfg.model,
            "entity": entity.model_dump(mode="json"),
            "tier": entity.tier,
            # Extra grounding changes the output, so it has to key the cache.
            "sources": hashlib.sha256(sources.encode("utf-8")).hexdigest()[:16],
            "excerpts": hashlib.sha256(excerpts.encode("utf-8")).hexdigest()[:16],
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
def _call_llm(
    client,
    cfg: DeepSeekConfig,
    entity: CanonicalEntity,
    sources: str,
    excerpts: str,
) -> str:
    user = SYNTH_USER_TEMPLATE.format(
        name=entity.canonical_name,
        type=entity.type.value,
        concept_id=entity.concept_id,
        aliases=", ".join(entity.aliases) or "-",
        tier_guidance=SYNTH_TIER_GUIDANCE[entity.tier],
        mentions=_render_mentions(entity),
        sources=SYNTH_SOURCES_TEMPLATE.format(sources=sources) if sources else "",
        excerpts=SYNTH_EXCERPTS_TEMPLATE.format(excerpts=excerpts) if excerpts else "",
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
    sources: str = "",
    excerpts: str = "",
) -> str:
    """Produce the German markdown body for one canonical entity (cached).

    ``sources`` is matched world material from ``knowledge/sources/``;
    ``excerpts`` is original transcript dialogue around this entity's
    citations. Both are optional extra grounding — see :mod:`pnp_okf.context`.
    """

    key = _cache_key(entity, cfg, sources, excerpts)
    path = _cache_path(cache_dir, entity)
    if not force and path.exists():
        blob = json.loads(path.read_text(encoding="utf-8"))
        if blob.get("_key") == key:
            log.info("[synth] cache hit: %s", entity.concept_id)
            return blob["body"]

    log.info(
        "[synth] calling DeepSeek: %s (tier=%s, %d mentions%s%s)",
        entity.concept_id,
        entity.tier,
        len(entity.mentions),
        ", +sources" if sources else "",
        f", +{len(excerpts)//1000}k excerpt chars" if excerpts else "",
    )
    client = client or build_client(cfg)
    body = _call_llm(client, cfg, entity, sources, excerpts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_key": key, "body": body}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return body
