"""GraphRAG-style entity summarization (docs/evolution/13, WP13.4).

Character.description gets folded per scene into `pending_notes`
(resolve.py, store.py) instead of overwriting a single description field —
a blind overwrite either blanks a prior session's note (Item 1, WP13.5
commit) or silently replaces it with a newer one. This module is a separate
step, run after ingest (not the per-scene hot path), that reads a
Character's existing `character_summary` + accumulated `pending_notes`, has
an LLM rewrite ONE cohesive bio, writes it back, clears the consumed notes,
and re-embeds — that bio is what embed.py actually embeds for Characters.
"""

import logging

from langchain_ollama import ChatOllama

from .config import NUM_CTX, SUMMARIZER_MODEL
from .embed import embed_entities

log = logging.getLogger("pnp_graph.summarize")

_PROMPT = (
    "Du schreibst eine kurze, zusammenhängende Charakterbeschreibung (2-4 Sätze, Deutsch) für "
    "eine TTRPG-Kampagne, basierend auf einer bisherigen Zusammenfassung (falls vorhanden) und "
    "neu beobachteten Eigenheiten/Verhaltensweisen aus späteren Sessions. Verschmelze beides zu "
    "EINEM zusammenhängenden Text — wiederhole keine Fakten doppelt, aber verliere auch keine. "
    "Nur der Beschreibungstext, keine Einleitung, keine Anführungszeichen.\n\n"
)


def _build_prompt(existing_summary: str | None, notes: list[str]) -> str:
    parts = [_PROMPT]
    if existing_summary:
        parts.append(f"Bisherige Zusammenfassung: {existing_summary}\n\n")
    parts.append("Neue Beobachtungen:\n" + "\n".join(f"- {n}" for n in notes))
    return "".join(parts)


def summarize_entities(driver) -> int:
    """Fold every Character's pending_notes into character_summary, clear the
    notes, and re-embed. Returns the count of characters updated."""
    llm = ChatOllama(model=SUMMARIZER_MODEL, temperature=0, num_ctx=NUM_CTX, reasoning=False)
    with driver.session() as db:
        rows = db.run(
            "MATCH (n:Entity{type:'Character'}) WHERE size(n.pending_notes) > 0 "
            "RETURN n.id AS id, n.character_summary AS summary, n.pending_notes AS notes",
        ).data()
        updated_ids: list[str] = []
        for row in rows:
            prompt = _build_prompt(row.get("summary"), row["notes"])
            try:
                new_summary = llm.invoke(prompt).content.strip()
            except Exception as exc:
                log.warning("summarization failed for %s (%s) — notes kept for next run",
                            row["id"], exc)
                continue
            if not new_summary:
                continue
            db.run(
                "MATCH (n:Entity{id:$id}) SET n.character_summary = $summary, n.pending_notes = []",
                id=row["id"], summary=new_summary,
            )
            updated_ids.append(row["id"])
    if updated_ids:
        embed_entities(driver, updated_ids)  # own session, after ours closes
    log.info("summarized %d/%d characters with pending notes", len(updated_ids), len(rows))
    return len(updated_ids)
