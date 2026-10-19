# T3 — Daggerheart rules glossary for the prompts

| | |
|---|---|
| Branch | `feat/rules-glossary` |
| Base | `origin/main` (after A4 merged) |
| Depends on | A4 (separate prompt versions; the pin test there must stay green) |
| Design | [T00 §4.9](T00-tracking-model.md) |
| Cost | $0. This plan only *defines* the glossary and its test. Wiring it into extraction or synthesis is a budgeted event (B2 / a synth bump) |
| Size | S |

## Goal

Add `RULES_GLOSSARY` to `services/kb/src/pnp_okf/prompts.py`: a short German
Daggerheart cheat sheet with every line checked against the SRD. T5 (state
pass) uses it from day one. B2 adds it to `EXTRACT_SYSTEM` at the next
budgeted re-extraction.

## Why

The extractor misreads table mechanics as world facts:

- `events/sturz_von_dodo` says "überlebt mit einem Hitpoint". In the
  transcript the player of Dodo *marks* 1 HP of damage ("dann ist es ein Hitpoint"). In
  Daggerheart you mark HP when hurt; you don't "have one left".
- Item names carry rules jargon: "Heiltrank (1w4)", "Grüner Trank (drei
  Hope)", "Tier-2-Schwert".
- The KB's `Domain` type means *cosmological realms* (Splitterwelt, Circle
  Below), but Daggerheart "Domains" are card decks (Arcana, Blade, …).
  Without being told, a model conflates the two.

Dice rolls themselves are **not** tracked (T00 §4.9). The glossary exists so
the model understands mechanics, not so it records them.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c feat/rules-glossary origin/main
```

### 2. Add the constant to `prompts.py`

Insert below `EXTRACT_SYSTEM = ...` and above `EXTRACT_USER_TEMPLATE`. **Do
not** reference it from `EXTRACT_SYSTEM` or `SYNTH_SYSTEM` in this plan. That
would change the prompt text and trip A4's pin test (as intended).

```python
# Daggerheart mechanics, so a model reading a table transcript stops turning
# rules talk into world facts ("überlebt mit einem Hitpoint" was a damage
# roll; "Heiltrank (1w4)" is a stat, not a name). Every line is checked
# against the SRD -- see docs/plans/T3-rules-glossary.md for the sources.
# Used by the state pass (T5) now; extraction picks it up at the next
# budgeted re-extraction (B2), synthesis at its next version bump.
RULES_GLOSSARY = """\
Regelbegriffe (Daggerheart) -- das ist Spielmechanik, KEIN Weltgeschehen:
- Hit Points (HP) werden bei Schaden MARKIERT ("einen Hitpoint markieren" =
  1 Schaden genommen). Wer seinen LETZTEN HP markiert, fällt und macht einen
  Todeszug (death move). "Ein Hitpoint" heißt fast nie "nur noch ein HP übrig".
- Schadensschwellen: unter Major = 1 HP, ab Major = 2 HP, ab Severe = 3 HP.
- Stress wird ebenfalls markiert (Anstrengung, Kosten von Fähigkeiten). Letzter
  Stress markiert = verwundbar (Vulnerable).
- Rüstungsplätze (Armor Slots) markieren senkt den Schaden um eine Schwelle.
- Duality Dice: zwei W12, Hoffnung (Hope) und Furcht (Fear). "Mit Hope" /
  "mit Fear" beschreibt nur, welcher Würfel höher war.
- Hope ist eine Ressource der Spieler (max. 6), Fear eine der Spielleitung
  (max. 12). Sie sind keine Gegenstände und keine Gefühle der Figuren.
- Evasion ist der Verteidigungswert; "Difficulty" ist die Schwierigkeit eines
  Wurfs.
- "Domains" der Regeln (Arcana, Blade, Bone, Codex, Grace, Midnight, Sage,
  Splendor, Valor) sind Kartenstapel für Fähigkeiten -- KEINE Reiche oder
  Ebenen der Spielwelt.
- Tier 1-4 und Level sind Stufen der Spielercharaktere, keine Ränge in der Welt.
- Würfelangaben (1W4, 2W6+3, d12) und Zahlen wie "drei Hope" gehören NIE in
  den Namen einer Entität.
- Spotlight, Downtime, Rast, Countdown, Fear-Move, Tag-Team-Wurf sind
  Spielleitungs- und Tischbegriffe.
"""
```

### 3. Verify each line against the SRD (record it in the PR body)

The SRD lives in the sibling repo:
`../daggerheart-srd/.build/01_pdf/DH-SRD-2025-09-09.md`. For each glossary
bullet, find the supporting section and paste the heading and line number
into the PR body as a table. Expected anchors (verified 2026-10-18; line
numbers may drift):

| Glossary line | SRD section | ≈ line |
|---|---|---|
| HP marked, last HP → fall + death move | `### HIT POINTS & DAMAGE THRESHOLDS` | 2105 |
| Thresholds 1/2/3 HP | same section | 2109–2112 |
| Stress, last Stress → Vulnerable | `## STRESS` | 2128 |
| Armor slot lowers severity by one threshold | e.g. `_Unyielding:_`, `_Partners-in-Arms:_` | 777, 851 |
| Duality Dice = 2d12 Hope/Fear | intro paragraph | 40 |
| Hope max 6, Fear max 12 | `### HOPE & FEAR` | 2074–2093 |
| Evasion | `### EVASION` | 2099 |
| 9 Domain decks | `## DOMAINS` | 177 |
| Tier 1–4 | `#### TIER 1` … `#### TIER 4` | 511–727 |
| Death move | `## DEATH` | 2287 |

If any line can't be supported, **delete the line**; don't soften it.

### 4. Test: `services/kb/tests/test_prompts_glossary.py` (new file)

```python
"""RULES_GLOSSARY stays a short, mechanics-only cheat sheet (T3)."""

from __future__ import annotations

from pnp_okf.prompts import EXTRACT_SYSTEM, RULES_GLOSSARY, SYNTH_SYSTEM


def test_glossary_is_short():
    # A prompt prefix is paid on every call; past ~25 lines it stops being a
    # cheat sheet and starts competing with the actual instructions.
    assert len(RULES_GLOSSARY.strip().splitlines()) <= 25


def test_glossary_names_the_misreadings_it_exists_for():
    for term in ("markiert", "Hope", "Fear", "Domains", "Tier", "Würfel"):
        assert term in RULES_GLOSSARY, term


def test_glossary_is_not_yet_in_extraction_or_synthesis():
    # Wiring it in changes the prompt text, which is a budgeted re-extraction
    # (B2) or a synthesis version bump -- never a side effect of this plan.
    assert RULES_GLOSSARY not in EXTRACT_SYSTEM
    assert RULES_GLOSSARY not in SYNTH_SYSTEM
```

### 5. Verify

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
```

A4's prompt-pin test must stay green; this plan doesn't change any existing
prompt string.

### 6. Commit and PR

Message: `feat(kb): add an SRD-checked Daggerheart rules glossary for prompts`

The PR body holds the SRD table from step 3. Request **human review of the
German wording** (the GM knows how the table talks).

## Done when

- [ ] Constant merged, every line SRD-cited in the PR, wording approved by the human.
- [ ] `test_glossary_is_not_yet_in_extraction_or_synthesis` green.

## Follow-ups (not this plan)

- T5 puts `RULES_GLOSSARY` into the state-pass system prompt.
- B2 deletes the third test and appends the glossary to `EXTRACT_SYSTEM` in
  the same commit that bumps `EXTRACT_PROMPT_VERSION`.
