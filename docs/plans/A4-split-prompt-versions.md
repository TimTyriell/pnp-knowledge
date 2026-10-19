# A4 — Separate extraction and synthesis prompt versions, pin prompt text

| | |
|---|---|
| Branch | `chore/split-prompt-versions` |
| Base | `origin/main` |
| Depends on | — |
| Cost | **Must be $0.** If any cache key changes, this plan has failed. See the invariance test |
| Size | S |

## Goal

1. Replace the one `PROMPT_VERSION = "6"` in `prompts.py` with
   `EXTRACT_PROMPT_VERSION = "6"` and `SYNTH_PROMPT_VERSION = "6"`.
   - Today a synthesis-only wording fix needs a bump, and that bump
     re-extracts the whole corpus (~$6.50) and churns concept ids
     (PIPELINE.md §4, §6). A synthesis prose tweak shouldn't be an identity
     event.
2. Add a test that pins a hash of each prompt's **text and schema** to its
   version.
   - Today PIPELINE.md §6 consequence 2 says: "The prompt *text* is not in
     the key … change prompt content without bumping and the cache silently
     serves stale results." The test turns that silent trap into a red test.
3. **Every existing cache key stays byte-identical.** The version values stay
   `"6"`, and the payload format of both `_cache_key` functions is unchanged.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c chore/split-prompt-versions origin/main
```

### 2. Record today's keys **before** changing anything

Run from `services/kb` on the fresh branch (no edits yet):

```bash
.venv/Scripts/python.exe - <<'PY'
from pnp_okf.config import DeepSeekConfig
from pnp_okf.extract import _cache_key as ek
from pnp_okf.synthesize import _cache_key as sk
from pnp_okf.models import SessionTranscript, Segment, CanonicalEntity, EntityType, MentionRef
cfg = DeepSeekConfig(api_key="x", model="deepseek-v4-pro", base_url="https://example.invalid")
t = SessionTranscript(session_id="2025-03-26_RF_x", date="2025-03-26", url="u",
                      segments=[Segment(start=0, end=1, speaker="A", text="Hallo")])
e = CanonicalEntity(concept_id="npcs/hexe", type=EntityType.NPC, canonical_name="Hexe",
                    mentions=[MentionRef(session_id="s", date="2025-03-26", url="u", citation_ts="00:00:01", note="n")])
print("extract", ek(t, cfg))
print("synth", sk(e, cfg, "", "", ""))
PY
```

Write both printed keys into the invariance test below. (This heredoc has
no backslashes, so it is safe; PIPELINE.md §11 trap 2.)

Make sure `PNP_EXTRACT_FREEZE_BEFORE` / `PNP_EXTRACT_FREEZE_VERSION` aren't
set in the shell (the session date may sit before the cutoff). Run
`unset PNP_EXTRACT_FREEZE_BEFORE PNP_EXTRACT_FREEZE_VERSION` first, or note
the values. The test below clears them with `monkeypatch`.

### 3. `prompts.py`

Replace the module docstring's second paragraph and the constant:

```python
"""German prompts for the extraction and synthesis stages.

Two versions, because the two stages invalidate very different things.
Bumping EXTRACT_PROMPT_VERSION re-extracts every session (~$6.50) and
resamples entity names, which moves concept ids (PIPELINE.md §4). Bumping
SYNTH_PROMPT_VERSION only re-synthesises entity prose. A prose tweak must
not be an identity event. tests/test_prompt_pins.py fails when a prompt's
text changes without its version moving.
"""

from __future__ import annotations

from pnp_okf.models import SUBTYPES

EXTRACT_PROMPT_VERSION = "6"
SYNTH_PROMPT_VERSION = "6"
```

Remove `PROMPT_VERSION` entirely. No alias: an alias invites the next
person to bump the wrong one.

### 4. Callers

- `extract.py`: import `EXTRACT_PROMPT_VERSION`; replace both uses in
  `_frozen_prompt_version`. Update the docstrings that say `PROMPT_VERSION`
  to `EXTRACT_PROMPT_VERSION`.
- `synthesize.py`: import `SYNTH_PROMPT_VERSION`; `"v": SYNTH_PROMPT_VERSION`
  in `_cache_key`. **Keep the dict key `"v"`**; renaming it changes every
  synth key.
- `cli.py:91` comment: say `EXTRACT_PROMPT_VERSION`.
- `tests/test_identity_spelling_and_freeze.py`: import and compare
  `EXTRACT_PROMPT_VERSION`.
- `tests/test_synthesize_cache.py`: update the docstring wording only.
- `grep -rn "PROMPT_VERSION" services/ docs/architecture/PIPELINE.md`. Then
  update PIPELINE.md §6 (the cache-key code blocks and consequence 2: "now
  caught by tests/test_prompt_pins.py") and §13 ("bump
  EXTRACT_PROMPT_VERSION … budgeted event; SYNTH_PROMPT_VERSION re-synthesis
  only").

### 5. Tests: `services/kb/tests/test_prompt_pins.py` (new)

```python
"""Prompt text is pinned to its version (A4).

The cache keys carry only the version number, not the prompt text
(PIPELINE.md §6), so editing a prompt without bumping its version serves
stale cached output forever. This makes that edit a red test instead. When
it fails: if the change is deliberate, bump the matching *_PROMPT_VERSION,
add the new hash below and budget the run (extraction ~$6.50 + id churn;
synthesis cheaper, no churn). Never "fix" it by updating the hash alone.
"""

from __future__ import annotations

import hashlib
import json

from pnp_okf import prompts
from pnp_okf.models import SessionExtraction


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


EXTRACT_PINS = {"6": "<fill>"}
SYNTH_PINS = {"6": "<fill>"}


def test_extract_prompt_matches_its_version():
    assert EXTRACT_PINS.get(prompts.EXTRACT_PROMPT_VERSION) == extract_fingerprint(), (
        "EXTRACT_SYSTEM / EXTRACT_USER_TEMPLATE / SessionExtraction schema changed "
        "without bumping EXTRACT_PROMPT_VERSION -- see this file's docstring."
    )


def test_synth_prompt_matches_its_version():
    assert SYNTH_PINS.get(prompts.SYNTH_PROMPT_VERSION) == synth_fingerprint(), (
        "A SYNTH_* prompt changed without bumping SYNTH_PROMPT_VERSION -- see this file's docstring."
    )
```

Fill `<fill>` by running
`.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); import test_prompt_pins as t; print(t.extract_fingerprint(), t.synth_fingerprint())"`
from `services/kb`.

Also note in the docstring: the schema of `EntityMention` (including the
`EntityType` enum) is part of the extract fingerprint, so adding a type to
`EntityType` correctly trips this test. T5/T6 deliberately do **not** add
`Thread` to `EntityType` for that reason.

Then the **invariance test** (same file):

```python
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
    assert ek(t, cfg) == "<extract key from step 2>"
    assert sk(e, cfg, "", "", "") == "<synth key from step 2>"
```

### 6. Verify

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
```

If you have a local `.env` with a key, also run
`.venv/Scripts/python.exe -m pnp_okf.cli run --estimate --transcripts ../../../pnp-crawl/transcripts_final`.
It must report **0 uncached** extraction and synthesis calls for the 68
ingested sessions. (New transcripts after 2026-09-22 will be uncached;
that is expected and unrelated.) `--estimate` makes no LLM calls.

### 7. Commit and PR

Message: `chore(kb): split prompt versions per stage and pin prompt text`

The PR body states: "Cache keys verified unchanged (invariance test plus
`--estimate` output)."

## Done when

- [ ] `PROMPT_VERSION` no longer exists anywhere in `services/`.
- [ ] Pin and invariance tests green; `--estimate` shows 0 uncached for existing sessions.
- [ ] PIPELINE.md §6 and §13 updated.
