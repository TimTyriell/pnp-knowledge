"""Merge-candidate detection for the human-in-the-loop dedup sweep.

``resolve.merge_near_duplicates`` folds duplicates it can prove from the
strings alone. Three failure modes survive it, all observed in this bundle:

* **Ambiguous supersets** — "Voras", "Graf Voras der Heilige" and "Voras der
  Heilige / der Schrecken". Token-subset matching finds *two* candidate
  supersets and deliberately refuses rather than guess.
* **Sub-threshold spelling drift** — "Willau" vs "Willauch" scores ~0.86
  against a 0.9 cutoff.
* **Semantic identity** — "Lenra" *is* "die Hack". No string method can ever
  connect those; it needs someone (or something) that read the entries.

This module proposes; it never writes. Confirmed groups become ``merge:``
entries in the registry, which is the durable record — the bundle itself is
regenerated output.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel, Field

from pnp_okf.config import DeepSeekConfig
from pnp_okf.llm_client import build_client
from pnp_okf.models import PERSON_TYPES, CanonicalEntity
from pnp_okf.okf import slugify

log = logging.getLogger(__name__)

# Below resolve.py's auto-merge bar: this stage only *suggests*, so it can
# afford to look at pairs that are too weak to fold automatically.
SUGGEST_RATIO = 0.72

# Entities per LLM call. One call for a whole space is slow (minutes of JSON
# generation) and dilutes attention across hundreds of candidates.
CHUNK_SIZE = 60

# Screening is a bounded per-call job and every group is confirmed by a human
# before anything is written, so a stalled call should fail fast and let the
# remaining chunks proceed rather than hang the whole sweep.
CALL_TIMEOUT_S = 180.0


class MergeGroup(BaseModel):
    """One proposed set of concept ids denoting the same entity."""

    concept_ids: list[str] = Field(default_factory=list)
    canonical: str = Field(default="", description="Preferred concept_id to keep.")
    reason: str = ""
    confidence: str = "mittel"  # hoch | mittel | niedrig
    source: str = "llm"  # llm | string


class _MergeResponse(BaseModel):
    groups: list[MergeGroup] = Field(default_factory=list)


def _space(entity: CanonicalEntity) -> str:
    """Identity space: a person may be typed Character in one session, NPC in
    another, so those share a space. Everything else matches its own type."""

    return "person" if entity.type in PERSON_TYPES else entity.type.value


def string_candidates(entities: list[CanonicalEntity]) -> list[MergeGroup]:
    """Pairs that look alike but sit under resolve.py's auto-merge threshold."""

    out: list[MergeGroup] = []
    for i, a in enumerate(entities):
        for b in entities[i + 1:]:
            if _space(a) != _space(b):
                continue
            sa = a.concept_id.rsplit("/", 1)[-1]
            sb = b.concept_id.rsplit("/", 1)[-1]
            ratio = SequenceMatcher(None, sa, sb).ratio()
            ta, tb = set(sa.split("_")), set(sb.split("_"))
            if ratio >= SUGGEST_RATIO:
                reason = f"Schreibvariante (Ähnlichkeit {ratio:.2f})"
            elif ta < tb or tb < ta:
                reason = "Namensteil-Übereinstimmung (Titel/Beiname)"
            else:
                continue
            out.append(
                MergeGroup(
                    concept_ids=[a.concept_id, b.concept_id],
                    canonical=(a if len(a.mentions) >= len(b.mentions) else b).concept_id,
                    reason=reason,
                    confidence="hoch" if ratio >= 0.85 else "mittel",
                    source="string",
                )
            )
    return out


_SYSTEM = """\
Du bist Archivar einer deutschsprachigen Pen-&-Paper-Kampagne. Du bekommst
eine Liste von Wiki-Einträgen (concept_id, Name, Kurzbeschreibung). Manche
Einträge beschreiben DIESELBE Entität unter verschiedenen Namen — durch
Transkriptionsfehler, Titel und Beinamen ("Graf X der Heilige" vs "X") oder
weil eine Figur unter zwei völlig verschiedenen Namen bekannt ist (ein
Eigenname und ein Beiname wie "die Hexe").

Finde diese Gruppen. Regeln:
- Nur zusammenfassen, wenn die Beschreibungen inhaltlich zur selben Entität
  passen. Gleiche Rolle allein genügt NICHT (zwei verschiedene Wirte, zwei
  verschiedene Goblins bleiben getrennt).
- Verwandte, aber verschiedene Dinge NICHT zusammenfassen: eine Stadt und die
  Taverne in dieser Stadt, ein Gott und sein Kult, eine Person und ihr
  Gegenstand bleiben getrennte Einträge.
- Gib je Gruppe an: alle concept_ids, welche als canonical bleiben soll
  (die mit der besten/vollständigsten Beschreibung), eine kurze deutsche
  Begründung und confidence (hoch/mittel/niedrig).
- Im Zweifel confidence niedrig setzen statt die Gruppe wegzulassen — ein
  Mensch prüft jede Gruppe nach.
- Einträge ohne Partner lässt du einfach weg.
"""


def llm_candidates(
    entities: list[CanonicalEntity], cfg: DeepSeekConfig, *, client=None
) -> list[MergeGroup]:
    """Ask the model which entries denote the same entity, one space at a time.

    Batched per identity space rather than pairwise: ~490 entities is ~120k
    pairs, but one prompt listing every NPC costs a single call and lets the
    model spot groups larger than two.
    """

    client = client or build_client(cfg)
    by_space: dict[str, list[CanonicalEntity]] = {}
    for e in entities:
        by_space.setdefault(_space(e), []).append(e)

    groups: list[MergeGroup] = []
    for space, members in sorted(by_space.items()):
        if len(members) < 2:
            continue
        # Sorted by slug so spelling variants ("willau"/"willauch") land in the
        # same chunk; a single call over hundreds of entries is both slow and
        # less accurate than several focused ones.
        members = sorted(members, key=lambda e: e.concept_id)
        for start in range(0, len(members), CHUNK_SIZE):
            chunk = members[start:start + CHUNK_SIZE]
            if len(chunk) < 2:
                continue
            groups.extend(_ask_chunk(client, cfg, space, chunk))
    return groups


def _ask_chunk(
    client, cfg: DeepSeekConfig, space: str, members: list[CanonicalEntity]
) -> list[MergeGroup]:
    listing = "\n".join(
        f"- {e.concept_id} | {e.canonical_name}"
        + (f" | auch: {', '.join(e.aliases)}" if e.aliases else "")
        + f" | {' '.join((e.mentions[0].note if e.mentions else '').split())[:160]}"
        for e in members
    )
    user = (
        f"Identitätsraum: {space} ({len(members)} Einträge)\n\n{listing}\n\n"
        "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt der Form "
        '{"groups": [{"concept_ids": [...], "canonical": "...", '
        '"reason": "...", "confidence": "hoch|mittel|niedrig"}]}.'
    )
    log.info("[dedup] asking about %d entries in space '%s'", len(members), space)
    try:
        completion = client.chat.completions.create(
            model=cfg.model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            timeout=CALL_TIMEOUT_S,
        )
        raw = completion.choices[0].message.content or "{}"
        parsed = _MergeResponse.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001 - one bad chunk must not sink the sweep
        log.warning("[dedup] chunk failed in space %s: %s", space, exc)
        return []

    known = {e.concept_id for e in members}
    out: list[MergeGroup] = []
    for g in parsed.groups:
        # Drop hallucinated ids rather than trusting the model's spelling.
        g.concept_ids = [c for c in dict.fromkeys(g.concept_ids) if c in known]
        if len(g.concept_ids) < 2:
            continue
        # Always keep the best-attested id, whatever the model nominated: it
        # routinely picks a one-mention spelling over the established concept
        # (e.g. "warzul_varsurs" over "vharzul" with 16 mentions), which would
        # fold the real entry into a stub.
        g.canonical = max(
            g.concept_ids,
            key=lambda c: len(next(e for e in members if e.concept_id == c).mentions),
        )
        out.append(g)
    return out


def load_never_merge(registry_path) -> list[set[str]]:
    """Pairs the human has ruled distinct, from the registry ``never_merge:``.

    Look-alikes that are genuinely different people recur every sweep —
    "Myko" (Willauch group) and "Miqo" (Kinder aus Abisalis) score as a near
    match forever. Without a memory of the rejection each run re-proposes
    them and the reviewer re-decides the same cases, which is what makes a
    repeated sweep expensive.
    """

    import yaml  # local: keeps the module importable without a registry

    path = Path(registry_path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[set[str]] = []
    for group in data.get("never_merge") or []:
        ids = {str(c).strip() for c in group if str(c).strip()}
        if len(ids) >= 2:
            out.append(ids)
    return out


def propose(
    entities: list[CanonicalEntity],
    cfg: DeepSeekConfig,
    *,
    client=None,
    never_merge: list[set[str]] | None = None,
) -> list[MergeGroup]:
    """String and LLM candidates, deduplicated, highest confidence first."""

    groups = llm_candidates(entities, cfg, client=client) + string_candidates(entities)
    if never_merge:
        kept = []
        for g in groups:
            ids = set(g.concept_ids)
            if any(len(ids & blocked) >= 2 for blocked in never_merge):
                log.info("[dedup] suppressed previously-rejected group: %s", ids)
                continue
            kept.append(g)
        groups = kept
    seen: dict[frozenset[str], MergeGroup] = {}
    for g in groups:
        key = frozenset(g.concept_ids)
        if key not in seen:
            seen[key] = g
        elif seen[key].source != g.source:
            # Independent agreement between methods is a real signal.
            seen[key].confidence = "hoch"
            seen[key].reason += f"; auch {g.source}: {g.reason}"
    order = {"hoch": 0, "mittel": 1, "niedrig": 2}
    return sorted(seen.values(), key=lambda g: (order.get(g.confidence, 3), g.canonical))


def render_report(groups: list[MergeGroup], entities: list[CanonicalEntity]) -> str:
    """Human-review report: one block per proposed group."""

    by_id = {e.concept_id: e for e in entities}
    lines = [
        "# Merge-Vorschläge",
        "",
        f"{len(groups)} Gruppen vorgeschlagen. Jede Gruppe muss bestätigt werden, "
        "bevor sie als `merge:` in die Registry geschrieben wird.",
        "",
    ]
    for i, g in enumerate(groups, 1):
        lines.append(f"## {i}. {g.canonical}  [{g.confidence}, {g.source}]")
        lines.append(f"*{g.reason}*")
        lines.append("")
        for cid in g.concept_ids:
            e = by_id.get(cid)
            mark = "**KANONISCH**" if cid == g.canonical else "→ einklappen"
            n = len(e.mentions) if e else 0
            note = " ".join((e.mentions[0].note if e and e.mentions else "").split())[:160]
            lines.append(f"- `{cid}` ({n} Belege) {mark}  \n  {note}")
        lines.append("")
    return "\n".join(lines)


def to_registry_merges(
    groups: list[MergeGroup], entities: list[CanonicalEntity]
) -> dict[str, str]:
    """Confirmed groups -> ``merge:`` entries (lowercased name -> concept_id)."""

    by_id = {e.concept_id: e for e in entities}
    out: dict[str, str] = {}
    for g in groups:
        for cid in g.concept_ids:
            if cid == g.canonical:
                continue
            e = by_id.get(cid)
            if not e:
                continue
            for name in [e.canonical_name, *e.aliases]:
                if name and slugify(name) != slugify(g.canonical.rsplit("/", 1)[-1]):
                    out[name.strip().lower()] = g.canonical
    return out
