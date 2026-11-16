# O8 — Vocabulary v2: Event and NPC subtypes, `ancestry`, thread kind `threat`

| | |
|---|---|
| Branch | none of its own. The code lands on B2's `feat/anchored-extraction` |
| Depends on | B2 (carries the `EXTRACT_PROMPT_VERSION` bump), T8 HUMAN RUN (roster in the prompt) |
| Cost | $0 on top of B2. The state-pass bump rides the state re-run B2 causes anyway |
| Size | S code |

## Intent

Measured 2026-11-16 on `knowledge/bundle/splitter_des_ewigen`:

- 161 of 580 event anchors (28 %) carry `Sonstiges` — the largest event bucket.
- NPCs (313 concepts) have no subtype list at all, so `npcs/index.md` is one
  flat list of persons, monsters, ghosts and pets.
- Ancestry is the descriptor the table uses most ("Ribbit-Rangerin",
  "Galapa-Farmer", "Infernis") and exists only as prose. It also drifts:
  Catfolk/Katari, Tiefling/Infernis, Drachengeborener/Drakona,
  Froschwesen/Ribbit/Ribbet name the same peoples.
- 119 of 193 threads are `mystery`. Sieges, growing armies and kill contracts
  sit there because no kind fits a danger that advances by itself.

Wanted: more labels where the data needs them, a closed `ancestry` field on
persons, and one more thread kind.

**Constraint — why this is not its own PR.** Subtype and ancestry are written
by the extraction prompt. Any change to `EXTRACT_SYSTEM` or to the
`EntityMention` schema needs an `EXTRACT_PROMPT_VERSION` bump: full
re-extraction (~$6.50) and concept-id churn (PIPELINE.md §4, §6). B2 already
budgets exactly one such bump (v6 → v7). Decision (human, 2026-11-16): O8
rides it. Do **not** bump a version for O8 alone.

**Deliberately not added.** New Item, Location and Faction subtypes. O1
demotes their one-session members to session bullets; only 19 items,
30 locations and 11 factions span two or more sessions, with 4 `Sonstiges`
between them. Nothing is left to group. Also out: adversary type and tier,
environment type, Hope/Fear, SRD domains (table mechanics, not world facts);
NPC role tags such as Wirt or Händler (no consumer); `subtype`/`ancestry` in
the API listing (add when pnp-export-data wants wiki categories).

Deity `Sonstiges` (21 of 43) is mostly spelling duplicates of canon gods
(Agastrale/Akastrale, Jorah/Joran/Joranja/Der Münzenzähler/Jhoran, four
goblin-god entries). That is `merge:` work in `knowledge/entity_rules.yaml`
after a GM look, not vocabulary, and not part of this plan.

## The vocabulary

Labels are German: they are frontmatter values and index headings. New labels
go **before** `Sonstiges` in each tuple (tuple order is index order).

### Event (9 → 15)

| New label | Means | Examples from the bundle |
|---|---|---|
| `Rettung` | rescue, liberation, healing that saves someone | Befreiung Lulis aus dem Kerker; Rettung Brims am Abgrund |
| `Flucht` | escape, retreat, emergency teleport | Flucht aus der brennenden Scheune; Gefängnisausbruch |
| `Verwandlung` | transformation, possession, loss of control | Übernahme Lindo Lauts durch Slix; Sanges erste Werwolf-Verwandlung |
| `Zerstörung` | deliberate destruction of an object or structure | Sprengung der Brücke; Zerstörung der vier Portalsäulen |
| `Erscheinung` | vision, omen, prophecy, a god or spirit appearing | Erscheinen der Göttin Nerash; Die Rote Nacht in Zebros |
| `Gefahr` | trap or environmental hazard with no enemy to fight | Giftgaswolke hinter der Steintür; Steinschlag am Bergpass |

Hand-classifying the 161 `Sonstiges` titles puts about 77 of them under these
six labels. Tie-break, stated in the prompt: `Tod` wins over everything;
`Kampf` wins when the scene is a fight; otherwise the label that matches what
the event's name says. Not added: `Rast` (5 events; a table term per
`RULES_GLOSSARY`) and a label for social moments (about 20; too vague for a
closed list).

### NPC (new list)

The axis is what the being **is**, never its job.

| Label | Means | Examples |
|---|---|---|
| `Person` | an individual of a people, named or not | Berthold, Xenia Rotkam, Lurk |
| `Kreatur` | beast, monster, construct | Der Oger, Steingolem-Koloss, Harpyie am Bergnest |
| `Untoter` | undead, ghost, bound soul | Tyrael, Das Hass-Geisterkind, Voras |
| `Begleiter` | animal or creature bound to a character or NPC | Nyruk, Perry, Merlin, Basilisk Sloppy |
| `Dämon` | demon or other being from beyond the mortal plane | Balor in der Zwischenebene, Lilly, Dämon der Hybris |
| `Sonstiges` | none of the above | the voices in the amulet (Esua, Zytral) |

Precedence when two fit: `Begleiter` > `Untoter` > `Dämon` > `Kreatur` >
`Person`. An entry for a group ("Die beiden Trolle") takes its members' label.

### Deity (+1)

`Heiliger` — a venerated mortal (Heiliger Duran). The model invented this
label once already. No `Titan`: one member.

### `ancestry` (new field, Character and NPC only)

One value from the closed list `ANCESTRIES`, or empty. There is **no**
`Sonstiges`: an unknown ancestry stays empty, otherwise the bucket becomes
the default answer.

- The 18 SRD ancestries (`daggerheart-data/core/ancestries.json`), in the
  table's spelling: `Clank`, `Drakona`, `Zwerg`, `Elf`, `Fee`, `Faun`,
  `Firbolg`, `Fungril`, `Galapa`, `Riese`, `Goblin`, `Halbling`, `Mensch`,
  `Infernis`, `Katari`, `Ork`, `Ribbet`, `Simiah`.
- Campaign extras: `Seraph`, `Gnoll`, `Kenku`, `Troll`.
- Normalisation hints for the prompt: Tiefling → `Infernis`;
  Drachengeborener/Dragonborn → `Drakona`; Catfolk/Katzenwesen → `Katari`;
  Froschwesen/Ribbit → `Ribbet`; Galappa/Schildkröte → `Galapa`;
  Pilzwesen → `Fungril`; Simia/Simai → `Simiah`; Pixie/Faery → `Fee`;
  Elb/Dunkelelf → `Elf`.
- Rule for the model: set it only when the table states it or describes it
  unmistakably. Oger, Vampir and Golem have no ancestry; the NPC subtype
  carries that.

**STOP — ask the human (GM):** is `Seraph` a people in this campaign (the
faction `Seraphen` is filed as `Volk`), or only the SRD class of that name?
Default to propose: keep `Seraph` in the list.

Extraction is the source for player characters too. T8's `class` stays the
verbatim `race_class` string (`Fee Barde`); do not parse it. B2 puts the
roster into the prompt, so the model sees each character's class line.

### Thread kind (+1)

`threat`, German label `Bedrohung`: a danger that advances by itself when the
party does nothing ("Belagerung von Breska durch die Untoten", "Der
Mordauftrag auf Rotunas"). This is the state pass, not extraction: it needs
`STATE_PROMPT_VERSION` `"1"` → `"2"`. B2 renames entities, the frozen glossary
is refreshed afterwards, and that already re-runs the state pass for every
session. The bump goes into that run.

## Steps

All in `services/kb`, on B2's branch, **before** B2 computes the new
`EXTRACT_PINS` hash. Tests first, as in every plan here.

1. **Tests.**
   - `tests/test_subtype_vocab.py`: `test_type_without_a_list_carries_no_subtype`
     uses `EntityType.CHARACTER`. Add: NPC with `Kreatur` keeps it; NPC with
     `Volk` gets `""`.
   - `tests/test_okf_v02.py::test_subtype_on_a_type_with_no_vocabulary_is_flagged`:
     use a `characters/` concept (NPC now has a list).
   - New `tests/test_ancestry.py`, built like `test_subtype_vocab.py` (reuse
     its `_run` and `_mention` shape): kept on an NPC and on a Character;
     `""` on a Faction reached through a cross-directory `merge:`; a value
     outside the list becomes `""`; adopted from a later mention when the
     first is empty; written to frontmatter by `emit_entity`;
     `validate_bundle` reports a foreign value.
   - `tests/test_subtype_index.py`: one case that groups NPCs.
   - `tests/test_thread_emit.py` and `services/summary/test_summary.py`: one
     `threat` thread round-trip each.
2. `src/pnp_okf/models.py`:
   - `SUBTYPES`: add the six Event labels and `Heiliger`; add
     `EntityType.NPC: ("Person", "Kreatur", "Untoter", "Begleiter", "Dämon", "Sonstiges")`.
   - `ANCESTRIES: tuple[str, ...]` after `SUBTYPES`, with a comment naming the
     SRD file and the campaign extras.
   - `EntityMention.ancestry: str = Field(default="", description=...)`;
     `CanonicalEntity.ancestry: str = ""`.
   - `THREAD_KINDS`: append `"threat"`.
3. `src/pnp_okf/prompts.py`:
   - extraction: "(Character, NPC, Domain)" becomes "(Character, Domain)";
     add a short *Abgrenzung* block (NPC precedence, Event tie-break, one line
     per new label); add the ancestry instruction, with the list rendered from
     `ANCESTRIES` the way `_render_subtypes` renders `SUBTYPES`, plus the
     normalisation hints.
   - next to B2's scope rules, two boundary lines: something that cannot be
     carried is a `Location`, never an `Item`; a realm beyond the mortal plane
     is a `Domain`, never a `Location`.
   - state: add "Bedrohungen (threat)" to the thread list in `STATE_SYSTEM`;
     `STATE_PROMPT_VERSION = "2"`. **This plan authorises that bump** — only
     on B2's branch.
4. `src/pnp_okf/resolve.py`: next to `_valid_subtype` add
   `_valid_ancestry(entity_type, value)`: the stripped value when the type is
   in `PERSON_TYPES` and the value is in `ANCESTRIES`, else `""`. Use it at
   the two places `_valid_subtype` is used (the `CanonicalEntity(...)`
   constructor and the adoption block). First valid mention wins, as for
   subtype; say so in a comment and name majority vote as the upgrade.
5. `src/pnp_okf/emit.py`: `emit_entity` writes `ancestry` after `subtype`,
   omitted when empty. `_THREAD_KIND_DE["threat"] = "Bedrohung"`. The NPC
   index groups itself: `SUBTYPES.get(etype)` already drives it.
6. `src/pnp_okf/state.py`: `ThreadKind` Literal gets `"threat"`.
7. `src/pnp_okf/validate.py`: `invalid_ancestries` on `ValidationReport`,
   mirroring `invalid_subtypes` (field, the `ok` condition, the report lines,
   the check beside the subtype check).
8. `services/summary/summary.py`: the kind label map gets `threat`.
9. `extraction_benchmark.py` `validate_output`: reject an `ancestry` outside
   `ANCESTRIES`, beside the subtype check.
10. `tests/test_prompt_pins.py`: `STATE_PINS["2"]`. `EXTRACT_PINS["7"]` is
    B2's step, computed once all prompt edits are in.
11. Docs: the vocabulary table in `T00-tracking-model.md` §4;
    `docs/architecture/PIPELINE.md` (ancestry is adopted next to subtype).

## Done when

- [ ] New tests pass; kb and summary suites green (kb: known `last_run.json` test excepted).
- [ ] `ruff check .` clean.
- [ ] B2's $0 dry run (three sessions, agent mode) meets: event `Sonstiges` ≤ 15 %; NPC subtype non-empty ≥ 95 %; every rostered character has an ancestry; no value outside the lists.
- [ ] After B2's HUMAN RUN and the state re-run: the commands below show it on the bundle.

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q
cd services/summary && ../kb/.venv/Scripts/python.exe -m pytest -q
ruff check .
# after the HUMAN RUNs, from knowledge/bundle/splitter_des_ewigen:
grep -h -o -E "^_[^·]+ · " sessions/*.md | sort | uniq -c | sort -rn   # Sonstiges <= 15 %
grep -L "^subtype:" npcs/*.md | grep -vc index.md                       # near 0
grep -h "^ancestry:" characters/*.md npcs/*.md | sort | uniq -c         # list values only
grep -h "^kind:" threads/*.md | sort | uniq -c                          # threat present
cd ../../../services/kb && .venv/Scripts/python.exe -m pnp_okf.cli validate --bundle ../../knowledge/bundle/splitter_des_ewigen
```
