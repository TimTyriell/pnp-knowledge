"""Prompt text is pinned to its version (A4).

The cache keys carry only the version number, not the prompt text
(PIPELINE.md §6), so editing a prompt without bumping its version serves
stale cached output forever. This makes that edit a red test instead. When
it fails: if the change is deliberate, bump the matching *_PROMPT_VERSION,
add the new hash below and budget the run (extraction ~$6.50 + id churn;
synthesis cheaper, no churn). Never "fix" it by updating the hash alone.

The schema of EntityMention (including the EntityType enum) is part of the
extract fingerprint, so adding a type to EntityType correctly trips this
test. T5/T6 deliberately do not add Thread to EntityType for that reason.
"""

from __future__ import annotations

import hashlib
import json

from pnp_okf import prompts
from pnp_okf.models import SessionExtraction
from pnp_okf.state import SessionState


def _sha(*parts: str) -> str:
    return hashlib.sha256("\n\x00\n".join(parts).encode("utf-8")).hexdigest()[:16]


def extract_fingerprint() -> str:
    schema = json.dumps(SessionExtraction.model_json_schema(), sort_keys=True, ensure_ascii=False)
    return _sha(prompts.EXTRACT_SYSTEM, prompts.EXTRACT_USER_TEMPLATE, schema)


def synth_fingerprint() -> str:
    return _sha(
        prompts.SYNTH_SYSTEM,
        json.dumps(prompts.SYNTH_TIER_GUIDANCE, sort_keys=True, ensure_ascii=False),
        prompts.SYNTH_USER_TEMPLATE,
        prompts.SYNTH_SOURCES_TEMPLATE,
        prompts.SYNTH_SECONDARY_TEMPLATE,
        prompts.SYNTH_EXCERPTS_TEMPLATE,
    )


def state_fingerprint() -> str:
    schema = json.dumps(SessionState.model_json_schema(), sort_keys=True, ensure_ascii=False)
    return _sha(prompts.STATE_SYSTEM, prompts.STATE_USER_TEMPLATE, schema)


EXTRACT_PINS = {"6": "6b9e8b098e4f7ff6"}
SYNTH_PINS = {"6": "68c15bec59a62702"}
STATE_PINS = {"1": "e27b22a5f6be2658"}


def test_extract_prompt_matches_its_version():
    assert EXTRACT_PINS.get(prompts.EXTRACT_PROMPT_VERSION) == extract_fingerprint(), (
        "EXTRACT_SYSTEM / EXTRACT_USER_TEMPLATE / SessionExtraction schema changed "
        "without bumping EXTRACT_PROMPT_VERSION -- see this file's docstring."
    )


def test_synth_prompt_matches_its_version():
    assert SYNTH_PINS.get(prompts.SYNTH_PROMPT_VERSION) == synth_fingerprint(), (
        "A SYNTH_* prompt changed without bumping SYNTH_PROMPT_VERSION -- see this file's docstring."
    )


def test_state_prompt_matches_its_version():
    assert STATE_PINS.get(prompts.STATE_PROMPT_VERSION) == state_fingerprint(), (
        "A STATE_* prompt or the SessionState schema changed without bumping "
        "STATE_PROMPT_VERSION -- see this file's docstring."
    )


def test_cache_keys_did_not_move(monkeypatch):
    """Splitting the version constant must not touch a single cached key."""
    monkeypatch.delenv("PNP_EXTRACT_FREEZE_BEFORE", raising=False)
    monkeypatch.delenv("PNP_EXTRACT_FREEZE_VERSION", raising=False)
    from pnp_okf.config import DeepSeekConfig
    from pnp_okf.extract import _cache_key as ek
    from pnp_okf.models import CanonicalEntity, EntityType, MentionRef, Segment, SessionTranscript
    from pnp_okf.synthesize import _cache_key as sk

    cfg = DeepSeekConfig(api_key="x", model="deepseek-v4-pro", base_url="https://example.invalid")
    t = SessionTranscript(session_id="2025-03-26_RF_x", date="2025-03-26", url="u",
                          segments=[Segment(start=0, end=1, speaker="A", text="Hallo")])
    e = CanonicalEntity(concept_id="npcs/hexe", type=EntityType.NPC, canonical_name="Hexe",
                        mentions=[MentionRef(session_id="s", date="2025-03-26", url="u",
                                             citation_ts="00:00:01", note="n")])
    assert ek(t, cfg) == "1db07dfcf4cf3f1e"
    assert sk(e, cfg, "", "", "") == "8b75d045dd1fd941"
