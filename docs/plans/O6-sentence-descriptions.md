# O6 — A description is a sentence, not a hard cut

Branch `feat/ontology-hygiene`. Second in the O-series. Cost $0 (the next
warm re-emit rewrites frontmatter only).

## Intent

1379 of 1472 concepts end their `description` in a mid-word "…"
(`"…Er ist e…"`). OKF SPEC §4.1 wants a short summary sentence; the wiki
and the API listing show it. Cause: `emit.py` `_short_desc` cuts at a fixed
character count:

```python
def _short_desc(text: str, limit: int = 140) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1].rstrip() + "…"
```

Wanted, in this order:
1. The **first sentence**, if it fits in `limit`.
2. Otherwise the text cut at the **last space** before `limit`, plus "…".
3. Text already ≤ `limit` with one sentence: unchanged.

A sentence ends at `.`, `!` or `?` followed by whitespace and an upper-case
letter (incl. ÄÖÜ) or an opening quote. German abbreviations must not end a
sentence: a period right after a **single letter** ("z. B.", "d. h.",
"u. a.") is not a sentence end. Keep it a regex; no NLP library.

`_short_desc` has several callers (entity, session, thread descriptions and
the session index blurb with `limit=100`). All of them benefit; do not add a
parameter.

## Steps

1. **Test first**, in `services/kb/tests/test_description.py` (import
   `_short_desc` from `pnp_okf.emit` next to the existing imports):
   - `"Kurz."` → `"Kurz."`
   - `"Erster Satz. Zweiter Satz."` → `"Erster Satz."`
   - `"Er trägt z. B. ein Schwert. Danach mehr."` → `"Er trägt z. B. ein Schwert."`
   - a single 200-char sentence of words → ends with `"…"`, length ≤ 140, and
     the character before `"…"` is not a space and the cut is at a word boundary
     (the text without "…" is a prefix of the input ending where the input has a space).
   - a first sentence longer than 140 → falls back to the word-boundary cut.
   - whitespace/newlines are collapsed as before.
2. `services/kb/src/pnp_okf/emit.py` `_short_desc`: implement. Suggested shape:
   ```python
   # One summary sentence (OKF §4.1). A period after a single letter is an
   # abbreviation ("z. B."), not a sentence end. O6: the old fixed cut left
   # 1379 of 1472 descriptions ending mid-word.
   _SENTENCE_END = re.compile(r"(?<![\s(]\w)(?<!^\w)[.!?](?=\s+[A-ZÄÖÜ„\"])")
   ```
   Find the first match; if `end <= limit` return `one_line[:end]`. Else if
   `len(one_line) <= limit` return `one_line`. Else
   `cut = one_line[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")` + "…".
   Verify the lookbehinds against your tests; adjust only the regex.
3. Full suite. `test_description.py` already has description tests via
   `emit_entity` — they must stay green. If a bundle-reading test pins an exact
   description string, STOP and report.

## Done when

- [ ] New tests pass; suite green except the known `last_run.json` test.
- [ ] `ruff check .` clean.
- [ ] After the shared HUMAN RUN: descriptions ending in "…" fall from 1379 to well under 400.

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q tests/test_description.py
cd services/kb && .venv/Scripts/python.exe -m pytest -q
ruff check .
# after HUMAN RUN, from repo root:
grep -rh "^description:" knowledge/bundle/splitter_des_ewigen --include=*.md | grep -c "…$"
```
