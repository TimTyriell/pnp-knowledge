# Plan — canon rulings: routing, structure, and the tests that pin them

**Status:** planned, 2026-08-29. Nothing implemented; no code changes on this
branch. Implementation belongs on its own branch.
**Decides:** how a GM ruling in `knowledge/sources/Kanon_Entscheidungen.md` is
bound to the entities it governs, what markers the file may use, and which
tests keep each failure mode from returning.
**Closes:** [IMPROVEMENTS.md](IMPROVEMENTS.md) I-002.
**Related:** [ADR-001](ADR-001-knowledge-layer.md);
[TESTPLAN-entity-matching.md](TESTPLAN-entity-matching.md);
`knowledge/conflicts/README.md`.
**Cost:** one `PROMPT_VERSION` bump = one full re-synthesis. Bump last, once.


## Context

`knowledge/sources/Kanon_Entscheidungen.md` is the GM's override layer: 88
`ENTSCHEIDUNG:` paragraphs under 62 `### <Name>` headings that settle
contradictions the transcripts cannot. It is the only human-authored input that
outranks session evidence.

I traced its full consumption path. It is shorter than expected:

```
cli.py:154  load_sources(paths.sources_dir)   ->  flat list[SourceSection]
cli.py:188  sources_for(entity, sections)     ->  one markdown string
synthesize.py:211  wrapped in SYNTH_SOURCES_TEMPLATE  ->  one DeepSeek call
```

That is all. Nothing else reads `knowledge/sources/`.

**The file works, but its structure is the bottleneck, not its prose.** Three
defects, all traceable to one root cause: *the heading text is the only join key
between a ruling and an entity.*

1. **Misrouting.** `context.py:83-84` matches names ≥4 chars by bidirectional
   substring containment. `### Harald (Freibeuter)` therefore also grounds the
   demon Harald; likewise both Hendriks, both Hans, both Adeligas, both Dodos.
   Six rulings currently feed text meant for one person into two entities —
   measured and frozen as `AMBIGUOUS_PERSON_RULING_BASELINE = 6` in
   `services/kb/tests/test_canon_decisions.py:63`. The rulings that most need
   precision (`ENTSCHEIDUNG: Zwei verschiedene Personen.`) are exactly the ones
   the matcher cannot express.

2. **Dead rulings.** Nine `ENTSCHEIDUNG:` sections match zero entities
   (`UNREACHED_RULING_BASELINE = 9`, same file:54). Some are policy headings
   that were never meant to match — but those are then *dead weight that reaches
   nobody*, which is not the same as "working". Others are stale: `### Ring der
   Teleportation` (entity is now `Teleportationsring`), `### Lenra` (now
   `Landra, die Hag`), `### Die Hags`, `### Sythraal`. A heading silently stops
   working when an entity is renamed, and the GM gets no signal.

3. **Contradictions injected verbatim.** Lines 472-482 send the model a ruling
   labeled `ENTSCHEIDUNG (überholt, siehe Korrektur …)` *and* its `KORREKTUR:`,
   in the same prompt block, relying on the model to obey the "überholt" tag.
   Current research says that is the wrong thing to rely on: LLMs
   [fail to enforce stated instruction precedence under conflicting
   directives](https://arxiv.org/html/2502.15851) and rarely even acknowledge
   the conflict. A superseded ruling must be deleted, not annotated.

Plus three smaller ones:

4. **`HINWEIS ZUR DARSTELLUNG:` has no prompt support.** Seven instances.
   `prompts.py:204` explicitly tells the model that *only* `ENTSCHEIDUNG:`
   sections are instructions and the rest is reference material to reason about.
   So the GM's presentation directives ("keep this short", "mark as rumour",
   "the wiki should know only what viewers know") arrive framed as lore.

5. **Duplicate headings.** `Ezhura`, `Nyrella`, `Silberkerne` appear twice with
   *different* rulings; both copies are injected, silently merged
   (`DUPLICATE_HEADING_BASELINE = 3`). A second `### Die Prinzessin` (:328) is
   empty and dropped.

6. **No size budget on sources.** `EXCERPT_BUDGET_CHARS = 60_000`
   (`context.py:31`) caps excerpts only; `sources_for` joins every hit
   unbounded. Harmless today, not once I-002 attaches secondary sections.

**I-002** (`docs/architecture/IMPROVEMENTS.md:9-36`) is the remaining half: a
ruling reaches only the entity it names, never the entries that *mention* the
ruled name — which are precisely the ones that re-derive the settled
contradiction from transcripts. `characters/nyrella` currently lists the
Nyruk/Nairuk spellings as an open conflict and resolves them on the **wrong**
spelling, because the ruling never reached it.

**Outcome intended:** a ruling is bound to a concept ID, not to a string;
it reaches every entry that depends on it; superseded and duplicate rulings
cannot survive; presentation directives are honored as directives; and a
rename cannot silently kill a ruling (a test fails instead).

Scope confirmed with the user: file restructure **+** code change **+** I-002.
Other files in `knowledge/sources/` are **out of scope** (findings recorded at
the end for later).

---

## Design

### The join key becomes explicit

Keep markdown headings — they stay the human's reading structure and
`load_sources` already handles them. Add a machine-readable directive line
directly under each heading, parsed and **stripped** by `load_sources` so it
never reaches the prompt:

```markdown
### Harald (Freibeuter)
<!-- okf: entity=npcs/harald_freibeuter -->

ENTSCHEIDUNG: Freibeuter-Kapitän, betreibt eine heruntergekommene Taverne und
verteidigt sich mit einem Rapier.
```

- `entity=<concept_id>[,<concept_id>…]` — exact routing. Ends misrouting and
  stale headings in one move.
- `mentions=off` — opt out of I-002 secondary attachment (for rulings that are
  only meaningful inside their own entry).
- Absent directive → current slug matching, unchanged. Back-compatible, so the
  code change can land before the file rewrite.

Chosen over YAML frontmatter per section (markdown has no per-section
frontmatter) and over a sidecar YAML file (splits the ruling from its prose;
the GM edits one file today and should keep doing so). An HTML comment is
invisible in every markdown renderer, survives the existing heading parser
untouched, and needs ~10 lines to parse. This matches the documented practice of
[embedding structured routing metadata directly in the markdown
source](https://blog.trysteakhouse.com/blog/markdown-first-semantics-frontmatter-rag-retrieval);
[metadata-enriched retrieval measures ~82.5% vs ~73.3%
precision](https://arxiv.org/html/2512.05411v1) against content-only matching.

### Marker vocabulary, fixed to three

| Marker | Meaning | Prompt handling |
|---|---|---|
| `ENTSCHEIDUNG:` | a world fact that outranks all session evidence | existing override clause |
| `DARSTELLUNG:` | how to *write* the entry (length, hedging, rumour framing) | **new** clause — directive, not lore |
| *(nothing else)* | — | — |

`HINWEIS ZUR DARSTELLUNG:` → `DARSTELLUNG:`. Bare `HINWEIS:` (:294) → folded
into its `ENTSCHEIDUNG:`. `KORREKTUR:` → **deleted**; its content replaces the
ruling it corrects. `ENTSCHEIDUNG (GM/Noah <date>)` keeps the date — provenance
is fine, a live-plus-dead pair is not.

### Prose rules for a ruling

One ruling = one claim, fact first, instruction second, no negative-only
phrasing. So:

> ENTSCHEIDUNG: Dodo vermisste die *Farbe* Blau, nicht blaue Haut — Ursache war
> ein Domänen-Effekt der Götter (alles schwarz-weiß außer Rot). Seine Spezies
> ist davon unberührt.

instead of a paragraph that ends in `Führe diesen Punkt nicht als
Spezies-Widerspruch auf.` German stays; the audience is a German-language
synthesis prompt.

### The four policy sections move out of the file

`### Benennung von Orten`, `### Was ein Gegenstand ist`, `### Was eine Fraktion
ist`, `### Gott und Erscheinung` are campaign-wide standing rules, not rulings
about an entity. They can never match a heading and are dead today. They belong
in `SYNTH_SYSTEM` (`prompts.py`), where standing instructions live and where
they reach every entity at zero per-entity prompt cost.

---

## Implementation

### Phase 1 — parser + explicit routing (`context.py`)

`services/kb/src/pnp_okf/context.py`:

- Add `_DIRECTIVE_RE = re.compile(r"<!--\s*okf:\s*(.*?)\s*-->", re.DOTALL)`.
- In `load_sources` (`context.py:48-63`): after slicing a section body, extract
  the directive, parse `key=value` pairs on `;`, `re.sub` it out of `body`.
  Store on `SourceSection` as new slots `targets: frozenset[str]` and
  `mentions_ok: bool`. Log a warning for an unknown key so typos surface.
- `SourceSection.__slots__` (`context.py:39`) gains `targets`, `mentions_ok`.
- `_matches` (`context.py:66-85`) unchanged — it stays the fallback.
- `sources_for` (`context.py:88-106`): if `section.targets`, match on
  `entity.concept_id in section.targets` **only**; else fall back to the
  existing slug match. Explicit beats fuzzy, never both.

### Phase 2 — I-002 secondary attachment (`context.py`, `prompts.py`)

The failure mode to design against is not retrieval, it is *voice*: a ruling
about Nyruk pasted into Nyrella's prompt invites a paragraph about Nyruk inside
Nyrella's entry. Primary and secondary sections therefore must not share a
prompt block.

- New `SOURCE_BUDGET_CHARS = 20_000` and `MAX_SECONDARY_SECTIONS = 6` beside
  `EXCERPT_BUDGET_CHARS` (`context.py:31`).
- New `secondary_sources_for(entity, sections, primary)` — reuse the mention
  rendering the prompt already builds (`synthesize._render_mentions`) rather
  than re-reading transcripts: a section is secondary for this entity when its
  heading name (or a `targets` entity's canonical name) occurs in the entity's
  mention text and it is not already primary and `mentions_ok`. Rank by longest
  matched name, truncate to the two limits.
- `cli.py:188` passes both; `synthesize.synthesize_entity_body` takes a new
  `secondary` argument and both hashes enter `_cache_key`
  (`synthesize.py:167-183`) — the existing `sources` hash slot pattern extends
  directly.
- `prompts.py`: new `SYNTH_SECONDARY_TEMPLATE`, injected after `{sources}` in
  `SYNTH_USER_TEMPLATE` (`prompts.py:178-190`). Its clause, in substance:
  *these rulings concern other entries mentioned here; obey them for spellings,
  identity and facts, but do not write a section about them, and do not list
  them under "Offene Konflikte".*
- Extend `SYNTH_SOURCES_TEMPLATE` (`prompts.py:192-215`) with the
  `DARSTELLUNG:` clause: presentation directives, obeyed silently, never quoted.

### Phase 3 — rewrite `Kanon_Entscheidungen.md`

`knowledge/sources/Kanon_Entscheidungen.md`, one pass top to bottom:

1. Merge the duplicate `### Ezhura` / `### Nyrella` / `### Silberkerne`; drop
   the empty second `### Die Prinzessin` (:328).
2. Delete the superseded `ENTSCHEIDUNG (überholt …)` at :472-475; promote the
   `KORREKTUR (GM/Noah 2026-08-29)` at :477-482 to be the ruling. Sweep for any
   other live/dead pair.
3. Add `<!-- okf: entity=… -->` to every remaining heading, resolved against
   `knowledge/entity_registry.yaml` (`concept_id` + `canonical_name`). The six
   ambiguous person headings get the *one* correct ID each. The four stale
   headings get their current ID and a heading text matching the bundle title.
4. `HINWEIS ZUR DARSTELLUNG:` → `DARSTELLUNG:`; `HINWEIS:` (:294) folded in.
5. Tighten prose per the rules above — fact first, one claim per ruling.
6. Move the four policy sections into `SYNTH_SYSTEM`; leave a pointer line in
   the file's preamble saying where they went.
7. Rewrite the `# Wie das funktioniert` preamble (:1-22). It is never loaded
   (`_HEADING_RE` starts at `##`) so it is pure human documentation — correct it
   while there: line 17 ("delete the finished file from `knowledge/conflicts/`")
   is redundant, `emit.prune_conflicts` (`emit.py:370-394`) already deletes it.
   Document the `<!-- okf: -->` line and the three-marker vocabulary; update the
   copy-paste template at :606-613.

### Phase 4 — guardrails and the two doc bugs

Tests are their own section below. The doc fixes:

- `emit.py:340-342` docstring is wrong: it says to record a ruling "under an
  `ENTSCHEIDUNG:` heading". `ENTSCHEIDUNG:` is a paragraph prefix; a real
  `### ENTSCHEIDUNG: …` heading slugifies to `entscheidung_…` and matches
  nothing. `knowledge/conflicts/README.md:82` already has it right.
- `knowledge/conflicts/README.md`: document the `<!-- okf: entity=… -->` line
  and the three-marker vocabulary — it is the file a GM actually reads when
  clearing the conflict queue.
- `docs/architecture/IMPROVEMENTS.md`: mark **I-002 done**, pointing at the
  commit. Do not delete the entry — the file's own header says a resolved
  proposal records its outcome.

### Phase 5 — bump and re-run

Bump `PROMPT_VERSION` (`prompts.py:11`) `"5"` → `"6"` **once, last**. It
invalidates every synth cache entry, so all of Phases 1-4 must land before it —
one full re-synthesis, not four. This cost is inherent to I-002 and was accepted
in scoping (`IMPROVEMENTS.md:36` flags it).

---

## Testing strategy

Every defect in the Context section is a *silent* failure — the pipeline runs
green, the bundle looks plausible, and the ruling simply does not land. That is
the property to test against. The rule for this work: **no defect listed above
may be fixed without a test that fails on its return.**

The repo already has the two layers to do this in, and both should be reused
rather than invented:

- **Mechanism tests** — `tmp_path` fixtures, offline, no bundle. Pattern:
  `test_tiering_and_context.py::test_sources_match_across_punctuation_drift`.
- **Campaign-data tests** — read the real `knowledge/` tree, guarded by
  `pytestmark = pytest.mark.skipif(not CANON_FILE.exists(), …)`. Pattern:
  `test_canon_decisions.py`.

### Ratchets vs. hard zeros

`test_canon_decisions.py` uses *measured baselines* (`UNREACHED_RULING_BASELINE
= 9`, etc.) because it was written against a file that was already broken and
could only ratchet downward. After Phase 3 that reason is gone. Every one of the
three drops to **hard zero**, with the comment rewritten from "measured on this
branch, do not wave through" to "must stay zero — see plan". A baseline that can
be raised is an invitation to raise it; the new checks below start at zero and
have no baseline constant at all.

### Defect → test map

| # | Defect (from Context) | Test | Layer | Fails when |
|---|---|---|---|---|
| 1 | Misrouting between same-name entities | `test_rulings_do_not_ground_more_than_one_person` — existing, baseline `6` → `0` | data | a ruling grounds two person entities again |
| 1 | Explicit routing regresses to fuzzy | **new** `test_explicit_entity_beats_slug_match` | mechanism | an `entity=` section also attaches by slug, or the wrong Harald matches |
| 2 | Rename silently kills a ruling | **new** `test_every_ruling_targets_a_live_concept` | data | any `entity=` ID is absent from `entity_registry.yaml` |
| 2 | Ruling reaches nobody | `test_every_ruling_reaches_at_least_one_entity` — existing, baseline `9` → `0` | data | a ruling matches zero entities |
| 3 | Superseded ruling left in file | **new** `test_no_superseded_rulings` | data | the file contains `überholt`, `veraltet`, `KORREKTUR`, or `siehe … darunter` |
| 4 | Invented marker word with no prompt support | **new** `test_only_known_markers` | data | a paragraph opens with an ALL-CAPS word + `:` outside `{ENTSCHEIDUNG, DARSTELLUNG}` |
| 5 | Duplicate headings merged into one prompt | `test_no_duplicate_headings` — existing, baseline `3` → `0` | data | a heading repeats with a non-empty body |
| 6 | **Directive leaks into the prompt** | **new** `test_directive_is_stripped_from_section_text` | mechanism | `<!-- okf:` survives into `SourceSection.text` |
| 6 | …and into the bundle | **new** assertion in `test_bundle_invariants.py` | data | `<!-- okf:` appears anywhere under `knowledge/bundle/` |
| 7 | Typo in a directive key, silently ignored | **new** `test_unknown_directive_key_warns` (`caplog`) | mechanism | an unknown key parses without a warning |
| 8 | Unbounded sources blow the prompt | **new** `test_secondary_sources_respect_budget` | mechanism | output exceeds `SOURCE_BUDGET_CHARS` / `MAX_SECONDARY_SECTIONS` |
| 9 | I-002 voice bleed | **new** `test_secondary_sections_stay_out_of_primary_block` | mechanism | a secondary section lands in the `{sources}` string |
| 9 | Settled conflict comes back | `test_no_conflict_regression.py` — append `characters/nyrella`, `npcs/tyrael` to `tests/data/resolved_conflicts.txt` | data | either conflict reappears in `knowledge/conflicts/` |
| 10 | Ruling written for a brief-tier entity = no-op | **new** `test_ruling_targets_are_not_brief_tier` | data | an `entity=` target computes to `brief` (never reaches synthesis) |
| 11 | Cache over- or under-invalidates | **new** `test_cache_key_tracks_secondary_sources` | mechanism | changing `secondary` leaves `_cache_key` unchanged, or an untouched entity's key moves |

### The three that matter most

Ranked by *likelihood × silence*, since that is what makes a defect survive:

1. **#6, the leaked directive.** A `<!-- okf: entity=… -->` reaching the prompt
   is a new failure mode this plan itself introduces, it is invisible in
   rendered markdown, and the model will happily paraphrase it into an entry.
   Two tests, one at each end of the pipe — the mechanism test catches it in
   milliseconds, the bundle invariant catches it if the mechanism test's fixture
   drifts from the real file's formatting.

2. **#2, the rename.** This is the defect that produced four of the nine dead
   rulings, and it recurs every time an entity is retitled — a routine, frequent
   operation done in a different file for unrelated reasons. `entity_registry.yaml`
   carries a `retired:` list of renamed concept IDs; the test should resolve a
   dead target against it and say *"`locations/lenra` was renamed to
   `npcs/landra_die_hag` — update the directive"* rather than just failing.
   A test that names the fix is the one that gets fixed instead of skipped.

3. **#10, brief tier.** Currently invisible in every direction: no test, no log
   line, no diff. A GM can write a ruling, re-run, see nothing change, and have
   no way to learn that `cli.py:180-182` returned before synthesis was reached.
   The failure message must name the remedy (`important: true` in
   `entity_rules.yaml`), because the remedy is documented nowhere the GM looks.

### Fixture for the mechanism tests

One shared `tmp_path` fixture, deliberately built to reproduce the real file's
hard cases rather than a clean toy:

```python
# two same-name persons, one explicitly routed, one not
"### Harald (Freibeuter)\n<!-- okf: entity=npcs/harald_freibeuter -->\n\n"
"ENTSCHEIDUNG: Freibeuter-Kapitän mit Rapier.\n\n"
"### Harald (Dämon)\n<!-- okf: entity=npcs/harald_daemon -->\n\n"
"ENTSCHEIDUNG: Magier-Dämon mit Seelenstein.\n\n"
# short name: must match a whole slug token, not a substring
"### Nox\n<!-- okf: entity=npcs/nox -->\n\nENTSCHEIDUNG: männlich.\n\n"
# no directive: slug fallback must still work
"### Nerithis, Mutter der Fluten\n\nGöttin der Ozeane.\n"
```

`test_sources_match_across_punctuation_drift`
(`test_tiering_and_context.py:57-80`) already covers the Vhar'Zul/Vhar Zul slug
case and the "h1 is not a section" rule — extend that file rather than
duplicating its fixture.

### What is *not* tested, and why

- **That the model obeys a ruling.** The chain from an edited `ENTSCHEIDUNG:` to
  a vanished conflict file is probabilistic — the model must choose to omit the
  `# Offene Konflikte` bullet before `prune_conflicts` (`emit.py:370-394`) can
  delete anything. No unit test can pin that. `test_no_conflict_regression.py`
  is the substitute: it catches the *outcome* after a real run, on the specific
  conflicts a human already settled. Adding the two I-002 cases to that ledger
  is the closest thing to a regression test for "the ruling actually worked".
- **Prompt wording.** Asserting on `SYNTH_SOURCES_TEMPLATE` text pins prose that
  is meant to be tuned. `PROMPT_VERSION` already forces re-synthesis when it
  changes; that is the guard that matters.
- **No new LLM calls in CI.** Every test above is offline. The data-layer tests
  read files already in the repo; the mechanism tests use `tmp_path`.

---

## Verification

```bash
cd services/kb && .venv/Scripts/activate
pytest tests/test_canon_decisions.py -v          # the three baselines now 0
pytest tests/test_tiering_and_context.py tests/test_no_conflict_regression.py
pytest tests/test_bundle_invariants.py
pytest                                            # full suite
```

Then a real run and a diff read:

```bash
python -m pnp_okf.cli run
git diff -- knowledge/
```

Four things to check by eye in that diff, in order of how likely they are to be
the thing that went wrong:

1. **No `<!-- okf:` anywhere in `knowledge/bundle/`.** Directive leaked into a
   prompt and the model echoed it.
2. `knowledge/conflicts/` — `npcs__harloen.md` and the other three open files:
   did the ones covered by a ruling disappear? Note the chain is
   probabilistic, not deterministic (the model must *choose* to omit the
   `# Offene Konflikte` bullet, then `prune_conflicts` deletes the file), so a
   survivor means re-reading the ruling's wording, not a code bug.
3. `bundle/splitter_des_ewigen/characters/nyrella.md` — the I-002 target case.
   The Nyruk/Nairuk spelling conflict must be gone **and** the entry must spell
   it `Nyruk`. Same for `npcs/tyrael` (Basul/Vasul).
4. The six formerly-ambiguous pairs — `npcs/harald_*`, `npcs/hendrik*`,
   `npcs/hans*`, the two Adeligas — each entry must now carry only its own
   ruling. Grep each pair for the other's distinguishing noun (Rapier vs.
   Seelenstein; Bergnomaden vs. Heinrich-Farm).

Also confirm cost behaviour: a second `pnp run` with no edits must be all cache
hits, and editing one `ENTSCHEIDUNG:` must re-synthesize only the entities that
section routes to (primary + its secondaries), not the bundle.

---

## Findings on the rest of `knowledge/sources/` (out of scope, recorded)

Not part of this plan; worth an `IMPROVEMENTS.md` entry later.

- **`Wiki_Team_Text.md` is structurally near-unreachable.** Its `## <Character>`
  bodies are empty because `_HEADING_RE` matches `##`–`####` and the next `###
  Überblick` truncates the parent. The actual prose lives under generic
  `### Überblick` / `### Rolle in der Kampagne` / `### Belege` headings whose
  slugs match no entity. 43 KB of curated wiki text that mostly reaches nobody.
- `Wiki_Team_Text.md:348` contains the literal string
  `[9] ENTSCHEIDUNG: Der Jen, aus Kanon_Entscheidungen.md` inside a `### Belege`
  section — a stray authority token in a file that declares itself non-canon.
  Harmless only because `belege` matches nothing.
- **`Der_Splitter_des_Ewigen.md` (77 KB) splits into 8 chapter sections of
  ~10 KB.** Chapter titles are not entity names so they rarely match — but a
  single match injects 10 KB unbudgeted. Phase 2's `SOURCE_BUDGET_CHARS` caps
  this as a side effect.
- `Der_Splitter_des_Ewigen.md` and `Der_Splitter_des_Ewigen_Buch1.md` overlap in
  content and are both globbed.
- **Brief-tier entities never receive sources at all.** `cli.py:180-182` returns
  `render_brief_body` before synthesis, so `sources_for` is never called. An
  `ENTSCHEIDUNG:` for a brief entity is a guaranteed no-op that no test catches.
  The remedy (`important: true` in `entity_rules.yaml`) is documented nowhere the
  GM would look.
