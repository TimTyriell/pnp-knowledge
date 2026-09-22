# Improvement backlog

Proposals that are understood but not decided. Nothing here is implemented.
When one is taken up, it becomes an ADR or just gets built; when it is
rejected, the entry says so and why, so it is not re-proposed.

---

## I-004 — A live registry entry with no aliases has no anchor

**Status:** proposed, 2026-09-22. Found by I-003's sample review, not by its
metrics. Not scheduled; wants its own measured run.

`_load_preserved_aliases` (`resolve.py:388`) skips any registry entry whose
`aliases` list is empty:

```python
if concept_id and aliases:
    out[concept_id] = aliases
```

So a concept whose alias list is empty **and** whose `canonical_name` no longer
slugifies to its own `concept_id` is unreachable by the reanchor path.
`_reanchor_to_retired` does not cover it either — that one only considers the
`retired:` ledger, and this concept is live. The next run mints a fresh id from
the raw extracted name, and the corrected id reads as abandoned:

```yaml
- concept_id: locations/taverne_in_willauch   # corrected at some point
  canonical_name: Taverne in Willau           # the mishearing, never fixed
  aliases: []                                 # nothing to match on
```

This is what produced the 35-concept refusal on the 2026-09-22 v0.2 re-emit
(see [the override record](../audits/2026-09-22-rename-guard-override.md)) and
it recurs on every run until fixed — each one needing the same manual triage.

**Sketch:** seed the reanchor candidates from `canonical_name` as well as
`aliases`. One line. The reason it is filed rather than done: it changes
resolution for all 1092 entities at once, so it needs a measured run and a
ratchet re-read, not a drive-by edit. Note it would also have prevented most of
the seven `merge:` rules added in `0e90b31`, which are a workaround for this.

**Also open, and human-only:** nine identity pairs the same episode surfaced —
Raben/Krähen-schädel, Tyrex/Tyrael, Schwarzhorn/Schwarzohr, Landra/Lanra,
Tatrick/Tattrick, Trillo/Trilo, Armringe/Ring, and the two Zebros/Cepros maces
that may both be `items/streitkolben_von_dodo`. These are GM rulings; no
matcher decides them.

---

## I-003 — Entity matching: measured, and the string path is at its ceiling

**Status:** done, 2026-09-22. Verdict from
[TESTPLAN-entity-matching.md](TESTPLAN-entity-matching.md), run at `0e90b31`
via `services/kb/eval_matching.py`.

The question was how many of the hand-written `merge:` rules a better matcher
would have found on its own. Answer: **not enough to justify replacing the
current one.**

- Alias closure (V1) lifts live `recall@3` +21.9 points over the shipped
  matcher — but only at t=0.60, where it makes 12 hard-negative false links
  against the ≤2 the acceptance criterion allows. At every threshold that *is*
  safe, it is no better than V0 and usually worse. The lift and the safety
  never coexist, so acceptance criterion 1 fails for all five variants.
- Criterion 3 therefore fires as written: **embeddings over mention notes move
  ahead of alias closure and phonetic normalisation** in the phase-2 order.
- Kölner Phonetik (V2) behaved exactly as the testplan predicted and is not
  worth its hand-written lines.
- E2's parent heuristic scored **6.7%** against a 70% bar — rejected. Three
  misses are structural: the parent is a *person*, not a place.

Incidentally measured and worth knowing: the shipped `FUZZY_RATIO = 0.9` makes
0 false links but **2 split violations**, so the automatic pass is less
conservative than criterion 2 asks for.

The real find was not in the metrics — see [[I-004]] above.

---

## I-002 — A ruling should reach every entry that depends on it

**Status:** done, 2026-08-30. Planned out in
[PLAN-canon-rulings-routing.md](PLAN-canon-rulings-routing.md) on the
`feat/canon-rulings-routing` branch: `context.secondary_sources_for` attaches
a ruling to every entity whose mentions cite the ruled name, capped by
`SOURCE_BUDGET_CHARS`/`MAX_SECONDARY_SECTIONS` and kept in its own prompt
block (`SYNTH_SECONDARY_TEMPLATE`) so it never bleeds into the entity's own
voice. Implemented together with the plan's routing rewrite (explicit
`<!-- okf: entity=... -->` directives), not alone — see the plan for why.

`context.sources_for()` attaches a `knowledge/sources/` section to an entity by
matching the section heading against that entity's name. So a ruling about
Nyruk reaches `npcs/nyruk` and nothing else — even though the entries that
*mention* Nyruk are exactly the ones that repeat the settled contradiction.

Two of the five open conflicts after the v5 rebuild are this, not real
disagreements:

- `characters/nyrella` lists the Nyruk/Nairuk/Nairook spellings as an open
  conflict, and even states that the ruling settles on "Nairuk" — it settles on
  **Nyruk**. The synthesis never saw the ruling and reconstructed it from the
  transcripts.
- `npcs/tyrael` lists "Basul" vs "Vasul" as unresolved. Both fold into
  `deities/vharzul` by rule.

A reviewer who finds decided questions in the queue stops reading the queue, so
this costs more than the two entries.

**Sketch:** match a source section not only against the entity's own names but
against the names of the entities it cites, i.e. attach a ruling to every entry
whose mentions contain the ruled name. The cost is per-entity prompt size, so
it wants a cap: attach at most the few most relevant sections, longest name
match first. Note this invalidates the synth cache for every entity that gains
a section — worth batching with other synthesis work rather than doing alone.

---

## I-001 — Canonical proper nouns at the source, not by rewriting transcripts

**Status:** proposed, 2026-07-27. Not scheduled.

### The question

Whisper hears one name several ways — `Vasul` / `Warzul` / `Basul` / `Valsur`
for Vhar'Zul, `Nairuk` / `Nairook` / `Naeruk` for Nyruk, `Willau` / `Willauch`
/ `Willoch`, `Breska` / `Brechka` / `Bresca`. Today every variant is repaired
after extraction by a `merge:` rule in `knowledge/entity_rules.yaml`, which is
why that file holds ~180 entries. Would it be better to apply those merges to
the transcript itself, before extraction, so every name is already consistent
in the text the pipeline reads?

### Why not to rewrite the transcript

**It destroys the evidence.** Every KB entry cites `Session @ HH:MM:SS`. If
`Basul` is rewritten to `Vhar'Zul` in `transcripts_final/`, the citation points
at words nobody said, and a wrong merge becomes unrecoverable. The whole
conflict-resolution process depends on being able to go back to what was
actually spoken.

**It inverts the cost model.** The extract cache is keyed on the dialogue text
(`extract._cache_key`). Editing a transcript invalidates it, so *every* naming
correction would trigger a full re-extraction — ~€2 and ~85 minutes. Today a
`merge:` rule costs nothing, because resolution is local.

**Search-and-replace cannot do identity.** The hard cases are session-
dependent, not spelling-dependent: two different Haralds, `der Graf` = Voras
der Heilige, Hendrik ≠ Hendrik Heinrich, Jen ≠ der Jen. These need the
`split:` rules, which a text substitution cannot express.

**Silent false positives.** German inflection and compounding ("Belorus'
Armee", "Minengang", "Willauer") make naive substitution unsafe in exactly the
places where it looks safest.

### What to do instead — three layers, each at its own level

| Layer | Where | Fixes | Cost |
|---|---|---|---|
| 1. Vocabulary | `pnp-crawl` Whisper `initial_prompt` | mishearing proper nouns — the *cause* | none |
| 2. Glossary | extraction prompt | model emits the canonical spelling | none for new sessions |
| 3. Rules | `knowledge/entity_rules.yaml` | identity no text can carry | none |

**Layer 1** is the real proposal, and the hook already exists.
`pnp-crawl/config.py` primes Whisper from the roster:

```python
INITIAL_PROMPT: str = _character_name_hint(_get_roster(GROUP_NAME))
```

That covers player and character names only. Deities, cities and recurring
NPCs — the names that actually drift — are absent. The KB can generate that
list, since it knows which concepts are `important` and how often each is
mentioned. This improves how the original is *recorded* rather than editing it
afterwards, so no evidence is touched.

**Layer 2** would put the same vocabulary in the extraction prompt as a
glossary, so the model writes `Vhar'Zul` even when the transcript says
`Basul`. Note the cost asymmetry: a prompt change invalidates the extract cache
for *all* sessions, so this is worth doing only for sessions not yet extracted
— never as a retrofit.

### Constraints to respect

- Whisper's `initial_prompt` is capped at **224 tokens**, and `config.py`
  already documents that a long prompt makes Whisper hallucinate-loop the
  prompt text back out during silence. Room for roughly 40–60 names, so the
  list must be selected (the `important` set plus the highest mention counts),
  not dumped.
- Both layers only affect **future** sessions. The 57 existing transcripts are
  unaffected, and `entity_rules.yaml` stays the mechanism for them.
- Layers 1 and 2 reduce how many `merge:` rules are *needed*; they never
  replace layer 3. Identity decisions stay human.

### Cross-repo note

Layer 1 touches `pnp-crawl`, layer 2 touches `services/kb`. They share only a
generated name list — no build or import coupling, consistent with the
three-repo split in ADR-002.
