"""Ratchet on identity churn: how many concept ids a fresh resolve would
abandon, compared against what the last real ``pnp run`` wrote to the
registry.

``concept_id`` is derived from the LLM-extracted entity name (see
``_default_concept_id``, resolve.py), and the LLM rewords names between
extractions. Re-running ``resolve_entities`` against the *same* cached
extractions and the *same* registry should reproduce almost all of the
registry's ids; every id it fails to reproduce ("abandoned") is a concept a
plain re-run would silently rename or drop, detaching any hand-authored rule
in entity_rules.yaml that keys on the old id. This test measures that number
directly from the real corpus, using the cache (no LLM calls, no `pnp run`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pnp_okf.config import DeepSeekConfig
from pnp_okf.extract import _cache_key, _cache_path, _load_cached
from pnp_okf.ingest import load_transcripts
from pnp_okf.resolve import resolve_entities

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"
TRANSCRIPT_DIR = (
    Path(__file__).resolve().parents[4] / "pnp-crawl" / "transcripts_final"
)

pytestmark = pytest.mark.skipif(
    not REGISTRY.exists() or not TRANSCRIPT_DIR.is_dir(),
    reason="no bundle checked out",
)

# Measured 2026-09-06 against the real 66-session corpus (entity_registry.yaml
# as last written by `pnp run` at 2026-09-05T16:42Z, extractions from
# .cache/extract -- no LLM calls, the cache is fixed).
#
# What this number actually is: the registry lags entity_rules.yaml by one
# run. The rules file was edited at 2026-09-05T18:58 (b3f1af3, the v6 identity
# cleanup) *after* the registry was generated, so 35 of the registry's 1092
# ids are ones current rules would no longer produce. Confirmed concretely:
# the registry carries items/notiz_von_tyrex (the Whisper mishearing that the
# 54-dangling-link incident was named after) while a fresh resolve now yields
# items/notiz_von_tyrael. 33 of the 35 are single-mention concepts.
#
# So this is pending, un-applied rule work rather than LLM identity churn --
# the next `pnp run` should materialise those repairs and drive it toward 0.
# RE-MEASURE AFTER THE NEXT RUN and lower the baseline accordingly; it is a
# ratchet, so it may only go down.
#
# The metric only sees LLM rewording after a re-extraction repopulates the
# cache, which is exactly when it is wanted: run it between extraction and
# emit to preview a mass rename before any file is written.
#
# Writing the live-reanchor fix (resolve.py's _reanchor_to_live_alias) first
# RAISED this to 41: fuzzy-matching every mention against every live concept's
# accumulated alias history is prone to false positives on short/common names
# -- a PC "Gunther" folded into an NPC cat's alias "Gunther", and
# locations/berg_zebros (its own established concept) folded into
# locations/berge_von_zebros even though a human had already ruled the
# mountain and the fortress ruin distinct (apply_merges.py's REJECTED_NOTES).
# The guard at the call site -- only attempt the live-alias reanchor when the
# mention's own default_id is NOT already an established registry concept --
# removed all 6 false positives and returned this to 35. None of the 35 have
# alias history to reanchor against, so that fix is real but does not move
# this particular snapshot.
CHURN_BASELINE = 35


def _fresh_concept_ids() -> set[str]:
    cfg = DeepSeekConfig.from_env()
    transcripts = load_transcripts(TRANSCRIPT_DIR)
    tmap = {t.session_id: t for t in transcripts}
    extractions = {
        t.session_id: c
        for t in transcripts
        if (c := _load_cached(_cache_path(CACHE_DIR, t, _cache_key(t, cfg)), _cache_key(t, cfg)))
    }
    entities = resolve_entities(extractions, tmap, REGISTRY)
    return {e.concept_id for e in entities}


def test_fresh_resolve_does_not_abandon_more_registry_ids_than_the_baseline():
    registry_data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    known = {
        str(e.get("concept_id", "")).strip()
        for e in registry_data.get("entities") or []
    }
    known.discard("")

    abandoned = known - _fresh_concept_ids()

    assert len(abandoned) <= CHURN_BASELINE
