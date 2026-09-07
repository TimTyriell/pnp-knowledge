# PIPELINE.md — how `pnp run` actually works

**Audience: an LLM agent about to change something in `services/kb`.** Read this
before touching the pipeline. Every line number and number below was verified
against the working tree on 2026-09-07; if a line number is off by a few, the
anchor name (`def …`) is authoritative.

> **Why this file exists.** Agents keep re-deriving the same five facts —
> the id-derivation chain, the emit ordering, what keys the caches, which rule
> families are id-keyed, and where the money goes — and keep drawing the wrong
> conclusion in the gap. Those five are §4, §6, §7, §5 and §8.

---

## 1. Fast facts

| | |
|---|---|
| Package | `services/kb/src/pnp_okf` |
| Venv | `services/kb/.venv/Scripts/python.exe` — **not** the repo-root `.venv`, which belongs to frozen `graph/` |
| Run tests from | `services/kb` (`pyproject.toml` sets `pythonpath = ["src"]`) |
| Suite | 266 passed, 1 xfailed (~68 s; the churn test alone is ~37 s) |
| System of record | `knowledge/bundle/splitter_des_ewigen/` — 1158 concept files, 6382 internal links |
| Registry | `knowledge/entity_registry.yaml` — **generated**, 1092 concept ids + a `retired:` ledger |
| Rules | `knowledge/entity_rules.yaml` — **hand-written, never rewritten by code** |
| Corpus | 66 sessions, German transcripts from `../pnp-crawl/transcripts_final` |
| Provider | DeepSeek, OpenAI-compatible SDK |
| Full rebuild | ~10.5 M tokens, **~$6.5 off-peak** |
| Warm re-emit | 18 calls, **~$0.05** |

**The single most important economic fact:** a rebuild costs ~130× a warm
re-emit. The pipeline is cheap to *run* and expensive to *invalidate*. Nearly
every cost mistake in this repo's history was a cache invalidation nobody
budgeted for.

---

## 2. Three repos, one direction

```
pnp-crawl  (private)      pnp-knowledge  (here)          pnp-export-data
audio -> transcript  ->   transcript -> knowledge   ->    knowledge -> wiki
                          OKF bundle in git               reads the KB API only
```

`pnp-export-data` is a pure client of the read-only API (`:8070`) and holds no
knowledge. It owns `wiki_pages.toml`, which maps **concept_id → wiki page** —
so **any concept_id rename is a cross-repo break.** Remember this in §4.

---

## 3. `pnp run` — the stage graph

`cli.py::_run_pipeline` (from `cli.py:203`). Order matters enormously; see §7.

| # | Stage | Anchor | Notes |
|---|---|---|---|
| 0 | mark run in flight | `cli.py:109` `_begin_run` | writes `state/run_in_progress.json`; finding one at startup means the previous run was killed, and that gets recorded to `history.jsonl` |
| 1 | load transcripts | `cli.py:206` | `--limit` / `--session` make it a *partial run*, which **disables the rename guard** |
| 2 | **extract** | `cli.py:221` `_extract_all` | 1 LLM call per uncached session, `ThreadPoolExecutor`, `--workers` default 8 |
| 3 | **resolve** | `cli.py:225` `resolve_entities` | pure function; no LLM. §4 |
| 4 | rename guard | `cli.py:228` `check_rename_safety` | refuses if >2% of registry ids vanish. Exit 2. Reads the *previous* registry |
| 5 | optional wipe | `cli.py:239` `shutil.rmtree` | only with `--clean` |
| 6 | build link index | `cli.py:256` `build_concept_index` | in-memory only |
| 7 | **synthesize** | `cli.py:290` | 1 LLM call per non-brief entity. **25–95 min. Every network failure lives here. Nothing is written yet.** |
| 8 | emit entities | `cli.py:305` `emit_entity` | first bundle write of the run |
| 9 | emit sessions | `cli.py:330` `emit_sessions` | **after** their link targets exist — see §7 |
| 10 | prune conflicts / orphans | `cli.py:339`, `cli.py:346` | orphan prune deletes files; guarded at 2% |
| 11 | write registry | `cli.py:359` `write_registry` | deliberately late, next to the indexes |
| 12 | indexes + log | `cli.py:360-361` | |
| 13 | **validate** | `cli.py:390` `validate_bundle` | gates the exit code — §9 |

> **The ordering is load-bearing, not incidental.** Everything expensive and
> failure-prone (step 7) happens before the first durable write (step 8), and
> each write depends only on what is already on disk. Preserve that property
> if you touch this function: sessions after entities, registry last.

**Subcommands** (`_build_parser`, `cli.py:601`): `run`, `extract`, `dedup`,
`check`, `visualize`, `validate`. **There is no emit-only subcommand** — `run`
is the only path to a bundle, and with warm caches it is nearly free.

---

## 4. Identity — the chain everyone re-derives

**A concept_id is derived from the LLM's chosen wording.** This is the root of
most trouble in this repo.

```
concept_id = TYPE_DIR[type] + "/" + slugify(apply_spellings(llm_name))
```

- `slugify` — `okf.py:22`. Lowercase, umlaut transliteration (ä→ae, ö→oe, ü→ue, ß→ss), non-alphanumerics → `_`.
- `_default_concept_id` — `resolve.py:30`. Applies `spelling:` rules **before** slugify.
- The typed id in frontmatter (`NPC_HEXE`) is `ID_PREFIX[type] + "_" + slug.upper()` (`models.py:222`) — **also derived, therefore equally unstable.** There is no stable id in this system.

### Resolution order (`resolve_entities`, `resolve.py:592`)

First match wins:

1. `split:` by `(name, date)`
2. `split:` by `(name, session_id)`
3. `merge:` / alias override by lowercased name
4. slug override — `slug_overrides[slugify(raw name)]`
5. **live-alias reanchor** — `_reanchor_to_live_alias`, fuzzy ≥0.9 against aliases of *live* concepts. **Only fires when the naive `default_id` is not already an established registry id** (without that guard it produces false positives: a PC "Gunther" folding into a cat "Günther")
6. `_default_concept_id` — the fallback that mints a new id
7. `_reanchor_to_retired` — fuzzy ≥0.9 against the `retired:` ledger
8. `ignore:` → mention dropped
9. Event span split — an Event spanning >`MAX_EVENT_SESSION_SPAN` (3) sessions gets `_<date>` appended
10. `canonical_name:` pin + `alias_block:` filter (display only, id unchanged)
11. `merge_near_duplicates` — §4.1

### 4.1 Auto-merge (`resolve.py:120`)

- **Fuzzy pass** — `difflib.SequenceMatcher` ≥ `FUZZY_RATIO` (0.9) on the slug with **tokens sorted first**, so "harald_der_alte" and "der_alte_harald" match.
- **Token-subset pass** — person types only, unique superset required.
- **Survivor** — `key=(concept_id in known_ids, len(mentions), concept_id)`. An id the registry already knows **never loses**. `known_ids` comes from the registry.
- `never_merge:` blocks both passes.
- Character and NPC share one identity space (`_same_space`, `resolve.py:54`).

### 4.2 Why this keeps hurting

Re-extraction resamples the model, which rewords names, which moves ids.
**Measured: 432 of 868 ids moved in one re-extraction.** Everything keyed on
concept_id detaches: rules, and `wiki_pages.toml` downstream.

The proper fix (assign a stable opaque id once; treat the name as a mutable
label) is what Graphiti/Zep, Cognee, Wikidata QIDs and Docusaurus `id`-vs-`slug`
all do. **Not implemented here** — the decision, its cheap hybrid form, and the
four triggers that should reverse it are written up in
[ADR-004](ADR-004-identity-primitive.md). Until then, treat every re-extraction
as a rename event and run the churn test (§10) before emitting.

---

## 5. `entity_rules.yaml` — rule families

Hand-written, never rewritten by code (that is *why* it is separate from the
generated registry — `write_registry` dumps YAML and would strip every comment,
i.e. the tool would erase the reasons for its own rules).

Merged with the registry by `_registry_data` (`resolve.py:255`); **rules win.**

| Family | n | Keyed by | Fragile to id drift? |
|---|---|---|---|
| `merge:` | 269 | name → concept_id | value only |
| `ignore:` | 144 | concept_id | **yes** |
| `important:` | 43 | concept_id | **yes** |
| `canonical_name:` | 32 | concept_id → name | **yes** |
| `split:` | 29 | (name, session) → concept_id | value only |
| `spelling:` | 22 | free text | no |
| `never_merge:` | 18 | concept_id pairs | **yes** |
| `alias_block:` | 12 | concept_id → names | **yes** |
| `unimportant:` | 1 | concept_id | **yes** |

`rules_doctor.py` reports dead rules: *inert* (source text no longer live —
safe to delete) vs *needs a decision*.

⚠ **Anything reading rules must go through `_registry_data`, not `yaml.safe_load`
on the registry alone.** `dedup.load_never_merge` did the latter and silently
ignored all 18 `never_merge:` groups.

---

## 6. Caching and cost — the real economics

### Cache keys

```python
# extract.py -- the key
key  = sha256(PROMPT_VERSION + cfg.model + session_id + dialogue)[:16]
# extract.py -- the path is now content-addressed (changed 2026-09-07)
path = cache_dir / "extract" / session_id / f"{key}.json"
```

```python
# synthesize.py:216 — the WHOLE serialized entity
key = sha256({v: PROMPT_VERSION, model, entity.model_dump(), tier,
              sha(sources), sha(excerpts), sha(secondary)})
```

**Four consequences you must internalise:**

1. ~~The key is versioned; the path is not.~~ **Fixed 2026-09-07.** Each key now lives at its own path, so a `PROMPT_VERSION` or model change no longer overwrites the previous entry and reverting one is free. ⚠ `.cache/` is gitignored — a machine holding a pre-2026-09-07 flat cache must migrate it (read each blob's `_key`, move to `<session>/<key>.json`) or it re-extracts at full price.
2. **The prompt *text* is not in the key**, only its version number. Change prompt content without bumping `PROMPT_VERSION` and the cache silently serves stale results.
3. **Changing `DEEPSEEK_MODEL` costs a full rebuild**, same as a prompt bump. Settle the model before starting one.
4. **Synthesis re-runs on any change to the entity** — a new mention note, a reordered alias, an `important:` flip, a tier change.

`PNP_EXTRACT_FREEZE_BEFORE` + `PNP_EXTRACT_FREEZE_VERSION` (`extract.py:38`)
pin sessions dated before a cutoff to an old prompt version. **Both vars
required**; comparison is lexicographic on the ISO date, cutoff exclusive.

### Prices (api-docs.deepseek.com, Sept 2026, per MTok)

| | input miss | input **cache hit** | output |
|---|---|---|---|
| `deepseek-v4-flash` | $0.22 / $0.44 | $0.007 / $0.014 | $0.66 / $1.32 |
| `deepseek-v4-pro` | $0.66 / $1.32 | $0.022 / $0.044 | $1.98 / $3.96 |

*off-peak / peak. Peak = 01:00–04:00 and 06:00–10:00 UTC, **Mon–Fri only**.*

- Provider-side cache is **exact-prefix only** — useless for 66 unique transcript bodies, useful for the shared system block. Put fixed instructions first, unique content last.
- **DeepSeek has no batch API.** Off-peak is the only "batch" discount.
- Extraction pro→flash saves ~$1.00 of a ~$6.5 rebuild (~15%), *not* 3×. The bill is dominated by **deep-tier synthesis completion tokens at $1.98/MTok**.
- `PNP_PRICE_IN_<MODEL>` / `PNP_PRICE_OUT_<MODEL>` are opt-in (`usage.py:51`) and currently **unset**, so no run has recorded a cost. Absent cost means "not priced", never "free".

---

## 7. Emit, links, and the crash window

### How session links are built (`emit.py:177`)

Session pages carry an "Auftretende Entitäten" bullet list. Each bullet targets
the concept id that `resolve_entities` actually assigned, looked up through
`mention_concept_index` (`emit.py:57`) — a `(session_id, citation_ts, note) →
concept_id` map built by walking the resolved entities back to their mentions.
`resolve_entities`' own signature is untouched; it has 25+ call sites.

A mention with no entry — `ignore:`d, or ambiguous between two entities — is
**left out of the list** rather than guessed.

> **Before 2026-09-07 this re-slugified the raw LLM name** (`slugify(mention.name)`),
> discarding every split/merge/ignore/spelling decision, with `normalize_body`
> fuzzy-rescuing the wreckage afterwards. Measured over 1846 mentions in the
> real corpus: 1475 landed correctly by luck, **320 only via the fuzzy rescue**,
> 7 pointed at the *wrong* concept and 4 were dropped to plain text. Now 100%
> exact by construction.

`ConceptIndex.resolve` (`links.py:123`) matches, in order: exact id → slugified
basename → name/compact/prefix tables → naive singularization. `_by_prefix` maps
a **short href onto a longer concept slug**, not the reverse. Session bullets now
hit its first (exact) branch every time; **prose autolinking in entity bodies
still genuinely needs the name/alias tables** — "Vasul" in German prose has to
reach `deities/vharzul`. Do not delete it.

⚠ **`dropped_links` in `last_run.json` does NOT count session bullets.** It is
`unresolved_total`, incremented only inside the *entity* emit loop
(`cli.py:312`, from `emit_entity`), so it measures unresolved links in
synthesized **body prose**. `emit_sessions` logs its own unresolved links at
`log.debug` and counts them nowhere. Do not read that number as a session-link
metric — an earlier version of this document did, and it was wrong.

### The crash window (closed 2026-09-07)

Until `8159eb2` the order was: registry → **sessions** → synthesis (25–95 min)
→ entities. A kill in the synthesis window left new session files linking to
entity pages that were never written, plus a registry naming concept ids with
no files. **That happened on 2026-09-05 and left 54 dangling links.**

Now nothing is written until synthesis has completed, and each write happens
after what it references: entities → sessions → registry. A kill during
synthesis leaves the previous bundle untouched and self-consistent.

⚠ Moving `emit_sessions` merely past the `ThreadPoolExecutor` join is **not
sufficient** — `emit_entity` writes the link targets in the loop that follows
the join, so sessions would still land first. It must come after that loop.

**Residual risk, stated plainly.** Every write is still a bare
`Path.write_text` (`okf.py:61` `write_if_changed`) — no temp+rename, no
staging, no rollback. A kill *inside* the now-seconds-long write phase
reproduces the same class of breakage, just far less likely. That is the
honest cost of shrinking the window rather than protecting it. The available
upgrade is per-file `os.replace`; note a whole-**directory** atomic swap is
not possible — POSIX `rename(2)` needs an empty destination and Windows
`MoveFileEx` is not atomic for directories. Real "atomic swaps" flip a
symlink, which does not compose with a git working tree.

Detection, since prevention is partial: `_begin_run` (step 0) makes a hard
kill visible to the next run, and `validate_bundle` (step 13) now gates the
exit code.

---

## 8. Tiering — where the money goes

`CanonicalEntity.tier` (`models.py:225`):

| Tier | Condition | LLM |
|---|---|---|
| `deep` | `important:` OR ≥5 mentions OR (Character/Deity AND ≥2) | **pro** |
| `standard` | ≥2 mentions OR Domain/Faction | flash |
| `brief` | everything else | **none** — rendered locally |

Constants: `DEEP_MENTION_THRESHOLD = 5`, `ALWAYS_DEEP_TYPES = {Character, Deity}`,
`ALWAYS_STANDARD_TYPES = {Domain, Faction}`.

Context budgets (`context.py`): `EXCERPT_BUDGET_CHARS = 60_000` (deep only),
`SOURCE_BUDGET_CHARS = 20_000`, `MAX_SECONDARY_SECTIONS = 6`.

> **These constants are the cost dial, more than the model name is.** Deep-tier
> population × 60 KB of excerpts × $1.98/MTok output is the bill. Measure the
> deep/standard/brief split before reaching for a cheaper model.

Routing: `for_tier` (`config.py`). Extraction routes through
`for_tier("extract")`, overridable with `DEEPSEEK_EXTRACT_MODEL`; the default
is unchanged (`DEEPSEEK_MODEL`, i.e. pro). Changing it resamples every entity
name, so it is a **budgeted event**, not a config tweak — see §6 and ADR-004.

---

## 9. Validation — two different bars

`validate_bundle` (`validate.py`) returns a `ValidationReport` with two properties:

| Property | Includes | Used for |
|---|---|---|
| `ok` | everything, incl. fuzzy heuristics | `pnp validate` exit code |
| `integrity_ok` | broken_links, **dangling_links**, missing_type, duplicate_ids | **gates `pnp run`** (exit 3) |

They differ on purpose. A *healthy* bundle today reports 1 duplicate title,
4 cross-type slugs and 10 suspected person dups — heuristics a human triages.
Gating a run on `ok` would fail every run, and a gate that always fails gets
switched off.

- `broken_links` — the href does not resolve *via the fuzzy index*.
- `dangling_links` — the href **names no file on disk**. Strict; catches the case where a link resolves to a *different* existing concept than it names. Currently 0 across 6382 links, committed as a hard-0 invariant.

---

## 10. Tests and ratchets

254 tests. Bundle-dependent ones are guarded by
`skipif(not REGISTRY.exists())`; `conftest.py` turns that skip into a hard error
when `PNP_REQUIRE_BUNDLE=1` (set in CI), so the suite cannot pass by vanishing.

**Ratchet convention** (the repo's own policy, `test_canon_decisions.py:48`):
a hard `0` invariant may never be moved; a movable baseline may only tighten,
and every move must record *why* in a comment. `test_link_coverage.py:44-83`
is the model — it narrates 1871→1816→1889→1912 including a deliberate raise.

Key files: `test_bundle_invariants.py`, `test_link_coverage.py`,
`test_canon_decisions.py`, `test_rules_applied.py`, `test_spelling_sweep.py`,
`test_identity_churn.py` (churn baseline 35 — see its header for why that
number is *pending rule work*, not LLM churn).

**Nothing yet measures whether the extraction is *correct*** — every other test
measures the shape of the emitted corpus. The harness exists
(`tests/test_extraction_quality.py`, precision/recall) but **skips until
`tests/data/gold/` holds hand-labelled sessions**, and it says so in its skip
reason rather than passing silently. Produce a label file with:

```bash
python make_gold_stub.py 2025-03-26 > tests/data/gold/2025-03-26.yaml
```

then correct the draft by hand (`wrong` / `rename` / `missed`). 3-5 sessions
clears the ~30-example floor; ~100 labels still carries about ±8pp of noise, so
the result is directional, not an SLA.

This is also the gate for any cheaper extraction model: small models do not
omit entity names, they **invent** them, so "can extraction move to flash" is a
precision question and unanswerable without these labels.

---

## 11. Traps that have actually bitten

1. **`ModuleNotFoundError: pnp_okf`** — you used the repo-root `.venv`. Use `services/kb/.venv`.
2. **Bash heredocs here silently eat backslashes.** `cat <<'EOF'` with `\n` inside Python source produces a literal newline and a syntax error. Use the Write/Edit tools for anything containing escapes.
3. **`report.ok` is False on a healthy bundle.** Never gate a run on it (§9).
4. **Reading rules from the registry only** misses everything in `entity_rules.yaml` (§5).
5. **A partial run (`--limit`/`--session`) disables the rename guard.** Do not use it to "test" a rename.
6. **`--clean` deletes the whole bundle at step 6**, before synthesis. A crash then loses everything not in git.
7. **Never make a backup copy of `.env`** — it contains the API key and `.env.*` is gitignored precisely so copies cannot be committed.
8. **The frozen `graph/` pipeline is a different system.** Its `test_golden.py` is known-red and it is excluded from CI. Read `graph/CLAUDE.md` before touching it.
9. **A failed run's completed calls are not lost** — extraction and synthesis cache per item on success, so a retry reuses them. Do not report a failed run's tokens as "burned".

---

## 12. Commands

```bash
cd services/kb

.venv/Scripts/python.exe -m pytest -q                    # full suite
PNP_REQUIRE_BUNDLE=1 .venv/Scripts/python.exe -m pytest  # CI mode: no silent skips

.venv/Scripts/python.exe -m pnp_okf.cli check            # config + transcript count, no LLM
.venv/Scripts/python.exe -m pnp_okf.cli run --estimate \
    --transcripts ../../../pnp-crawl/transcripts_final \
    --bundle ../../knowledge/bundle/splitter_des_ewigen   # the bill, before you pay it
.venv/Scripts/python.exe -m pnp_okf.cli validate --bundle ../../knowledge/bundle/splitter_des_ewigen
.venv/Scripts/python.exe rules_doctor.py                 # dead rules
.venv/Scripts/python.exe spelling_doctor.py              # name-drift sweep

# COSTS MONEY -- only with a budget and a reason:
.venv/Scripts/python.exe -m pnp_okf.cli run --transcripts ../../../pnp-crawl/transcripts_final \
    --bundle ../../knowledge/bundle/splitter_des_ewigen
```

Exit codes for `run`: `0` ok · `2` rename guard refused · `3` failed post-emit
validation.

**Rollback:** `git checkout <ref> -- knowledge/` restores the bundle. The caches
are unaffected, so the next run will want the same rename again — rollback buys
time, it does not close the gap.

---

## 13. Before you change anything

| If you are about to… | Read first |
|---|---|
| touch naming, merging, splitting | §4, §5 |
| bump `PROMPT_VERSION` or change a prompt | §6 — this is a **budgeted event**, ~$6.5 |
| change the model | §6 — same cost as a prompt bump |
| reorder or add an emit step | §7 |
| add a quality check | §9, §10 — and decide hard-0 vs ratchet *by measuring* |
| make anything cheaper | §8 first, §6 second. The model name is rarely the answer |
