# O4 — State-pass names with a parenthetical find their concept

Branch `feat/ontology-hygiene`. Third in the O-series. Cost $0; no state
re-run (the lookup happens at emit time, against cached state).

## Intent

`knowledge/conflicts/state_unmatched.md` lists 265 state-pass names that
matched no concept. 124 of them carry a parenthetical, because the state
model writes "Name (Erklärung)":

```
- threads/belagerung_von_breska_durch_die_untoten: Auranie (Oraniel)
- threads/belorus_der_stille_und_seine_untotenburg: Dodo (Marco's Guardian)
- threads/das_geoeffnete_buch_...: Ezua (Stimme im Amulett)
```

`state.py` `NameIndex.lookup` tries the exact name/alias (lowercased), then
the slug, and gives up. Wanted: on a miss, if the name has the shape
`Outer (Inner)`, try `Outer`, then `Inner`, through the same two tables, and
return the first **unique** hit. Ambiguity rule unchanged: a key two
concepts share maps to nothing.

This also stops a player name leaking through ("Marco's Guardian" is dropped,
"Dodo" resolves). Do not add other heuristics (no fuzzy matching, no article
stripping); one rule, measured by the unmatched count.

## Steps

1. **Test first**, in `services/kb/tests/test_state_ledger.py` (it already
   imports from `pnp_okf.state` and builds `CanonicalEntity` objects; reuse that):
   - entity `npcs/auranie` with alias `Oraniel`: `lookup("Auranie (Oraniel)") == "npcs/auranie"`.
   - entity `characters/dodo`: `lookup("Dodo (Marco's Guardian)") == "characters/dodo"`.
   - only the inner part matches: entity `npcs/ezua`, `lookup("Stimme (Ezua)") == "npcs/ezua"`.
   - outer part shared by two concepts and inner unknown → `None`.
   - name without parentheses that misses → `None` (unchanged).
2. `services/kb/src/pnp_okf/state.py` `NameIndex.lookup`: move the current
   loop into a private `_lookup_exact(self, name)`; `lookup` calls it, and on
   `None` matches `_PAREN = re.compile(r"^(.*?)\s*\((.+)\)\s*$")` and tries
   `group(1)`, then `group(2)`. Comment: O4, 124 of 265 unmatched names had a
   parenthetical. Import `re` if missing.
3. Full suite.

## Done when

- [ ] New tests pass; suite green except the known `last_run.json` test.
- [ ] `ruff check .` clean.
- [ ] After the shared HUMAN RUN: unmatched lines < 265 (record the new number in the PR).

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q tests/test_state_ledger.py
cd services/kb && .venv/Scripts/python.exe -m pytest -q
ruff check .
# after HUMAN RUN, from repo root:
grep -c "^- " knowledge/conflicts/state_unmatched.md
```
