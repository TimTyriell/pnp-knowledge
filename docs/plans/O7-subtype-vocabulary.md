# O7 — A subtype outside its type's vocabulary is dropped

Branch `feat/ontology-hygiene` (shared by O1–O7, one commit per plan; see
README). Implement **first** of the O-series. Cost $0 code; the shared HUMAN
RUN in O1 re-synthesises the few entities whose subtype changes.

## Intent

`SUBTYPES` (`models.py`) is a closed vocabulary per type, and
`validate.py` already reports `invalid_subtypes`. The bundle still carries
foreign values: `factions/*` with `Wildnis`, `npcs/*` with `Volk`, `Bande`,
`Heiliger`, `characters/*` and `domains/*` with `Sonstiges`.

Cause, in `resolve.py` `resolve_entities`: a mention can be folded into a
concept of another directory (a `merge:` rule, or a person fold), and the
entity type is then taken from the directory (`DIR_TO_TYPE`) — but the
subtype is copied verbatim from the mention, which was typed by the model
as something else. Two places copy it: the `CanonicalEntity(...)`
constructor (`subtype=mention.subtype.strip()`) and the later
`if not entity.subtype and mention.subtype.strip():` adoption.

Wanted: an entity only ever carries a subtype from **its own** type's list;
anything else becomes `""`. Types with no list (Character, NPC, Domain)
carry none. No prompt change, no version bump.

## Steps

1. **Test first.** New file `services/kb/tests/test_subtype_vocab.py`. Model
   the setup on an existing resolve test that writes an `entity_rules.yaml`
   into `tmp_path` and calls `resolve_entities` (e.g. `tests/test_split.py` or
   `tests/test_identity.py` — reuse their helper shape, do not invent a new
   fixture style). Cases:
   - mention `type=Location, subtype="Wildnis"`, rules `merge: {"Wilde Horde": factions/wilde_horde}` → resolved entity type Faction, `subtype == ""`.
   - mention `type=Item, subtype="Waffe"` → `subtype == "Waffe"` (valid stays).
   - mention `type=NPC, subtype="Volk"` → `subtype == ""` (NPC has no list).
   - two mentions of one Location, first `subtype=""`, second `"Gebäude"` → `"Gebäude"` (adoption still works).
   Run: tests fail.
2. `services/kb/src/pnp_okf/resolve.py`: add a helper near the top-level
   helpers:
   ```python
   def _valid_subtype(entity_type: EntityType, subtype: str) -> str:
       """``subtype`` if it is in the type's closed list, else ``""`` (O7)."""
       s = subtype.strip()
       return s if s in SUBTYPES.get(entity_type, ()) else ""
   ```
   Import `SUBTYPES` from `pnp_okf.models` if not imported. Comment *why*:
   a cross-directory merge keeps the mention's subtype (`Wildnis` on a faction).
3. In `resolve_entities`: constructor uses
   `subtype=_valid_subtype(entity_type, mention.subtype)`; the adoption block
   becomes `if not entity.subtype: entity.subtype = _valid_subtype(entity.type, mention.subtype)`.
4. Run the full suite. If an existing test asserted a foreign subtype, STOP and report.

## Done when

- [ ] New tests pass; full suite green except the known `last_run.json` test.
- [ ] `ruff check .` clean.
- [ ] After the shared HUMAN RUN (O1): `pnp validate` reports 0 invalid subtypes.

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q tests/test_subtype_vocab.py
cd services/kb && .venv/Scripts/python.exe -m pytest -q
ruff check .
# after HUMAN RUN:
cd services/kb && .venv/Scripts/python.exe -m pnp_okf.cli validate --bundle ../../knowledge/bundle/splitter_des_ewigen | grep -A3 "Subtype outside"   # expect no output
```
