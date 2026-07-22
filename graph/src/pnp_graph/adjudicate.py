"""LLM identity adjudication (audit v6): semantic merge/distinct verdicts for
identity candidates deterministic fuzzy matching can't settle.

Two candidate sources (queued on `Resolver.pending_candidates` during resolve):
- gray-band mints: a new entity whose best fuzzy ratio against an existing
  same-type entry lands in config.ADJUDICATE_GRAY_BAND (Breska vs Breschka —
  merge; Tindrael vs Timrell — distinct);
- alias conflicts: a model-supplied Character alias that already names a
  different known character (the F1 wrong-merge path).

One batched structured-output call per session, run between resolve_graph and
write_session. Merges rewrite the alias registry and remap ids in the resolved
dict; distinct verdicts are memoized (`adjudicated_distinct`) so a pair is
never re-asked. Every verdict lands in state/review/<sid>/adjudications.jsonl
with its reasoning — the human-in-the-loop trail the audit asks for.
Adjudication failure degrades safely: nothing merges, both entities stay.
"""

import json
import logging

from pydantic import BaseModel, Field

from .config import STATE_DIR

log = logging.getLogger("pnp_graph.adjudicate")


class MergeVerdict(BaseModel):
    candidate_index: int = Field(description="Index of the candidate pair this verdict answers")
    same_entity: bool = Field(description="True ONLY if NEW and EXISTING refer to the same in-fiction entity")
    reasoning: str = Field(description="One sentence grounded in the provided context, not in name similarity alone")


class MergeVerdicts(BaseModel):
    verdicts: list[MergeVerdict] = []


def build_adjudicator():
    from .extract import _make_chat_llm, _structured_method  # shared provider wiring
    return _make_chat_llm().with_structured_output(MergeVerdicts, method=_structured_method())


_PROMPT = (
    "You adjudicate entity identity for a TTRPG (Daggerheart) campaign knowledge graph built "
    "from German ASR (Whisper) transcripts. Spelling variants of one name are common "
    "(Breska/Breschka/Brechka = one village), but similar-sounding names can also be "
    "different figures (a tomb guardian 'Tindrael' vs a fleeing child 'Timrell'). "
    "For each numbered pair below, decide whether NEW and EXISTING refer to the SAME "
    "in-fiction entity. Judge by role and description context; when the context shows two "
    "different figures, answer false even if the names are near-identical. If there is no "
    "context to judge by, answer false — a wrong merge is worse than a duplicate. "
    "Return exactly one verdict per pair, carrying that pair's index.\n\n"
)


def _describe(eid: str, section: str, resolved: dict, resolver) -> str:
    parts = [f"'{resolver.registry[section].get(eid, {}).get('canonical', eid)}'", f"[{eid}]"]
    entry = resolver.registry[section].get(eid, {})
    if entry.get("aliases"):
        parts.append(f"(aka {', '.join(entry['aliases'][:4])})")
    ent = next((e for e in resolved["entities"] if e["id"] == eid), None)
    if ent:
        notes = "; ".join(ent["props"].get("pending_notes", [])[:3]) \
            or ent["props"].get("description", "") or ent["props"].get("summary", "")
        if notes:
            parts.append(f"— {notes[:250]}")
    return " ".join(parts)


def _candidate_listing(candidates: list[dict], resolved: dict, resolver) -> str:
    lines = []
    for i, c in enumerate(candidates):
        kind = "alias conflict" if c.get("source") == "alias-conflict" else f"fuzzy {c['ratio']}"
        lines.append(
            f"{i}: type={c['section'][:-1]} ({kind}) "
            f"NEW {_describe(c['new_id'], c['section'], resolved, resolver)} "
            f"vs EXISTING {_describe(c['existing_id'], c['section'], resolved, resolver)}")
    return "\n".join(lines)


def _remap_ids(resolver, resolved: dict, remap: dict[str, str]) -> None:
    """Rewrite the resolved dict after merges: entities re-keyed to the kept id
    (props unioned when both halves were minted this session), edges re-pointed,
    self-loops and duplicates dropped."""

    def target(eid: str) -> str:
        while eid in remap:
            eid = remap[eid]
        return eid

    by_id: dict[str, dict] = {}
    for e in resolved["entities"]:
        nid = target(e["id"])
        if nid != e["id"]:
            e["id"] = nid
            canon = resolver.canonical(nid)
            if canon and "name" in e["props"]:
                e["props"]["name"] = canon
        if nid in by_id:  # both halves of a merged pair existed this session
            old, new = by_id[nid]["props"], e["props"]
            aliases = sorted(set(old.get("aliases", [])) | set(new.get("aliases", [])))
            if aliases:
                old["aliases"] = aliases
            chunks = sorted(set(old.get("evidence_chunks", [])) | set(new.get("evidence_chunks", [])))
            if chunks:
                old["evidence_chunks"] = chunks
            notes = old.get("pending_notes", []) + [
                n for n in new.get("pending_notes", []) if n not in old.get("pending_notes", [])]
            if notes:
                old["pending_notes"] = notes
        else:
            by_id[nid] = e
    resolved["entities"] = list(by_id.values())

    edges, seen = [], set()
    for r in resolved["edges"]:
        r["start_id"], r["end_id"] = target(r["start_id"]), target(r["end_id"])
        key = (r["start_id"], r["type"], r["end_id"])
        if r["start_id"] == r["end_id"] or key in seen:
            continue
        seen.add(key)
        edges.append(r)
    resolved["edges"] = edges


def apply_verdicts(resolver, resolved: dict, candidates: list[dict],
                   verdicts: list[MergeVerdict], session_id: str) -> dict[str, str]:
    review_dir = STATE_DIR / "review" / session_id
    review_dir.mkdir(parents=True, exist_ok=True)
    by_index = {v.candidate_index: v for v in verdicts}
    remap: dict[str, str] = {}
    with (review_dir / "adjudications.jsonl").open("a", encoding="utf-8") as f:
        for i, cand in enumerate(candidates):
            v = by_index.get(i)
            f.write(json.dumps(
                {**cand, "same_entity": v.same_entity if v else None,
                 "reasoning": v.reasoning if v else "no verdict returned — left unmerged"},
                ensure_ascii=False) + "\n")
            if v is None:
                continue
            section = cand["section"]
            if v.same_entity:
                if cand.get("source") == "alias-conflict":
                    # the alias's separate entry folds into the character carrying it
                    keep, drop = cand["new_id"], cand["existing_id"]
                else:
                    # the provisional new mint folds into the established entry
                    keep, drop = cand["existing_id"], cand["new_id"]
                log.info("adjudicated MERGE: %s -> %s (%s)", drop, keep, v.reasoning)
                resolver.merge_entries(section, keep, drop)
                remap[drop] = keep
            else:
                resolver.mark_distinct(section, cand["new_id"], cand["existing_id"])
                if cand.get("source") == "alias-conflict":
                    # the alias names a different figure — strip it off this node
                    ent = next((e for e in resolved["entities"] if e["id"] == cand["new_id"]), None)
                    if ent and cand["surface"] in ent["props"].get("aliases", []):
                        ent["props"]["aliases"].remove(cand["surface"])
    if remap:
        _remap_ids(resolver, resolved, remap)
    return remap


def adjudicate_session(resolver, resolved: dict, session_id: str,
                       adjudicator=None) -> dict[str, str]:
    """Drain queued candidates, get one batched verdict call, apply it.
    Returns the id remap ({dropped_id: kept_id}); empty when nothing merged."""
    candidates = resolver.drain_candidates()
    if not candidates:
        return {}
    adjudicator = adjudicator if adjudicator is not None else build_adjudicator()
    prompt = _PROMPT + _candidate_listing(candidates, resolved, resolver)
    try:
        result = adjudicator.invoke(prompt)
        verdicts = result.verdicts if result else []
    except Exception as exc:  # degrade safely: no merges, both entities stay
        log.warning("adjudication failed (%s) — %d candidates left unmerged",
                    exc, len(candidates))
        verdicts = []
    remap = apply_verdicts(resolver, resolved, candidates, verdicts, session_id)
    resolver.save()
    log.info("adjudicated %d candidates: %d merged", len(candidates), len(remap))
    return remap
