# Handoff: spelling/name-variant issues in OKF bundle

Follow-up to `2026-08-29-bundle-quality.md` (identity/link audit, done, branch
`fix/kb-autolink-and-entity-dedup`, merged into main tests at commit `d90b730`).
That audit fixed structural dupes/links. **Not fixed**: name-spelling drift
from Whisper transcription — separate root cause, separate fix surface.

## Where this lives

- `entity_rules.yaml`: `merge:` (name variant → concept_id), `canonical_name:`
  (pins display title), `never_merge:` (blocks fuzzy pass from folding two
  concepts). Hand-authored, never overwritten by pipeline.
- `resolve.py::merge_near_duplicates()` — the fuzzy Whisper-spelling-drift
  merge pass. Separate from initial entity creation; read this first, it's
  the actual mechanism (not string-exact `merge:` matching).
- Test pattern: ratchet-with-named-baseline, see any `services/kb/tests/
  test_rules_applied.py` function for the shape. Reuse it, don't invent a
  new pattern.

## Update 2026-08-30 (branch `fix/kb-spelling-drift`)

Handled a different slice of this problem: name-spelling drift in *prose*
(the node identity was right, the sentence around it was wrong) rather than
merge/link identity work. Added the missing mechanism (`spelling:` rules,
see `entity_rules.yaml` and `docs/audits/2026-08-30-spelling-sweep.md`) and
fixed the reported Zebros/Willauch/Landra/Voras cases plus everything the
same method surfaced (Breska, Tarvok, Adeliga, Slix, Korn, Huludan). The
items below are untouched by this branch — still open for whoever picks up
next.

## Known instances (found during prior audit, not resolved)

- `miaomani` / `miyamani` — `never_merge:` blocks them, but the *justification
  comment* is stale (says "Halbling im Zirkus", generated node is a Katari
  mit Armbrust now). Decision may still be right; comment is wrong. Needs a
  fresh look at both nodes' actual content before touching the rule.
- `locations/ringtal` — title says "Kleinringtal", body describes a
  different, larger place also called "Ringtal" — one slug, two real places.
  Not a spelling dupe, a missing split. `split:` rule needed once GM confirms
  they're distinct.
- Confirmed correctly separate (don't touch): `miko`/`myko` (Katzenvolk vs.
  Fungrill), `sage`/`sange`.
- Full GM-open list is in Teil 2.G of `2026-08-29-bundle-quality.md` — some of
  those (`vora`/`voras`, `gilde_in_breska`, etc.) are name-variant-shaped too,
  worth re-checking against the "is it spelling or is it two entities"
  question before assuming either way.

## Rules of engagement (same as prior audit)

- Never hand-edit a bundle `.md` file — fixes go in `entity_rules.yaml` /
  `sources/Kanon_Entscheidungen.md`, then `pnp run` regenerates.
- Ambiguous identity → GM question in `Kanon_Entscheidungen.md`, not a guess.
- New branch off `main`: `fix/kb-<short-name>`.
- Every finding needs both a test (ratchet or hard assertion, your call) and
  a fix — don't leave one without the other, that was the whole point of the
  last audit's Schritt 0.
