# Rename-guard override for the OKF v0.2 re-emit (2026-09-22)

`check_rename_safety` (`emit.py`) refused the v0.2 re-emit: **35 of 1092**
previously known concept ids were absent from a fresh resolve, over the 2%
ceiling. Nothing was written. This document is the evidence for overriding it
with `--allow-rename`, so the decision is auditable rather than a shrug.

## Why this is not the 2026-08 incident

[INCIDENT-2026-08-mass-rename.md](../architecture/INCIDENT-2026-08-mass-rename.md)
describes the failure this guard was written for: an LLM resample rewording
most entity names at once. Three things say that is not what happened here.

- **Extraction was 100% cached** (`67 cached, 0 to call`). The model was never
  asked to name anything, so no resample occurred.
- **Every one of the 35 is a 1-2 mention singleton.** No established concept
  moved. The registry's high-mention entities are untouched.
- **34 of 35 keep their content.** The abandoned id's name survives as an alias
  on a near-identical new id, verified by indexing every current entity by
  canonical_name + aliases and looking each abandoned name up.

The one genuine drop is `events/splitterkalb`, which re-types to
`npcs/splitterkalb` — an id on the `ignore:` list (`entity_rules.yaml:852`).
It is discarded on purpose.

## Root cause for the spelling subset

For a subset, the registry entry stores the **mis-heard** `canonical_name`
while its `concept_id` holds the **corrected** spelling — e.g.
`locations/taverne_in_willauch` stores `"Taverne in Willau"`. The id was
repaired at some earlier point; the name it derives from never was. A fresh
resolve rebuilds the id from the stored mishearing, so the corrected id reads
as abandoned.

Seven of those were fixed by rule in `0e90b31`, the same mechanism the
existing `slicks: npcs/slix_vasul` rule uses, bringing 35 → 28.

## The 28 that remain

| # | Abandoned id | → resolves as | Class |
|---|---|---|---|
| 1 | `events/brief_von_valeria` | `items/brief_von_valeria` | type correction |
| 2 | `events/tunnel_der_gnolle` | `locations/tunnel_der_gnolle` | type correction |
| 3 | `events/vertrag_des_ratten_daemons` | `items/vertrag_des_ratten_daemons` | type correction |
| 4 | `factions/seraphen_von_volgotha` | `npcs/seraphen_von_volgotha` | type correction |
| 5 | `items/blitzelementar` | `npcs/blitzelementar` | type correction |
| 6 | `npcs/esua` | `deities/esua` | type correction |
| 7 | `events/splitterkalb` | *(dropped)* | on the `ignore:` list |
| 8 | `items/stamina_trank` | `items/staminatrank` | cosmetic |
| 9 | `locations/heilige_treppen` | `locations/heilige_treppe` | cosmetic |
| 10 | `locations/der_altar_in_den_narben` | `locations/altar_in_den_narben` | cosmetic (article) |
| 11 | `events/flucht_durch_das_portal_2025-09-06` | `events/flucht_durch_das_portal` | cosmetic (date suffix) |
| 12 | `events/kampf_gegen_die_pilz_goblins_2025-06-17` | `events/kampf_gegen_die_pilz_goblins` | cosmetic (date suffix) |
| 13 | `events/entdeckung_des_okkulten_lagers` | `..._okkulten_opferlagers` | cosmetic (more specific) |
| 14 | `events/faelschung_der_goblin_notiz` | `..._goblin_notizen` | cosmetic (plural) |
| 15 | `events/kampf_gegen_das_tentakelmonster` | `..._tentakelige_monster` | cosmetic |
| 16 | `events/evakuierung_des_halblingsdorfs` | `..._halblingdorfs` | cosmetic |
| 17 | `factions/untote_armee_von_steinbachtal` | `factions/untotenarmee_von_steinbachtal` | cosmetic |
| 18 | `items/buch_flueche_und_das_schweigen` | `items/flueche_und_das_schweigen` | cosmetic |
| 19 | `deities/schlangengott` | `deities/alter_schlangengott` | cosmetic (more specific) |
| 20 | `items/amulett_mit_rabenschaedel` | `items/amulett_mit_kraehenschaedel` | **GM: Rabe vs Krähe** |
| 21 | `items/notiz_von_tyrex` | `items/notiz_von_tyrael` | **GM: two different beings** |
| 22 | `npcs/orlanius_schwarzhorn` | `npcs/orlanius_schwarzohr` | **GM: Horn vs Ohr** |
| 23 | `events/begegnung_mit_landra` | `events/begegnung_mit_lanra` | **GM: Landra vs Lanra** |
| 24 | `npcs/tatrick` | `npcs/tattrick` | **GM: spelling** |
| 25 | `npcs/trillo` | `npcs/trilo` | **GM: spelling** |
| 26 | `items/armringe_von_lindo_laut` | `items/ring_von_lindo_laut` | **GM: Armringe vs Ring** |
| 27 | `items/heiliger_streitkolben_aus_zebros` | `..._aus_zebras` | **GM: may be `items/streitkolben_von_dodo`** |
| 28 | `items/streitkolben_von_zebros` | `items/streitkolben_von_cepros` | **GM: may be `items/streitkolben_von_dodo`** |

Rows 20-28 are identity decisions, not spelling fixes. They were deliberately
left open: guessing an identity is how the 2026-08 incident began, and the
rules file's own precedent is that `merge:` encodes a human ruling. They are
tracked in [IMPROVEMENTS.md](../architecture/IMPROVEMENTS.md).

Rows 27-28 deserve a specific look: `entity_rules.yaml` already maps
`cepros' heiliger streitkolben` and `zebras zorn` to `items/streitkolben_von_dodo`,
so both of these may be that same mace under a third and fourth mishearing.

## Decision

Proceed with `--allow-rename`. The flag's documented purpose is "a deliberate
registry cleanup", and every one of the 28 is enumerated above with its cause.
The guard did its job: it converted silent churn into a stop, a diagnosis, and
seven rule fixes that will hold for every future run.

**Reproduce this table** by resolving against the warm extraction cache and
diffing the resolved concept ids against `entity_registry.yaml`'s `entities:`
keys — no LLM call is involved on that path.

## What this does not settle

Why a fresh resolve picks a different representative than the run that wrote
the registry, given identical cached extractions. Until that is understood this
recurs on every run and needs the same triage. Leading hypothesis: the 67th
session (the corpus has 67 transcripts against the bundle's 66 session files)
adds a second mention to singleton entities and flips which raw name wins.
