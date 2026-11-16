# E1 — One-case extraction golden benchmark

## Intent

Pick the model/effort/prompt configuration for the next full Season 1
extraction. Score each configuration against **one human-approved gold
reference** for session `2026-10-28_Team-A_4eyaH3z_QC8`. Quality and
API-equivalent cost are reported separately.

Constraints:

- Extraction and grading run only on Codex or Claude Code subscriptions. The
  Python harness is offline: it never launches a model and imports no provider SDK.
- The gold reference is approved once by a human, bound by hash to gold +
  rubric + source. An agent can never mark it approved.
- Cost = recorded usage × documented prices. Missing usage is `None`
  ("unknown"), never 0.
- Graders run blind, fresh context, one anonymous output each. Python does all arithmetic.
- Do not touch `graph/`, `knowledge/`, `prompts.py`, prompt-version constants, or `.claude/hooks/`.
- This repo is **public**. Campaign data (transcripts, gold, outputs) lives only
  under the gitignored `services/kb/.cache/extraction-benchmark/`
  (override: `PNP_BENCH_DIR`). Tests use invented data only.
- No model run without an explicit human trigger. Procedure: `docs/EXTRACTION-BENCHMARK.md`.

Human decisions already taken (2026-11-15): gold = one drafter + cross-family
gap pass; grader disagreements = one blind evidence exchange, then the human;
new-run matrix = Terra medium, Terra high, Sol high, Luna max, Sonnet 5.5
medium, Opus 5.5 high; Claude judge and inventory agent = Opus 5.5; all seven
existing outputs may serve as calibration material; no guard rule for
`approve-gold` (the TTY check below is the tripwire).

## Steps

Two files: `services/kb/extraction_benchmark.py` (one module, argparse CLI,
stdlib + pydantic + `pnp_okf`) and `services/kb/tests/test_extraction_benchmark.py`.
Write tests first. Everything below is the contract; names are exact.

### 0. Conventions

- All JSON read/written as UTF-8, `ensure_ascii=False`.
- `class BenchError(Exception)`: every refusal raises it; `main()` prints it to stderr and returns 2.
- `bench_root() -> Path`: `$PNP_BENCH_DIR` if set, else `<dir of this file>/.cache/extraction-benchmark`.
- Module-level imports: stdlib and `pydantic` only. Import `pnp_okf.*` **inside**
  the functions that need it (those modules import `openai`). Never import
  `openai`, `httpx`, `requests`, `anthropic`, `socket`, `urllib` in this module.
- `Segment` here = `dict` with `start`, `end`, `speaker`, `text`. Segment id = `f"S{index:03d}"`.

### 1. Hashing and files

```python
def canon(obj) -> bytes            # json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
def sha(data: bytes) -> str        # sha256 hex
def hash_obj(obj) -> str           # sha(canon(obj))
def read_json(path: Path)          # json.loads(path.read_text("utf-8"))
def write_once(path: Path, data: bytes) -> bool
```

`write_once`: creates parents. File absent → write with mode `"xb"`, return
True. File present with identical bytes → return False. Present with different
bytes → `BenchError("refusing to overwrite <path>")`.

`write_json(path, obj)` (mutable files only: reports, disagreement lists,
samples): `json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)`.

### 2. Case preparation

```python
def load_segments(source_json: Path) -> list[dict]     # data["segments"]
def render_dialogue(segments) -> str                    # "\n".join(f"[{HH:MM:SS}] {speaker}: {text.strip()}") for segments with non-empty text; time = int(round(start))
def segment_at(segments, seconds: float) -> int         # index of last segment with start <= seconds, else 0
def build_prompt(request: dict) -> str
def prepare(experiment: Path, transcript: Path, case_dir: Path) -> dict
```

`build_prompt`: exactly

```text
Answer the request below exactly as the model it addresses would. Reply with the JSON object only.
Use no tools and no other source of information.

=== SYSTEM ===
<request["messages"][0]["content"]>

=== USER ===
<request["messages"][1]["content"]>
```

`prepare`: reads `<experiment>/manifest.json` (keys `session_id`,
`transcript_sha256`, `request_sha256`, `schema_sha256`). Verifies the raw-byte
sha256 of `transcript`, `<experiment>/request.json`, `<experiment>/schema.json`
against it; verifies `render_dialogue(segments)` is a substring of the request's
user message. Any mismatch → `BenchError`, **nothing written**. Then `write_once`
byte copies into `case_dir`: `source.json`, `baseline_request.json`,
`schema.json`; plus `dialogue.txt`, `prompt.txt`, and `case_manifest.json` =
`{session_id, source_sha256, request_sha256, schema_sha256, prompt_sha256, segments: <count>}`.
Writes `<case_dir>/../../rubrics/v1.json` = `DEFAULT_RUBRIC` if absent. Returns the manifest.

```python
DEFAULT_RUBRIC = {"version": 1,
  "weights": {"F": 0.35, "C": 0.20, "N": 0.20, "E": 0.15, "G": 0.10},
  "tolerance": 2.0, "g_window_segments": 2,
  "calibration": {"overall": 0.90, "F": 0.85, "critical_misses": 0}}
```

### 3. Gold

Gold JSON (pydantic models `Gold`, `GoldEntity`, `GoldFact`, `NoteReq`, `CriticalRule`, `Question`, all `extra="forbid"`):

```text
Gold:         version:int, entities:[GoldEntity], facts:[GoldFact], notes:[NoteReq],
              critical:[CriticalRule], questions:[Question], excluded:[{segments:[str], reason:str}]
GoldEntity:   id, label, aliases:[str], required:bool,
              accepted:[{type:str, subtypes:[str] | null}], evidence:[segment id]
GoldFact:     id, statement, scene:str, subjects:[entity id], evidence:[{segment, quote}],
              qualifiers:str="", weight:int, placement:"any"|"recap"|"notes"="any"
NoteReq:      id, fact:<fact id>, entity:<entity id>, weight:int
CriticalRule: id, description, trigger, evidence:[segment id], rationale
Question:     id, text, segments:[segment id], items:[str]
```

`validate_gold(gold: dict, segments) -> list[str]` (empty = valid). Errors for:
schema failure; duplicate ids within a kind; unknown segment id anywhere;
`quote` not a verbatim substring of its segment's text; weight not in `{1, 3}`;
fact subject or note entity/fact that does not exist; `accepted` empty or a type
outside `pnp_okf.models.EntityType` values; critical rule with empty `trigger`;
no required entity; no fact.

`review_pack(gold, rubric, segments, hashes: dict) -> str` (Markdown). Order:
title; line `Approval hash: <hashes["approval"]>` plus gold/rubric/source
hashes; `## Offene Fragen` (questions, with segment text); `## Fakten` grouped by
`scene` in first-appearance order, each `- [F-id] (w=3, any) statement — "quote" (S012 00:10:04)`;
`## Notiz-Anforderungen`; `## Entitäten`; `## Kritische Regeln`;
`## Ausgeschlossen`; `## Bewertung` (weights, tolerance, g window, calibration bar).

### 4. Approval

```python
def approval_hash(gold_hash, rubric_hash, source_hash) -> str   # sha((gold_hash + rubric_hash + source_hash).encode())
def approve_gold(case_dir, rubric_path, typed_hash, reviewer, approval_ref, *, isatty, environ, confirm) -> Path
def check_approval(case_dir, rubric_path) -> tuple[dict | None, str]
```

`approve_gold`: refuses (`BenchError`, nothing written) when `isatty()` is
False; when `environ` has `CLAUDECODE` or any key starting with `CODEX_`; when
`validate_gold` reports errors on `gold/draft.json`; when `typed_hash` is
shorter than 12 chars or is not a prefix of the computed approval hash; when
`confirm()` (the CLI passes a function that prompts the human to retype the
first 12 chars) does not return those 12 chars. Otherwise `write_once`
`gold/v<version>.json` (the draft's canonical bytes) and
`gold/v<version>.approval.json` =
`{approval_hash, gold_hash, rubric_hash, source_sha256, reviewer, approval_ref, date}`; returns the approval path.

`check_approval`: finds the highest `gold/v*.approval.json`; recomputes
`hash_obj(gold)`, `hash_obj(rubric)` and the source hash from `case_manifest.json`.
Returns `(gold, "")` when all match, else `(None, "<reason>")`: `"no approval"`,
`"gold changed since approval"`, `"rubric changed since approval"`.

### 5. Output validation, attempts, repair

```python
def validate_output(raw: str, segments) -> dict
    # {"valid": bool, "errors": [str], "extraction": dict | None}
```

Uses `pnp_okf.agent_status._check("extract", raw)` (any exception → error),
then `SessionExtraction.model_validate_json(pnp_okf.extract._extract_json_block(raw))`.
Extra errors: empty recap; zero entities; `subtype` non-empty and not in
`pnp_okf.models.SUBTYPES[type]` (or type has no list); `citation_ts` where
`pnp_okf.context._parse_ts` returns None or the value is `< 0` or `> segments[-1]["end"]`.
`extraction` = `model_dump(mode="json")` when it parsed at all.

```python
def repair_similarity(raw: str, repaired: dict) -> float
    # difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() where a, b = only str.isalnum() chars of
    # raw and of json.dumps(repaired, ensure_ascii=False)
REPAIR_MIN = 0.98
def attempt_id(case_hash, prompt_hash, schema_hash, host, model, effort, repeat) -> str   # hash_obj of those 7, first 12 hex
def prepare_run(run_dir, case_dir, matrix: dict) -> list[Path]
def import_output(run_dir, case_dir, file: Path, label, provenance: Path | None) -> Path
def attempt_state(attempt_dir, segments) -> dict
```

`matrix` = `{"arms": [{"label", "host", "model", "effort", "repeats": int}]}`.
`prepare_run` creates `runs/<run>/attempts/<label>-r<repeat>-<attempt_id>/attempt.json`
(`write_once`) = `{label, host, model, effort, repeat, kind: "new", attempt_id, case/prompt/schema hashes}`.
`case_hash` = the `case_manifest.json` `source_sha256`. Repeat indexes run from
the arm's optional `"first_repeat"` (default 1) for `repeats` items, so finalist
repeats are a second matrix with `"first_repeat": 2, "repeats": 2`.

`import_output`: attempt dir `<label>-retro-<first 12 of sha(file bytes)>`,
`attempt.json` with `kind: "retrospective"`, `raw.txt` = the file bytes,
`execution.json` = provenance bytes if given.

Worker-written files in an attempt dir: `raw.txt` (first complete response),
`usage.json`, `execution.json`, optionally `repair.raw.txt`, `repair.usage.json`.

`attempt_state` (derived every time, never stored) → `{"state", "errors", "extraction", "similarity"}`:

| state | condition |
|---|---|
| `pending` | no `raw.txt` |
| `valid` | `raw.txt` validates |
| `repaired` | `raw.txt` invalid, `repair.raw.txt` validates and `repair_similarity(raw, repaired) >= REPAIR_MIN` |
| `failed` | anything else (including a repair below the threshold) |

`validate_run(run_dir, case_dir) -> dict[attempt name, state dict]`; for `valid`
and `repaired` attempts it `write_once`s `extraction.json` = `canon(extraction)`.

### 6. Grading packets

```python
def prepare_grading(run_dir, case_dir, *, salt: str | None = None) -> dict[str, str]   # attempt name -> anon id
```

Reads or creates `runs/<run>/private/identity_map.json` =
`{"salt": <secrets.token_hex(16) unless given>, "map": {attempt name: anon id}}`.
`anon id = sha((salt + sha(extraction.json bytes)).encode())[:8]`. For every
attempt with `extraction.json`: `write_once` `runs/<run>/grading/<anon>/output.json`
(same bytes). Nothing else goes into `grading/<anon>/` from this function: no
label, model, effort, host, cost or attempt name.

Judge-written files in `grading/<anon>/` (judge ids: any `[a-z0-9]+`, e.g. `claude`, `codex`):

```text
inventory.json        {"output_sha256", "config": {...}, "claims": [{"id", "loc", "span", "group", "kind"}]}
                      loc = "recap" | "entity:<index>"; kind = "claim" | "not_claim"
A.<judge>.json        {"binds": {...}, "judge": {"host","model","effort","prompt_sha256"},
                       "claims":   {claim id:     {"verdict", "segments": [...], "why"}},
                       "locators": {entity index: {"verdict", "segments": [...], "why"}}}
B.<judge>.json        {"binds": {...}, "judge": {...},
                       "facts":    {fact id: {"verdict", "spans": [...], "why"}},
                       "notes":    {req id:  {"verdict", "entity_index": int | null, "why"}},
                       "entities": {entity index: {"match", "type_ok": bool, "subtype_ok": bool, "segments": [...]}},
                       "critical": {rule id: {"verdict", "spans": [...], "why"}}}
A.<judge>.x.json, B.<judge>.x.json   same shape, only the items revised in the evidence exchange
adjudication.json     {"<kind>:<id>": {"verdict" (or "match","type_ok","subtype_ok" for E), "by": "human", "ref"}}
usage.<anything>.json grading usage records (same shape as attempt usage.json)
```

Verdict vocabularies (anything else → `BenchError` when read):

```python
V_CLAIM = ("supported", "contradicted", "unsupported", "unresolved")
V_LOC   = ("supported", "not_supported", "unresolved")
V_FACT  = ("present", "partial", "absent", "conflicting", "unresolved")
V_NOTE  = ("present", "absent", "wrong_entity", "unresolved")
V_CRIT  = ("violated", "not_violated", "unresolved")
# entity match: "gold:<id>" | "extra_supported" | "duplicate_of:<index>" | "unsupported" | "unresolved"
```

Item keys: `F:<claim id>`, `G:<entity index>`, `C:<fact id>`, `N:<req id>`, `E:<entity index>`, `K:<rule id>`.

`binds`: packet A = `{output_sha256, inventory_sha256, source_sha256, rubric_sha256}`;
packet B = `{output_sha256, source_sha256, rubric_sha256, gold_sha256}`
(`inventory_sha256` = `sha(inventory.json bytes)`, gold/rubric = `hash_obj`).
`judge_hash(judge: dict) -> str` = `hash_obj(judge)[:12]`.

```python
def sentences(text: str) -> list[str]
def validate_inventory(inv: dict, extraction: dict) -> list[str]
```

`sentences`: per non-empty line, split with `pnp_okf.claims._BOUNDARY` after
protecting `pnp_okf.claims._ABBREV` dots (same trick as `claims.split_claims`),
strip, drop empties. **No minimum word count**, no markdown stripping.

`validate_inventory` errors: `output_sha256` ≠ `hash of canon(extraction)`;
unknown `loc`; `span` not a verbatim substring of that loc's text (recap, or
`entities[i]["note"]`); duplicate claim id; a sentence of any recap/note text
with no span of the same loc where `span in sentence or sentence in span`
(compare stripped); no claim of kind `claim` at all.

### 7. Resolution and disagreements

```python
def load_judgments(grading_dir, packet: "A" | "B") -> dict[judge id, dict]
    # base file with the .x file's items overlaid per section; validates vocabularies
def stale_reasons(packet, judgment, expected_binds) -> list[str]   # one entry per differing binds key
def resolve(key, verdicts: dict[judge id, value], adjudication: dict) -> tuple[value | None, str]
```

`resolve` → `(value, how)`: adjudication has the key → `(its value, "adjudicated")`;
fewer than 2 judges have the item → `(None, "missing")`; all judges equal and
not `unresolved` → `(value, "agreed")`; otherwise `(None, "disputed")`. For `E:`
items the value is the tuple `(match, type_ok, subtype_ok)`. Opposite verdicts
are never averaged.

`diff_judgments(run_dir, case_dir) -> dict` writes (mutable)
`runs/<run>/disagreements.json` = list of
`{anon, key, how, verdicts: {judge: value}, evidence: {judge: {segments|spans, why}}}`
for every `disputed` or `missing` item, and per judge
`runs/<run>/exchange/<anon>.<packet>.<judge>.json` = that judge's disputed
items with **only the other judge's** `segments`/`spans` and `why` (no verdict field).

### 8. Scoring

```python
def score_output(extraction, gold, rubric, inventory, judg_a, judg_b, adjudication) -> dict
```

`judg_a`, `judg_b` are `load_judgments` results. Every item below is first put
through `resolve`. A `None` result is "open": counted in `open_items` and it
makes bounds. Returned dict:

```text
{"F": comp, "C": comp, "N": comp, "E": comp, "G": comp, "Q": comp,
 "counts": {"contradicted", "unsupported", "claim_groups", "entities"},
 "critical": [rule ids resolved "violated"], "open_items": [keys], "ledger": [{"key", "problem"}]}
comp = {"value": float | None, "low": float, "high": float}   # value is None exactly when low != high
```

- **F.** Claims of kind `claim`, grouped by `group`. Group verdict = the single
  resolved verdict shared by all members; members disagree or any is open →
  group open (ledger `mixed_group` when resolved verdicts differ).
  `F = 100 × supported groups / all groups`. Open groups count 0 in `low`, 1 in `high`.
- **C.** `100 × Σweight(resolved == "present") / Σweight(all gold facts)`. Open → bounds.
- **E.** Walk emitted entities in index order with resolved `(match, type_ok, subtype_ok)`:
  `gold:<id>` first time → supported identity (required or optional per gold);
  same gold id again → duplicate; `extra_supported` → supported extra;
  `duplicate_of:*`, `unsupported` → false positive.
  `precision = supported identities / emitted`; `recall = matched required / required`;
  `identity = 2PR/(P+R)` or 0; `classification = supported identities with type_ok and subtype_ok / (required + matched optional + extras)` (0 when the denominator is 0);
  `E = 100 × (2/3 × identity + 1/3 × classification)`.
  Open E items: `low` treats them as `unsupported`, `high` as `extra_supported` with both flags true.
- **N.** For each note requirement: target record indexes = entities whose
  resolved match is `gold:<target>` plus entities `duplicate_of` one of those.
  Credit only when the resolved verdict is `present` **and** `entity_index` is a
  target index. `present` with a non-target index, or `wrong_entity` → no credit,
  ledger `wrong_entity`. No target record → 0 without needing a verdict.
  `N = 100 × Σweight(credited) / Σweight(all requirements)`; no requirements → 100. Open → bounds.
- **G.** `100 × resolved "supported" / emitted entities`. Open → bounds.
- **Q.** `Σ rubric weight × component`, for `low` and `high` separately; `value` only when every component has a value.
- **critical.** Rule resolved `violated`. A rule that is open goes to `open_items`.

No rounding anywhere in `score_output`.

### 9. Cost

```python
def normalise_usage(style: str, raw: dict) -> dict
    # {"input_total", "cache_read", "cache_write", "output_total", "reasoning"}; each int or None
def cost(turns: list[dict], price: dict | None) -> dict
    # {"standard": float | None, "observed": float | None, "unknown": [reasons]}
def attempt_cost(attempt_dir, prices: dict) -> dict
```

- `style == "openai"` (also DeepSeek, Codex): input = `prompt_tokens` or
  `input_tokens`; cached = first present of `prompt_tokens_details.cached_tokens`,
  `input_tokens_details.cached_tokens`, `cached_input_tokens`, `prompt_cache_hit_tokens`;
  output = `completion_tokens` or `output_tokens`. Cached is a **subset** of
  input: `input_total = input`, `cache_read = cached`, `cache_write = 0`.
  Reasoning (informational, already inside output) from
  `completion_tokens_details.reasoning_tokens`, `output_tokens_details.reasoning_tokens` or `reasoning_output_tokens`.
- `style == "anthropic"`: `input_tokens` **excludes** cache tokens:
  `cache_read = cache_read_input_tokens`, `cache_write = cache_creation_input_tokens`,
  `input_total = input_tokens + cache_read + cache_write` (None if any of the three is missing);
  `output_total = output_tokens`.
- Unknown style → `BenchError`. A missing source field → that normalised field is `None`.
- Price row: `{"model", "currency", "input", "cache_read", "cache_write", "output", "source_url", "retrieved", "tier", "max_input_tokens": int | null}`, prices per million tokens.
- Per turn: `standard = (input_total × input + output_total × output) / 1e6`;
  `observed = ((input_total − cache_read − cache_write) × input + cache_read × price.cache_read + cache_write × price.cache_write + output_total × output) / 1e6`.
  Sum over turns. Any `None` needed for a figure, no price row, no turns, or
  `input_total > max_input_tokens` → that figure is `None` and a reason is
  appended. Never 0 for unknown.
- Usage file = `{"style", "model", "turns": [raw usage dict, ...], "provenance"}`.
  `attempt_cost` sums `usage.json` + `repair.usage.json` (a `repair.raw.txt`
  without `repair.usage.json` → unknown); price row looked up by `model` in
  `prices` (`{"rows": [price row, ...]}`).

### 10. Calibration

```python
def calibration_sample(run_dir, case_dir, seed: int, n: int = 60, holdout: int = 20) -> list[dict]
def calibrate(run_dir, case_dir, labels: dict[str, str], rubric) -> dict
```

`calibration_sample`: all item keys of all graded outputs as `<anon>|<key>`,
sorted; `random.Random(seed)`; every `K:` item is always included; the other
kinds are sampled evenly up to `n`; `holdout` of them get `"set": "holdout"`,
the rest `"tune"`. Each row: `{item, kind, set, text}` (the claim span, fact
statement, entity name + note, locator, or rule description) and **no judge
verdict**. Written to `runs/<run>/calibration/sample.json` with `write_once`.

`calibrate`: `labels` = `{item: human verdict}` (for `E:` the match string
only). Per judge (original verdict, **before** `.x` overlays): agreement
overall, per kind, separately for `tune` and `holdout`; `critical_misses` =
`K:` items where the judge differs from the human. `pass` = both sets reach
`rubric["calibration"]["overall"]`, both reach the `F` bar on `F:` items, and
`critical_misses <= rubric["calibration"]["critical_misses"]`. Result per judge
written (mutable) to `runs/<run>/calibration/<judge_hash>.json` with `misses: [items]`.
`calibrated_judges(root) -> set[judge_hash]` = every `runs/*/calibration/*.json` with `pass: true`.

### 11. Report and selection

```python
def score_run(run_dir, case_dir, prices: dict | None, baseline: str | None = None) -> dict
def select(configs: list[dict], tolerance: float) -> dict
def render_report(report: dict) -> str
```

`score_run` builds `report.json` (mutable) and `report.md`:

- per attempt: `{attempt, label, kind, state, status, reasons, scores | None, per_judge_Q, cost, grading_cost}`.
  `status`: `invalid` when state is `failed`/`pending` or there are zero claim
  groups; else `provisional` with `reasons` when: approval missing/stale, a
  judge of this output not in `calibrated_judges`, stale binds, fewer than 2
  judges, any open item; else `official`. `critical` is a separate boolean list, it does not change Q.
  `per_judge_Q`: `score_output` run with only that judge's verdicts duplicated as both judges.
- per configuration (label): `{label, n_attempts, n_valid, q_values, q_mean, q_min, q_max, eligible, why_not, cost_standard, cost_observed, cost_per_valid, retrospective}`.
  `eligible` = every attempt `official`, none `critical`, none `failed`, not retrospective.
  `cost_standard`/`cost_observed` = mean over valid attempts, `None` if any is unknown.
  `cost_per_valid` = sum of `standard` over all attempts ÷ `n_valid`, `None` if any unknown.
- `delta_to_baseline` per configuration when `baseline` label is given.
- `limits`: the fixed list of limits from `docs/EXTRACTION-BENCHMARK.md`, verbatim in every report.
- grading usage is summed separately (`grading_cost`), never added to extraction cost.

`select(configs, tolerance)` → `{"best_quality", "best_value", "within_tolerance": [labels], "provisional": [reasons]}`:

1. Only `eligible` configs. None → both winners `None`, reason `"no eligible configuration"`.
2. `best_quality` = highest `q_mean`; ties listed in `provisional` as `"tie: a, b"`.
3. `within_tolerance` = eligible with `q_mean >= best − tolerance` (2.0 below is in, 2.01 is out).
4. Any of them with `cost_standard is None` → `best_value = None`, reason `"cost unknown: <labels>"`. Else the cheapest `cost_standard`.
5. Rank flip: a config **outside** tolerance whose `q_max >= best's q_min` → reason `"rank flip: <label>"`, `best_value = None`.
6. No points-per-dollar figure anywhere.

`render_report`: Markdown from `report.json` only (so a stored report re-renders
identically). Numbers formatted with one decimal **only here**; bounds as
`71.2–74.0 (open)`; unknown cost as `unknown`.

`status(root) -> str`: per case approval state; per run counts of attempts by
state, outputs with inventory, judgments per judge, stale judgments, open items.

### 12. CLI

`main(argv=None) -> int`, subcommands, all taking `--root` (default `bench_root()`)
and `--case` (default `2026-10-28_Team-A_4eyaH3z_QC8`):

```text
prepare --experiment DIR --transcript FILE
validate-gold | review-pack
approve-gold --hash HEX --reviewer NAME --approval-ref TEXT
import-output --run ID --file FILE --label LABEL [--provenance FILE]
prepare-run --run ID --matrix FILE
validate-run --run ID
prepare-grading --run ID
diff-judgments --run ID
calibration-sample --run ID --seed N
calibrate --run ID --labels FILE          # JSON {item: verdict}
score --run ID [--prices FILE] [--baseline LABEL]
status
```

`approve-gold` passes `sys.stdin.isatty`, `os.environ` and an `input()`-based confirm.

### 13. Tests (`tests/test_extraction_benchmark.py`)

Invented data only: a 6-segment transcript about "Alrik", "Brunhild" and the
"Mühle von Tannbach", a matching extraction, gold, inventory and judgments
built by small helper functions in the test file. `tmp_path` for every file.
One test function (or more) per numbered group; name them `test_<nn>_…`:

1. source hash mismatch → `BenchError`, case dir empty; stale approval after a gold edit; changed rubric.
2. `approve_gold` refused with `isatty=lambda: False`, with `CLAUDECODE` set, with `CODEX_HOME` set, with a wrong hash, with a wrong confirm; no approval file in each case. Happy path writes both files.
3. perfect extraction + all-agree judgments → F, C, N, E, G, Q all `100.0`; empty text, zero entities, schema-invalid JSON → `valid: False`; zero claim groups → status `invalid`.
4. fact only in recap → C credit, N none; `present` with a non-target `entity_index` → no N + ledger; target entity not emitted → N 0.
5. two claims in one group count once in F; a supported claim and a contradicted claim in different groups → F 50; one group with mixed verdicts → open + ledger.
6. E, one assertion each: required entity missing (recall), alias match counts, optional match, extra supported, duplicate record, `type_ok` false, `subtype_ok` false, unsupported record. Assert exact fractions.
7. locator `not_supported` lowers G; `citation_ts` `"99:00:00"` and `"abc"` → invalid output.
8. critical rule violated → `critical` non-empty, config not eligible, Q unchanged versus the same data without the violation.
9. judges disagree → `value is None`, `low < high`, status `provisional`; only one judge → `missing` → provisional; `select` with no eligible config → no winner.
10. inventory with a non-verbatim span → error; with an uncovered sentence → error; a 2-word sentence still needs coverage.
11. cost: openai style with cached subset (standard uses full input once, observed splits); anthropic style adds cache tokens to input; reasoning never added to output; repair turn included; missing usage → `None` not 0; no price row → `None`; grading usage not in extraction cost.
12. `attempt_id` differs when effort, repeat, prompt hash or model changes; `write_once` raises on different bytes and returns False on identical; `stale_reasons` non-empty when gold hash or inventory hash changes.
13. after `prepare_grading`, no file under `grading/` contains any attempt label, model, effort or host string; `identity_map.json` is outside `grading/`.
14. repair with rewritten prose → state `failed`; whitespace/fence-only repair → `repaired`.
15. `select`: 2.0 below best is within tolerance, 2.01 is not; unknown cost → `best_value is None`; rank flip → reason present.
16. `render_report(json.loads(json.dumps(report)))` equals `render_report(report)`; `score_output` values are unrounded floats.
17. AST of `extraction_benchmark.py`: no module-level import of `openai`, `httpx`, `requests`, `anthropic`, `socket`, `urllib`, `pnp_okf`; and a full prepare → score run passes with `socket.socket` monkeypatched to raise.

### 14. Docs

`docs/EXTRACTION-BENCHMARK.md`: procedure, human gates, task templates,
launch rules, limits. `docs/plans/README.md`: E1 row.

**HUMAN RUN** (never by an agent without a trigger): telemetry probe, gold
drafting + gap pass, gold approval (own terminal), grading, calibration
labelling, generation runs, finalist repeats, final selection.

## Done when

- [ ] All 17 test groups exist and pass.
- [ ] Lint clean.
- [ ] CLI help lists every subcommand.
- [ ] Diff touches only the harness, its test, `docs/EXTRACTION-BENCHMARK.md`, this plan and the plans README.
- [ ] Full kb suite unchanged apart from the known red test.
- [ ] Human-gated: gold v1 approved; judges calibrated; seven existing outputs scored; six arms screened; finalists repeated; selection recorded. (UNVERIFIED by design until the human runs them.)

```powershell
cd services/kb
& .venv/Scripts/python.exe -m pytest tests/test_extraction_benchmark.py -q
& .venv/Scripts/python.exe extraction_benchmark.py --help
& .venv/Scripts/python.exe -m pytest -q
ruff check ..\..
git diff --stat origin/main
```
