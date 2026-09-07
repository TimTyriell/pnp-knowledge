# Handoff: repair the identity layer after the prompt-v6 regeneration

**For:** an agent working in `pnp-knowledge`, branch `chore/docs-ci-and-instrumentation`
**Prereq:** read `docs/architecture/MIGRATION-prompt-v6.md` first — it explains why the bundle was regenerated and what it cost.

## Situation

The bundle was regenerated under `PROMPT_VERSION=6` with `deepseek-v4-pro`
(previously `deepseek-chat`). The run succeeded. The **content** is fine —
measured across the 399 concepts that kept their id, v6 has +33% median
outgoing links and half as many zero-link orphans. **Do not re-run extraction
or synthesis**; it costs ~$8 and ~96 min and will not fix anything below.

The **identity layer** is what broke: 868 → 1099 concepts, 524 old titles
gone, 757 new, 54 dead rules, 11 failing tests.

Two structural causes are already fixed in code — do not redo these:

1. `spelling:` now reaches concept-id derivation, not only prose
   (`resolve.py::_default_concept_id`). It previously ran only in `links.py`,
   so a mishearing the GM had already ruled on could still mint its own node.
2. Extraction can be frozen per session
   (`extract.py::_frozen_prompt_version`, `PNP_EXTRACT_FREEZE_*`), so a future
   `PROMPT_VERSION` bump no longer re-derives the back catalogue.

Your job is the **data**: the rules and directives the rename detached.

## Ground rules

- **Never move a hard-`0` baseline.** From `test_canon_decisions.py:48` — *"A
  baseline that can be raised is an invitation to raise it; this is a fact
  about the file, not a ceiling to negotiate."* Fix the data instead.
- A *measured* ratchet (unlinked mentions, spelling totals) may move **only**
  with a written justification in the comment above the constant, in the style
  of `test_link_coverage.py:43-83`.
- Anything needing a GM ruling is **not yours to decide**. Collect those into
  one list and stop. Marked **GM** below.
- All of this is free — no LLM calls. `pnp validate`, `rules_doctor.py`,
  `spelling_doctor.py`, `pnp dedup` and `pytest` are offline.
- Re-emitting without re-extracting is cheap and expected: the extraction
  cache is warm.

## Reference data (already generated, in the session scratchpad)

| file | contents |
|---|---|
| `renamed.tsv` | 18 concepts whose id changed but title survived |
| `dropped.tsv` | 524 titles present before, absent now |
| `added.tsv` | 757 new titles |
| `kept.tsv` | 399 unchanged ids |

Rebuild with `rename_map.sh`. It matches on **title, not id** — the id is
derived from the title, so an id join finds nothing by definition.

## Tasks, in order

### 1. Repair the canon directives (fixes 4 failing tests)

`knowledge/sources/Kanon_Entscheidungen.md` binds rulings to concepts via
`<!-- okf: entity=... -->`. Seven targets no longer resolve:

| directive target | status |
|---|---|
| `npcs/abisalis_harald` ("Harald (Dämon)") | renamed/absorbed — find the new id |
| `npcs/hendrik_heinrich` | renamed; `npcs/hendrik` exists — **GM**: same person? |
| `deities/bodrak_gott_der_stille` ("Stiller Gott") | renamed; `deities/bodrak` exists |
| `items/magischer_ring` ("Ringe") | renamed |
| `npcs/der_schinder` | exists but brief tier — add `important: true` |
| `items/ring_der_teleportation` | brief tier — add `important: true` |
| `events/verhandlung_mit_harl` | brief tier — add `important: true` |

Also `Bekannte_Pantheon_der_Goetter.md :: "Nicht in dieser Schrift verzeichnet"`
reaches no entity — it is a prose heading, not an entity. Move it to
`knowledge/narrative/` or give it a directive.

Verify: `pytest tests/test_canon_decisions.py` — every count must return to 0.

### 2. Repoint dead `entity_rules.yaml` rules

```bash
cd services/kb && python rules_doctor.py
```

54 dead: 36 inert (safe to delete), 18 need a decision. Use `renamed.tsv` to
**repoint rather than delete** — a rule aimed at a renamed concept is still
wanted, just misaddressed.

The 8 dead `never_merge:` pairs are the urgent ones. Each is a GM ruling that
two things are distinct, currently unenforced:

```
factions/fluechtlinge            <-> factions/fluechtlinge_aus_breska
npcs/freibeuter_harald           <-> npcs/abisalis_harald
npcs/hendrik                     <-> npcs/hendrik_heinrich              GM
npcs/jen                         <-> npcs/der_jen
npcs/lenra                       <-> npcs/kraeuterhexe_von_lady_kalen   GM
npcs/kraeuterhexe_von_lady_kalen <-> npcs/lady_kalen                    GM
npcs/adeliga_vom_haus_des_loewen <-> npcs/adeliga_der_eulenseraph       GM
characters/kip                   <-> characters/kipp    GM (neither exists now)
```

### 3. Add the missing spelling rules

`spelling:` now drives identity, so each entry prevents a future split. v6
introduced variants v5 never produced:

```
Breschka -> Breska        Cepros -> Zebros
Willau   -> Willauch      Tavok  -> Thar'Vok    (confirm the canon form)
Willoch  -> Willauch      Tarvok -> Thar'Vok
```

`Willau`/`Willoch` already exist — confirm they now take effect through
`_default_concept_id`. Check each candidate against `alias_block:` first: a
substring rewrite that is too eager can fold unrelated concepts together.

Re-emit, then re-measure. Expect `test_spelling_sweep` mismatches to fall from
45 — but note ~35 of those are German declension
(`Belorus dem Stillen` → `npcs/belorus`), **not** errors. Do not chase them.

### 4. Triage generic-noun nodes (GM-adjacent)

Common nouns are getting their own nodes: `npcs/wirt`, `npcs/waechter`,
`npcs/voegel`, `locations/wirtshaus`, `locations/klippe`, `locations/steg`,
`items/kurzschwert`, `items/spitzhacke`. 241 single-token nodes exist; most are
180–300 char stubs.

`npcs/wirt` is the clearest case — its own body states the innkeeper's name is
unrecorded and that it may describe **two different people** in two towns.

Add role nouns and generic equipment to `ignore:` (138 entries already), or to
`alias_block:` where the node should exist but must not autolink. Do not delete
proper names that merely look generic — `Navisal`, `Nazirathel` and `Wabarask`
are real.

### 5. Merge the duplicate persons `pnp validate` reports

```
characters/cookie                     <-> npcs/perry_begleiter_von_cookie
npcs/canfield_lobrecht <-> npcs/lobrecht <-> npcs/kapitaen_kahnfuehrer_lobrecht
npcs/lord_voras                       <-> npcs/voras
npcs/untoter_waechter <-> npcs/waechter <-> npcs/vermummter_waechter_des_berges
npcs/hans_wirt_zum_gruenen_sichelmond <-> npcs/wirt
factions/die_gilde_in_ehrenfels       <-> factions/gilde_von_ehrenfels
locations/sanddorninseln              <-> locations/sandhorn_inseln
```

Route through `merge:`. Check `never_merge:` before merging anything — it
records pairs already ruled distinct.

### 6. Cross-repo: `pnp-export-data/wiki_pages.toml`

One id is stale: `deities/ezhura` no longer exists.
(`events/beschwoerung_von_slix` is also absent but sits in `exclude`, so it is
a no-op.) That repo is a pure API client — fix the map **there**, never in
`knowledge/`.

### 7. Re-measure, then update the docs

`README.md`, `docs/QUALITY.md` and `ADR-001` still state **868 concepts / 64
sessions** and the v5 ratchet baselines. They were committed in `6861d33`
before the regeneration finished. Update once the numbers settle — the bundle
is now 1099 concepts / 66 sessions, `conflicts_open` 12, `dropped_links` 144.

Also fix an emit bug the mismatch report exposed — one link label contains raw
YAML frontmatter:

```
("P-0\ntags:\n- locations\ntimestamp: '2026-03-24T00:00:00Z'\nid: LOC_MAGIERTURM
  ...", 'locations/gemata')
```

## Done when

```bash
cd services/kb && PNP_REQUIRE_BUNDLE=1 python -m pytest -q
```

242 passing, 0 failing. `rules_doctor.py` reports no rule needing a decision
that has not been repointed or escalated to the GM list. The `pnp validate`
duplicate-person count is down. Every baseline you moved carries a written
reason, and every hard `0` is still `0`.
