# Plan — OKF v0.2: trust tiers, structured sources, and relationship edges

**Status:** planned, 2026-09-05. Nothing implemented; no code changes on this
branch. Implementation belongs on its own branch.
**Decides:** which OKF v0.2 frontmatter families the emitter adopts, how the
`status` key collision is resolved, and what shape a relationship edge takes in
the bundle — now and at full build-out.
**Follows:** [../audits/2026-09-05-okf-v0.2-handoff.md](../audits/2026-09-05-okf-v0.2-handoff.md)
(the research; includes the Google Knowledge Catalog comparison).
**Related:** [ADR-001](ADR-001-knowledge-layer.md) (bundle is the system of
record; typed edges are the ADR-001 revisit trigger for a derived graph index);
[ADR-003](ADR-003-no-llm-downstream.md) (LLM calls live in `pnp_okf` only);
`knowledge-catalog/okf/SPEC.md` §5, §6, §7, §13.
**Cost:** phases 0–3 need **no** `PROMPT_VERSION` bump and no re-synthesis — all
derivation is post-synthesis and deterministic. The Vision section does need one.
**Measured:** 2026-09-05 against the current bundle — 1099 entity concepts + 67
sessions, 1812 mentions, 54 ENTSCHEIDUNG-routed concepts, 73 pages with a
`## Beziehungen und Verbindungen` section (459 bullets).

## Context

`knowledge-catalog` vendors the OKF spec, which moved 0.1 → 0.2 while our
emitter stayed on 0.1. The research established that OKF's Entry/Aspect model is
Google's Knowledge Catalog model minus the live service, so adopting v0.2's
additive frontmatter families *is* adopting Google's approach, file-based.

Three gaps, all in `services/kb/src/pnp_okf/`:

1. **Trust is unrecorded.** 54 concepts are grounded by a GM `ENTSCHEIDUNG:`
   canon ruling. Nothing in the bundle says so — answering "which facts did a
   human confirm?" means re-running the routing logic by hand against
   `Kanon_Entscheidungen.md`.
2. **Citations are prose only.** `# Belege` is markdown; the inline `[P-08]`
   markers resolve against nothing in the file. Any consumer wanting sources
   must parse German prose.
3. **Edges are invisible.** The only inter-concept structure is an untyped
   markdown link, so a relationship asserted under
   `## Beziehungen und Verbindungen` is indistinguishable from an incidental
   name-drop in `## Chronologie`.

Outcome: concepts carry `generated`, `verified`, `sources[]` and
`relationships[]`; `status` stops colliding with the spec; no LLM re-run and no
new prose parsing.

## Constraints that shape every phase

Measured, not assumed. Violating any of these is expensive.

- **Never add a field to `CanonicalEntity`.** `_cache_key` hashes
  `entity.model_dump(mode="json")` (`synthesize.py:227`) — one new field
  invalidates ~1000 synth cache entries and forces a full DeepSeek re-run (last
  run: 293 calls / 96 min; a full miss is ~1000). All new data travels as
  keyword arguments to `emit_entity`. No existing test catches this.
- **Never call `_now_iso()` in the new keys.** `write_if_changed` (`okf.py:61`)
  keeps mtimes meaningful for the run summary (`cli.py:202-304`); a wall-clock
  value churns 1099 files every run.
  `test_incremental_ingest.py::test_second_run_over_identical_inputs_writes_nothing`
  is the canary — run it first.
- **`# Belege` prose stays exactly as it is.** `pnp-export-data/02_extract.py:38`
  regexes `Session (\d{4}-\d{2}-\d{2})` out of the whole body and gates on
  `MIN_SESSIONS = 2`. Reshaping Belege silently drops most wiki pages.
- **Keep inline `[P-08]` markers; do not switch to the spec's `[^footnote]`
  syntax.** `pnp-export-data/md2wiki.py:26-27` parses exactly that form. Same
  join semantics, different marker — a deliberate deviation from §5.1.
- **Citation labels are all-or-nothing.** `citation_labels` returns `None` if any
  URL is missing from `episodes.yaml`; **122 of 1099 concepts are in that
  state**. Every id set must be `labels or [str(i) for i in range(1, n+1)]`,
  never `episodes.id_for_url` per mention.
- **`_order_frontmatter` drops `None` and `""` but keeps `[]`**
  (`okf.py:38-46`) — guard each new key at the call site, matching the existing
  `if entity.aliases:` at `emit.py:326`.

---

## Phase 0 — spec hygiene

Ship alone, ~20 minutes, no design content.

- `ARCHITECTURE.md:13` — "spec v0.1" → v0.2.
- `emit.py:329` — `status` → `review_status`, freeing `status` for the spec's
  `draft|stable|deprecated` (§5.4). 12 bundle files carry it; nothing in
  `pnp-export-data`, `services/summary` or `services/dashboard` reads it.
- `tests/test_identity.py:193` — the one assertion that breaks.

Do **not** touch `emit_conflict`'s `status: open` (`emit.py:367`): conflict files
live outside the bundle, no OKF consumer reads them, and renaming costs two more
test edits for nothing. Do **not** start emitting `status` — §5.4 says absent ⇒
`stable`, and every concept is stable.

## Phase 1 — trust tiers (`generated` + `verified`)

Most value per line: the only phase that adds information the bundle does not
already contain in some form.

**`context.py`** — one function, ~6 lines, reusing `_primary_hits`
(`context.py:240`) so both directive routing and the slug fallback keep working:

```python
def ruling_targets(
    entities: list[CanonicalEntity], sections: list[SourceSection]
) -> set[str]:
    """Concept ids grounded by an ENTSCHEIDUNG: section (spec §5.3 human tier)."""
```

Filter on `s.text.lstrip().startswith("ENTSCHEIDUNG:")` — **not** `is_ruling()`,
which also matches `DARSTELLUNG:` (`context.py:46,102-105`). A presentation
instruction must not confer a trust tier.

**`emit.py`** — new keyword-only params (existing positionals 1-4 unchanged; six
test call sites depend on that):

```python
def emit_entity(
    bundle_dir, entity, body, index=None, *,
    labels: list[str] | None = None,
    verified: bool = False,
    relationships: list[dict] | None = None,
) -> tuple[list[str], str | None]:
```

In the frontmatter block (`emit.py:317-330`), reusing the *exact* `ts` string
already computed for `timestamp` at `emit.py:324`:

```python
"generated": {"by": f"pnp_okf/{__version__}", "at": ts},
```

and, when `verified`, `{"by": "human:gm"}` — **no `at`**. §5.3 derives the tier
purely from the `human:` prefix; inventing a date from the last mention would
assert something false. Keep the legacy `timestamp`: §13.1 prescribes emitting
both during migration, and `pnp-export-data/02_extract.py:49` reads it for
Sessions.

Comment that bumping `__init__.py:__version__` rewrites all 1099 files through
`generated.by` — correct, but someone will otherwise discover it via a surprise
diff.

**`cli.py`** — one line before the emit loop (`source_sections` is already local
at `cli.py:194`), one at the call site:

```python
verified_ids = ruling_targets(entities, source_sections)
...
unresolved, conflicts = emit_entity(
    paths.bundle_dir, entity, body, index,
    verified=entity.concept_id in verified_ids,
)
```

Churn: 1099 files, ~+3300 lines (`generated`) + 54 files × 2 (`verified`).

## Phase 2 — `sources[]` and the citation-label fix

**Fix the latent backfill bug first (TDD — it fails today).** `cli.py:251-253`
relabels the body, then `emit.py:307-308` appends `render_belege_section(entity)`
when the model omitted `# Belege` — emitting unlabelled `1. Session …` lines
after the inline markers became `[P-08]`. Zero occurrences right now, but it
fired historically (`tests/test_bundle_invariants.py:162-178`). Threading
`labels` through kills the whole class.

**`synthesize.py`** — one optional param; both existing call sites stay
byte-identical:

```python
def render_belege_section(entity: CanonicalEntity, labels: list[str] | None = None) -> str:
```

Line 193 emits `[{labels[i-1]}] Session …` when labels are present, else today's
`{i}.` form.

**`emit.py`** — a module-private helper plus the `sources` key:

```python
def _source_entries(entity: CanonicalEntity, labels: list[str] | None) -> list[dict]:
    ids = labels or [str(i) for i in range(1, len(entity.mentions) + 1)]
    return [
        {"id": sid, "resource": m.url, "last_modified": f"{m.date}T00:00:00Z"}
        for sid, m in zip(ids, entity.mentions, strict=True)
    ]
```

Three keys per entry, deliberately lean — the human-readable label already lives
in Belege. `sources` goes last in the frontmatter literal (longest block).
`emit.py:308` becomes `render_belege_section(entity, labels)`.

**`cli.py`** — stop discarding the `labels` already computed at `cli.py:251`.

The payoff: `sources[].id` is the *same* id as the inline `[P-08]` marker, making
the body's citations resolvable against frontmatter (§5.1's join-key idea, our
marker syntax). Honestly: `md2wiki` already resolves those markers against its
own episode map, so the beneficiaries are the KB API (`/concepts/{cid}` passes
raw frontmatter through, `api.py:281-286`) and spec-generic consumers — not the
wiki.

Churn: 1099 files, ~+6500 lines.

## Phase 3 — `relationships[]`, untyped

**Decided: untyped edges now.** A German keyword table was measured against all
459 bullets and classified **87 % as generic `related`**, with false positives
that would poison the system of record (`verführt` → `leads`; "gehört zu den
Gefährten von Rotunas" → `member_of` pointing at a *person*). Direction is not
recoverable from a bullet either — the same keyword means opposite orientations
depending on which page you are on. Reciprocity would then copy each wrong
`kind` into a second concept's frontmatter, on a page whose own prose never made
the claim. Typed edges are the Vision below, and they need the transcript.

The signal that *is* free and correct: **which section the link came from**. A
link under `## Beziehungen und Verbindungen` is an asserted relationship; one
under `## Chronologie` is an incidental mention.

**`links.py`** — one function, ~40 lines, no new module (it already owns
`ConceptIndex` and every body-parsing regex; a module for one function is an
interface with one implementation):

```python
def relationship_edges(
    bodies: dict[str, str], index: ConceptIndex, live: set[str]
) -> dict[str, list[dict]]:
```

Per body: find the `Beziehung…` heading, slice to the next `^#{1,6} `, iterate
`- `/`* ` bullets, take the head (bold span, or text before the first `:`), try
its `.md` link first then the plain name, `index.resolve` (the same function
`normalize_body` uses — bodies here are pre-normalization, which is fine). Emit
`{"target": cid, "note": <truncated bullet prose>}`, then a second pass writing
the mirror edge onto the target. Measured: 360 of 459 bullets resolve (305 via
link, 56 via bare name); strip a leading `^Zu[rm]?\s+` to recover
`**Zur Gilde:**` heads.

Three filters the naive version misses:
- **Drop self-edges** — `normalize_body` degrades self-links to plain text
  (`links.py:259-263`); the edge map must match.
- **Drop session targets** — `build_concept_index` (`emit.py:47`) seeds
  `sessions/<date>`, and sessions are written at `cli.py:207`, *before* the
  entity loop; a reciprocal edge onto one lands in an already-closed file.
  Restrict to `live = {e.concept_id for e in entities}`.
- **Sort by target before emit**, or dict iteration order leaks into the file and
  defeats `write_if_changed`.

**`cli.py`** — gate on partial runs, which would otherwise strip relationships
from the files they touch: `edges = {} if partial_run else relationship_edges(...)`.
(Not a new hazard class: `emit_indexes` already rewrites every index from a
partial entity set, so a partial run's bundle is already not committable.)

**`validate.py`** — two checks in the existing per-file loop
(`validate.py:145-166`, frontmatter already parsed at `:152`):
`bad_relationship_targets` and `asymmetric_relationships`, extending
`ValidationReport.ok` (`:63`) and `summary()` (`:74`).

Note while in this file: `fix_bundle` (`validate.py:266`) passes the whole file
text including frontmatter to `normalize_body`, and bare URLs are not protected
by `_LINK_TARGET_RE`, so a `spelling:` rule can in principle rewrite a
`resource:` URL. Pre-existing (Session `resource:` is already exposed);
`sources[].resource` multiplies the surface 1812×. One-line comment, not a fix.

Churn: ~300 files, ~+2000 lines.

## Verification

Per phase, from `services/kb`:

```bash
python -m pytest tests/test_incremental_ingest.py   # idempotency canary — run first
python -m pytest                                    # full offline suite (47 files)
ruff check .
PNP_REQUIRE_BUNDLE=1 python -m pytest               # bundle-backed tests must not skip
```

New tests:
- P0 → `test_identity.py`: `review_status` set, `status` absent.
- P1 → new `test_okf_v02.py`: `generated.at == timestamp`; `generated.by` matches
  `^\S+/\S+$` (§7 actor convention); `verified` absent by default.
  `test_canon_decisions.py`: `ruling_targets` returns exactly the
  ENTSCHEIDUNG-routed ids and **excludes a DARSTELLUNG-only section**.
- P2 → `test_okf_v02.py`: `sources[].id` equals the inline markers; falls back to
  `1..n` when `citation_labels` returns `None` (the 122-concept path); the
  backfilled Belege list uses labels — write this one first, it fails today.
- P3 → new `test_relations.py`: bullet parsed from a link head and from a plain
  bold head; self-edge dropped; session target dropped; mirror produced;
  **running the stage twice is byte-identical**. Plus the two validate checks.
- Optional guard for the cache trap:
  `test_cache_key_unchanged_by_emit_only_metadata` in `test_synthesize_cache.py`
  (today's tests only vary `secondary`).

End to end, after the phases land: one `pnp run` with warm caches. Confirmed
LLM-free — `extract_session` returns at `extract.py:186` and
`synthesize_entity_body` at `synthesize.py:310`, both before `build_client`;
brief tier never enters synthesis. `DEEPSEEK_API_KEY` must still be set
(`DeepSeekConfig.from_env()` at `cli.py:154` raises without it) even though
nothing is called. Then `pnp validate` and inspect the single bundle diff.

**Land phases 0–2 as separate commits on one branch, tests green, then one
regeneration commit** — `write_if_changed` makes that final run produce exactly
the union diff, and three 1099-file regenerations are worse to review than one.
Phase 3 rides the same branch or follows; keep its commit separate either way.

## Deliberately not doing (in these phases)

- **`kind` on relationships** — no trustworthy *deterministic* source. See Vision.
- **`verified.at` and a `verified=YYYY-MM-DD` directive** — no date exists to
  record; the trust tier does not need one. Would also need
  `SourceSection.__slots__` (`context.py:83`) to grow.
- **Renaming `emit_conflict`'s `status: open`** — different problem, outside the
  bundle.
- **`okf_version: "0.2"` in the root index** — §12 permits it, but it breaks
  `test_pipeline_offline.py:95` and `test_okf.py:35` and changes `write_index`'s
  contract for a MAY.
- **Reciprocity sold as a bug fix** — the motivating audit number is stale.
  Re-measured: 42/47 factions already link a person (was 22/42). NPC→faction at
  22 % is the remaining gap, and only the 73 pages with a Beziehungen section can
  move it.
- **API/wiki plumbing for the new keys** — `/concepts/{cid}` already returns them
  raw; the `/concepts` list and `/status` projections (`api.py:266-274,334-343`)
  stay until something needs them.

---

# Vision — typed relationships extracted from the transcript

Phase 3 ships the *shape* of an edge without its semantics. This section is
where edges should end up, and why the typed version has to be extracted at the
transcript, not inferred from synthesized prose. Not scheduled; written down so
Phase 3's frontmatter is forward-compatible rather than a dead end.

## Why the transcript is the only honest source

Three insertion points exist for relation extraction. Only one has the evidence:

| Where | Sees | Verdict |
|---|---|---|
| **Extract stage** (`extract.py`, one LLM call per session over the diarized dialogue) | the actual spoken scene: who joined what, who betrayed whom, *when* | **This one.** Direction, timing and the triggering event are all present and unambiguous |
| Synthesis stage (`synthesize.py`, per entity) | mention notes + source sections + transcript excerpt windows | Entity-scoped, already-summarized; ~1000 calls on cache miss |
| Post-hoc typing pass over the 459 bullets | prose the model already wrote | Inherits every summarization loss; cannot recover direction (measured) |

[ADR-003](ADR-003-no-llm-downstream.md) fixes the boundary: LLM calls belong to
`pnp_okf`, never to a consumer. Relation extraction at the extract stage sits
squarely inside it. A post-hoc typing pass in the wiki agent would violate it.

The decisive property is **temporality**. Campaign relationships are not facts,
they are events with a beginning and sometimes an end: alliances break,
characters die, a splinter faction forms, Lindo becomes bound to Vasul in one
session and that binding develops in later ones. A session-scoped extraction
gives every edge its `since` for free (the session date) and lets a later
session *end* it. Prose synthesized per entity has already flattened that.

## Extraction shape

`SessionExtraction` (`models.py:180-189`) gains a sibling list to `entities`,
extracted in the same call that already reads the dialogue — so the marginal
cost is a longer prompt over 67 sessions, not a new pass:

```python
class EntityRelation(BaseModel):
    subject: str        # entity name as spoken
    predicate: str      # closed vocabulary, Literal[...] so structured output enforces it
    object: str         # entity name as spoken
    note: str           # what the transcript actually says
    citation_ts: str    # HH:MM:SS — same provenance contract as EntityMention
    polarity: Literal["asserted", "ended"]
```

`subject`/`object` are raw spoken names on purpose: they then flow through the
*existing* `resolve.py` machinery — aliases, `merge:`, `split:`, `never_merge:`,
`canonical_name:` — that already turns mention names into concept ids. No second
identity system. `_call_llm_structured` (`extract.py:79`) already constrains
output against a pydantic schema, so a `Literal` predicate is enforced at the
API level rather than validated after the fact.

## The vocabulary — closed, and typed by endpoint

The reason to close the vocabulary is not tidiness; it is that a closed set
makes edges *checkable*. Each type declares its legal endpoint types, so
`member_of` between two NPCs is a detectable extraction error — exactly the
class of mistake the keyword table produced ("member of a human being"). This is
Google's `EntryType`-requires-`AspectType` idea, applied to edges.

A `RELATION_TYPES` table in `models.py`, next to the existing `SUBTYPES` closed
vocabulary (`models.py:267-281`) which is the precedent to copy:

| Group | Type | Direction | Inverse | Legal endpoints |
|---|---|---|---|---|
| Social | `ally_of`, `enemy_of`, `family_of` | symmetric | itself | person ↔ person |
| Social | `mentor_of`, `serves` | directed | `student_of`, `served_by` | person → person |
| Affiliation | `member_of` | directed | `has_member` | person → faction |
| Affiliation | `leads` | directed | `led_by` | person → faction/location |
| Spatial | `located_in`, `originates_from` | directed | `contains`, — | any → location |
| Spatial | `rules_over` | directed | `ruled_by` | person/faction → location |
| Possession | `carries`, `owns`, `created` | directed | `carried_by`, `owned_by`, `created_by` | person → item |
| Divine | `worships`, `bound_to`, `avatar_of` | directed | `worshipped_by`, —, — | person → deity |
| Narrative | `participated_in`, `caused` | directed | `had_participant`, `caused_by` | any → event |
| Factional | `allied_with`, `at_war_with` | symmetric | itself | faction ↔ faction |
| Factional | `splinter_of` | directed | `has_splinter` | faction → faction |

`related` stays as the escape hatch for a real relationship that fits nothing —
the same role it plays in Google's fixed set, and what Phase 3's untyped edges
become when this lands.

## Emitted shape

Folding per-session relations into per-concept edges is deterministic once
extraction is typed. Each edge cites the evidence with the **same ids as
`sources[]`**, which is what makes Phase 2 load-bearing rather than decorative:

```yaml
relationships:
  - target: factions/gilde_von_ehrenfels
    kind: member_of
    since: '2025-06-17'
    sources: [P-12]
  - target: deities/vharzul
    kind: bound_to
    since: '2025-09-02'
    sources: [P-22, P-24, P-31]
  - target: npcs/harloen
    kind: ally_of
    since: '2026-07-29'
    until: '2026-08-04'        # a later session asserted polarity: ended
    sources: [S1-01-A, S1-02-A]
```

Corroboration comes free: `len(sources)` is how many independent sessions
asserted the edge, which is the honest version of a confidence score (and
matches §5.1's position that credibility is *inferred* from signals, not
stored). Reciprocity becomes correct rather than guessed — the inverse comes
from the table, not from a keyword.

## What it unlocks

- **A derived graph index.** [ADR-001](ADR-001-knowledge-layer.md) freezes
  `graph/` but names a rebuilt-from-the-bundle index as the revisit trigger.
  Typed, directed, cited edges are precisely the missing input — a Neo4j load
  becomes a bundle read, with no prose parsing anywhere.
- **Queries without an LLM.** "Who was in the Gilde during session 12?" is a
  filter over `kind`, `since`, `until` — answerable by the read-only API, inside
  the ADR-003 boundary.
- **Deterministic wiki infoboxes.** `pnp-export-data` could render a
  relationship table per page from frontmatter, no model, no prose regex.
- **Conflict detection on edges.** Two sessions asserting contradictory
  `member_of` for the same subject is exactly the shape the existing conflict
  queue and `ENTSCHEIDUNG:` override loop already handle for facts.

## Costs and risks, stated plainly

- **One `PROMPT_VERSION` bump** → re-extraction of all 67 sessions. Cheap
  relative to synthesis (67 calls vs ~1000), but it also invalidates the synth
  cache, so bump **last and once**, exactly as
  [PLAN-canon-rulings-routing.md](PLAN-canon-rulings-routing.md) prescribes.
- **Relations must not live on `CanonicalEntity`** — the `_cache_key` trap from
  the Constraints section applies with full force. Fold them into a separate
  `dict[concept_id, list[Edge]]` built in `resolve.py` and passed to
  `emit_entity` as the same `relationships=` kwarg Phase 3 introduces. That is
  why Phase 3's signature is worth getting right now.
- **The model will assert edges the table has no room for.** A `Literal`
  predicate constrains the output; a `validate.py` endpoint-type check catches
  what slips through. Both are cheap and both fail loudly.
- **Extraction quality is unproven at this granularity.** Mentions are easy;
  relations require the model to track who did what to whom across a scene. Pilot
  on 3–5 sessions with hand-checked ground truth before committing a prompt
  version — the same discipline
  [TESTPLAN-entity-matching.md](TESTPLAN-entity-matching.md) applies to identity.
