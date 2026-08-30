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
    SYNTH_SECONDARY_TEMPLATE,
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

    A name claimed by two or more distinct concepts is ambiguous and dropped
    entirely rather than resolved by any tiebreak — a wrong link (silently
    picking one concept's page for a mention that meant the other) is worse
    than no link.
    """

    owners: dict[str, set[str]] = {}
    concept_of: dict[str, str] = {}
    for entity in entities:
        for name in [entity.canonical_name, *entity.aliases]:
            name = name.strip()
            if len(name) >= 4:
                owners.setdefault(name, set()).add(entity.concept_id)
                concept_of[name] = entity.concept_id
    return {name: concept_of[name] for name, ids in owners.items() if len(ids) == 1}


def _link_first_occurrence(
    text: str,
    name: str,
    concept_id: str,
    known_names: set[str] | None = None,
    *,
    skip_headings: bool = False,
) -> str:
    """Link the first bare occurrence of ``name`` in ``text``, or return it
    unchanged if there isn't one.

    ``skip_headings`` skips a match that falls on a ``#``-heading line (a
    section title, not prose) without giving up the single whole-text scan —
    it walks matches in order and takes the first whose own line isn't a
    heading, rather than splitting the body into lines up front.
    """

    # German runs names through the genitive ("Lindo Lauts Amulett"), so
    # allow a trailing -s and keep it inside the link label. Suppressed when
    # name + "s" is itself a known entity name (e.g. "Vora" / "Voras") --
    # otherwise the genitive tail lets the shorter name's link consume the
    # longer name's occurrences, mislinking every "Voras" in the bundle to
    # the unrelated one-mention concept "Vora".
    collides = known_names is not None and (name + "s").lower() in known_names
    tail = "" if name[-1] in "sßxz" or collides else "s?"
    # Not inside a word, not inside an existing link label or url.
    pattern = re.compile(rf"(?<![\w\[/]){re.escape(name)}{tail}(?![\w\]])")

    match = None
    if skip_headings:
        for candidate in pattern.finditer(text):
            line_start = text.rfind("\n", 0, candidate.start()) + 1
            line_end = text.find("\n", candidate.end())
            line = text[line_start : line_end if line_end != -1 else len(text)]
            if not line.lstrip().startswith("#"):
                match = candidate
                break
    else:
        match = pattern.search(text)

    if match is None:
        return text
    label = match.group(0)
    return f"{text[:match.start()]}[{label}]({concept_id}.md){text[match.end():]}"


def _autolink(text: str, targets: dict[str, str], skip: str) -> str:
    """Link the first occurrence of each known entity name in ``text``."""

    known_names = {n.lower() for n in targets}
    linked: set[str] = set()
    # Longest names first, so "Lindo Laut" is not pre-empted by "Lindo".
    for name in sorted(targets, key=len, reverse=True):
        concept_id = targets[name]
        if concept_id == skip or concept_id in linked:
            continue
        new_text = _link_first_occurrence(text, name, concept_id, known_names)
        if new_text != text:
            text = new_text
            linked.add(concept_id)
    return text


_BELEGE_HEADING_RE = re.compile(r"^#{1,6}\s*Belege\s*$", re.IGNORECASE | re.MULTILINE)
_LINK_TARGET_RE = re.compile(r"\]\(([^)\s]+?)\.md\)")


def _linked_concept_ids(text: str, targets: dict[str, str]) -> set[str]:
    """Concept ids already reachable via a markdown link somewhere in
    ``text`` — matched by full path or bare slug, so a link the model wrote
    itself (or a previous autolink pass) is never linked a second time.

    A link that names a directory (``/deities/foo.md``) must match that
    exact concept id — falling back to a bare-slug match there let a linked
    ``deities/foo`` mark the unrelated ``npcs/foo`` as already-linked too,
    silently swallowing a real mention (see validate.py's own
    ``cross_type_slugs`` check, which exists because such collisions are
    expected). The slug-only fallback stays, but only for links the model
    wrote without a directory segment at all.
    """

    paths = {m.group(1).lstrip("./").lstrip("/") for m in _LINK_TARGET_RE.finditer(text)}
    dir_paths = {p for p in paths if "/" in p}
    bare_slugs = {p for p in paths if "/" not in p}
    return {
        cid
        for cid in set(targets.values())
        if cid in dir_paths or cid.rsplit("/", 1)[-1] in bare_slugs
    }


def autolink_prose(text: str, targets: dict[str, str], skip: str) -> str:
    """Autolink the narrative prose of a synthesized body — everything
    before the ``# Belege`` heading, one line at a time.

    Two things stay untouched on purpose: the ``# Belege`` citation list
    (and anything after it, e.g. ``# Offene Konflikte`` — those cite by
    number, not by name), and any ``#``-heading line, where an entity name is
    a section title rather than prose. Idempotent: a name already linked
    anywhere in the text (by the model itself or a prior pass) is never
    linked again, so applying this twice is the same as applying it once.
    """

    match = _BELEGE_HEADING_RE.search(text)
    head, tail = (text[: match.start()], text[match.start() :]) if match else (text, "")

    linked = _linked_concept_ids(head, targets) | {skip}
    names = sorted(targets, key=len, reverse=True)
    known_names = {n.lower() for n in targets}
    for name in names:
        concept_id = targets[name]
        if concept_id in linked:
            continue
        new_head = _link_first_occurrence(head, name, concept_id, known_names, skip_headings=True)
        if new_head != head:
            head = new_head
            linked.add(concept_id)
    return head + tail


def render_belege_section(entity: CanonicalEntity) -> str:
    """The ``# Belege`` citation list built from ``entity``'s mentions.

    Shared by :func:`render_brief_body` (which always needs one) and
    ``emit.py::emit_entity`` (which backfills one when the model's own
    synthesis omitted the section it was asked for).
    """

    lines = ["# Belege", ""]
    for i, m in enumerate(entity.mentions, start=1):
        marker = "" if m.quality == "hoch" else f" [Transkriptqualität: {m.quality}]"
        lines.append(f"{i}. Session {m.date} @ {m.citation_ts} ({m.url}){marker}")
    return "\n".join(lines)


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
    return f"{body}\n\n{render_belege_section(entity)}"


def _cache_key(
    entity: CanonicalEntity,
    cfg: DeepSeekConfig,
    sources: str,
    excerpts: str,
    secondary: str = "",
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
            "secondary": hashlib.sha256(secondary.encode("utf-8")).hexdigest()[:16],
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
    secondary: str = "",
) -> str:
    user = SYNTH_USER_TEMPLATE.format(
        name=entity.canonical_name,
        type=entity.type.value,
        concept_id=entity.concept_id,
        aliases=", ".join(entity.aliases) or "-",
        tier_guidance=SYNTH_TIER_GUIDANCE[entity.tier],
        mentions=_render_mentions(entity),
        sources=SYNTH_SOURCES_TEMPLATE.format(sources=sources) if sources else "",
        secondary=SYNTH_SECONDARY_TEMPLATE.format(secondary=secondary) if secondary else "",
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
    secondary: str = "",
) -> str:
    """Produce the German markdown body for one canonical entity (cached).

    ``sources`` is matched world material from ``knowledge/sources/``;
    ``excerpts`` is original transcript dialogue around this entity's
    citations; ``secondary`` is I-002's rulings about other entities this
    entity's own mentions cite. All three are optional extra grounding — see
    :mod:`pnp_okf.context`.
    """

    key = _cache_key(entity, cfg, sources, excerpts, secondary)
    path = _cache_path(cache_dir, entity)
    if not force and path.exists():
        blob = json.loads(path.read_text(encoding="utf-8"))
        if blob.get("_key") == key:
            log.info("[synth] cache hit: %s", entity.concept_id)
            return blob["body"]

    log.info(
        "[synth] calling DeepSeek: %s (tier=%s, %d mentions%s%s%s)",
        entity.concept_id,
        entity.tier,
        len(entity.mentions),
        ", +sources" if sources else "",
        f", +{len(excerpts)//1000}k excerpt chars" if excerpts else "",
        ", +secondary" if secondary else "",
    )
    client = client or build_client(cfg)
    body = _call_llm(client, cfg, entity, sources, excerpts, secondary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_key": key, "body": body}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return body
