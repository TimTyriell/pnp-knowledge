# Spelling sweep: prose drift behind pinned canonical names

Follow-up to `2026-08-29-spelling-handoff.md`. Produced by
`services/kb/spelling_doctor.py`, restricted to the 44 concepts with an
explicit `canonical_name:` pin in `entity_rules.yaml` (a human already ruled
one spelling correct there; anything else in prose is unambiguous drift) and
filtered to aliases that fuzzy-match a word of the canonical name (excludes
legitimate shortened references and unrelated nicknames — see the script's
docstring).

Raw run: 933 files, 44 pinned concepts, 48 alias/canonical pairs surfaced.
Manually triaged below into buckets per the branch plan:

- **A — safe token rewrite**: variant is never anything but the misspelling.
- **B — needs phrase context**: variant collides with a real word/phrase.
- **C — semantic misread**: the LLM understood the wrong thing; GM ruling + re-synth.
- **excluded**: doctor false positive — a legitimate shortened reference or
  paraphrase, not a spelling error. Listed so the exclusion is a decision, not
  a silent drop.

## Bucket A — token rewrite (`spelling:` bare-token rule)

| concept | variant → canonical | hits |
|---|---|---|
| locations/willauch | Willau → Willauch | 67 |
| locations/willauch | Willoch → Willauch | 16 |
| locations/willauch | Villauch → Willauch | 1 |
| locations/breska | Brechka → Breska | 45 |
| locations/breska | Bereska → Breska | 5 |
| locations/breska | Bresca → Breska | 2 |
| locations/breska | Breschka → Breska | 1 |
| npcs/lenra | Lanra → Landra | 42 |
| npcs/lenra | Leandra → Landra | 21 |
| npcs/lenra | Lenra → Landra | 9 |
| deities/tarvok_der_erdrichter | Tarvok → Thar'Vok | 29 |
| deities/tarvok_der_erdrichter | Tavok → Thar'Vok | 13 |
| deities/tarvok_der_erdrichter | Tarvolk → Thar'Vok | 1 |
| npcs/adeliga_der_eulenseraph | Adelia → Adeliga | 24 |
| npcs/slix_vasul | Slicks → Slix | 8 |
| deities/korn | Born → Korn | 5 |
| deities/korn | Kord → Korn | 1 |
| deities/huludan | Holodarn → Huludan | 1 |
| items/streitkolben_von_dodo | Zebrus Zorn → Zebros Zorn | 3 |

Compound duplicates of the above (`Tarvok (Der Erdrichter)`, `Tavok (Erdrichter)`,
`Tavok (der Erdrichter)`) need no separate rule — the bare-token rule already
rewrites the `Tarvok`/`Tavok` inside them.

## Bucket B — phrase-scoped (not reported by the doctor; found in the original report + manual re-check)

| variant phrase | canonical phrase | why phrase-scoped |
|---|---|---|
| "Festung Zebras" | "Festung Zebros" | "Zebras" alone collides with the animal |
| "Berg Zebras" | "Berge von Zebros" | same |
| "heiliger Streitkolben aus Zebras" / "Streitkolben von Cepros" | "…von Zebros" | "Cepros" never made it into the registry as an alias at all — extraction never proposed it as a mention; needs a direct `merge:`/`spelling:` addition, not just a registry fix |
| "die Hack" (referring to Landra) | "die Hag" | "Hack" is a common word; only the phrase referring to the hag should turn |

`Cepros`/`Zebras` not appearing in the doctor's own output (despite being the
lead example in the original report) is itself a finding: they were never
extracted as recognized alias text, so the registry-driven doctor is blind to
them by construction. Confirms the plan's premise that regex/registry alone
can't be the whole mechanism — see Bucket C below for the related semantic
error on the same kingdom.

## Bucket C — semantic misread, needs GM ruling + targeted re-synth

- `sources/Kanon_Entscheidungen.md:465-467` currently rules "Cepros" is a real,
  separate origin ("drei Teile einer Geschichte") — overturned per this
  branch's GM decision (2026-08-29): Cepros is a mishearing of Zebros, not a
  third thing.
- `factions/untote_horde_von_zebras.md:13` — "eine große Schar untoter
  Zebras" reads the kingdom name as the animal ("undead zebra animals"). Needs
  a GM sentence in Kanon_Entscheidungen.md and a `--force` re-synth of this
  one concept (a `spelling:` token swap alone would produce "untoter Zebros",
  which is grammatically not much better — the sentence needs rewriting, not
  a word swap).

## Excluded — doctor false positives (legitimate shortenings/paraphrases, do nothing)

| concept | variant | why excluded |
|---|---|---|
| factions/gilde_von_ehrenfels | "Die Gilde", "Gilde von Ehrenfels", "Gilde in Ehrenfels", "Ehrenfels-Gilde", "Gilde Ehrenfels" | ordinary German short reference / preposition variants |
| locations/parfon_kapelle_auf_dem_berg | "Die Kapelle" | shortened reference |
| items/gruener_seelenkristall_von_hans | "Seelenstein" | shortened reference |
| locations/taverne_von_ehrenfels | "Die Taverne", "Taverne in Ehrenfels" | shortened reference / preposition |
| locations/verlassene_mine_an_der_farm | "Die Mine" | shortened reference |
| locations/zum_gruenen_sichelmond_von_tiefwasser | "Zum grünen Sichelmond" | drops parenthetical, still unambiguous |
| locations/taverne_kyla_von_sanddorn | "Taverne Kyla" | shortened reference |
| locations/banditenlager_der_silberkerne | "Banditenfestung", "Banditenlager (Burgruine)", "Das Banditenlager (im Wald)", "Altes Banditenlager" | descriptive variants, not mishearings |
| locations/kapelle_von_ehrenfels | "Kapelle in Ehrenfels" | preposition variant |
| locations/ende_jenseits_der_orkgebiete | "Das Ende" | shortened reference |
| locations/bibliothek_von_willauch | "Die Bibliothek" | shortened reference |
| npcs/lord_kalidarn_von_willauch | "Lord von Willauch" | shortened reference |
| npcs/hal_harl | "Hal (Harl)" | parenthetical variant |
| npcs/voras | "Graf Voras" | registered alias, honorific + name, not a mishearing |
| factions/koenigreich_zebros | "König Zebros" | already an identity `merge:` key (`entity_rules.yaml:40`); leaving prose as-is since "in König Zebros' Zeit"-type phrasing may be intentional retrospective narration — flag for GM if it reads wrong after other fixes land, don't blind-rewrite |

## Not from the doctor: known autolink/identity defects (separate mechanism, same branch)

- `[Voras](/npcs/vora.md)` — 18 occurrences link the label "Voras" to the
  wrong, unrelated one-mention concept `npcs/vora` instead of
  `npcs/voras`. Root cause: `_link_first_occurrence`'s genitive `s?` suffix
  lets "Vora" consume "Voras". Fixed in code (`synthesize.py`), not by a
  `spelling:` rule — the link *target* is wrong, not the *text*.
- `characters/dodo.md:46` — `[Amulett](/items/amulett_des_heiligen_duran.md)`
  links Dodo's own unrelated trinket to Duran's artefact, because "Amulett"
  is registered as a bare alias of that artefact. Fixed via `alias_block:`.
- `characters/sange.md:18` — the common noun "Krieg" (war) linked to PC
  `characters/krieg`. **Not fixed on this branch**: unlike the Duran amulet,
  "Krieg" is that character's actual `canonical_name`, not an extra alias —
  `alias_block:` only strips from `aliases`, so blocking it would still leave
  the canonical name linkable (per `synthesize.py::link_targets`, which reads
  `[canonical_name, *aliases]`). A character whose name is a common German
  word will keep colliding with normal prose use of that word; fixing this
  needs either a context-aware autolink (skip a name if it's not capitalized
  as a name, or requires a minimum-mentions run of surrounding capitalized
  words) or a per-occurrence override, neither of which exists yet. Flagged,
  not fixed.
- `items/zebras_zorn.md` vs `items/streitkolben_von_dodo.md` — duplicate
  concepts for the same weapon, one letter apart in the slug. Fixed via
  `merge:`; `validate.py`'s duplicate-title check widened to catch the next
  one of these (was `characters/`+`npcs/`-only).
