# Extraction benchmark (E1): how to run it

Status: the offline harness is built and tested. No model has been run for this benchmark yet.
Owner: the human. A coordinating agent may run the offline steps and the
task templates after the gate that unlocks them.

## 1. What this is

- One session is scored: `2026-10-28_Team-A_4eyaH3z_QC8`. The benchmark tests extraction on this one case only.
- Quality is measured against one **gold** reference. Gold is the answer key: the facts, entities and rules a correct extraction should contain. A human approves gold once, by hash.
- Quality (**Q**, 0 to 100) and cost (**API-equivalent dollars**) are reported separately. They are never combined into one number.
- Every model call runs on a Claude Code or Codex subscription. No API key is used. The Python harness is offline: it never launches a model and imports no provider SDK.
- Python does all counting and arithmetic. Model workers only write the judgment files that Python then reads.

## 2. Where things live

| What | Path |
|---|---|
| Harness (one module, argparse CLI) | `services/kb/extraction_benchmark.py` |
| Tests (invented data only) | `services/kb/tests/test_extraction_benchmark.py` |
| This procedure | `docs/EXTRACTION-BENCHMARK.md` |
| Plan and decisions | `docs/plans/E1-extraction-golden-benchmark.md` |
| Private data root | `services/kb/.cache/extraction-benchmark/`, or the folder in `PNP_BENCH_DIR` if that is set |

**Worktree rule.** A git worktree has no `.cache` folder. In a worktree shell, set `PNP_BENCH_DIR` to the main checkout's folder:

```powershell
$env:PNP_BENCH_DIR = "C:\dev\lindo-lauts-notebook\pnp-knowledge\services\kb\.cache\extraction-benchmark"
```

**Public repo, private data.** This repo is public. The data folder is gitignored, so git does not back it up. The human keeps a private copy outside the repo. Make that copy before Gate 1. The harness never copies data into `knowledge/`.

Layout under the private root (`<root>`). The case folder is `cases/<case>/`.

```text
<root>/
  cases/<case>/
    source.json, baseline_request.json, schema.json   byte copies from the experiment folder
    dialogue.txt                  transcript rendered as "[HH:MM:SS] speaker: text" lines
    prompt.txt                    the one prompt every arm receives
    case_manifest.json            hashes and segment count
    gold/
      draft.json                  the gold draft (JSON)
      gap_objections.json         output of the gap pass
      v<N>.json                   approved gold, canonical bytes
      v<N>.approval.json          approval record
      review.md                   review pack for the human
  rubrics/v1.json                 rubric (weights, tolerance, calibration bar)
  runs/<run id>/
    attempts/<label>-r<repeat>-<attempt id>/
                                  attempt.json, raw.txt, usage.json, execution.json,
                                  repair.raw.txt, repair.usage.json, extraction.json
    grading/<anon id>/            output.json, inventory.json, A.<judge>.json,
                                  B.<judge>.json, *.x.json, usage.*.json
    private/identity_map.json     maps attempts to anonymous ids (never inside grading/)
    exchange/                     <anon>.<packet>.<judge>.json
    calibration/                  sample.json, <judge hash>.json
    disagreements.json            list of disputed items
    adjudication.json             human decisions (location assumed; see section 11)
    report.json, report.md        written by score
```

Other folders the harness reads or writes, if you pass them: a matrix JSON
for `prepare-run`, a labels JSON for `calibrate`, and a price file for
`score --prices` (one row per exact model; see section 8).

## 3. Gates

An agent never passes a gate. Each gate needs a human action. Do not start the next phase before the gate says so.

| Gate | The human does | What it unlocks |
|---|---|---|
| 0 | Runs the telemetry probe: two "reply OK" runs, one per host. Checks login mode, usage fields and that model and effort can be set. Chooses the drafter and gap-pass models. Writes the exact headless flags into section 5. | Phase 2 (gold drafting). |
| 1 | Reads `gold/review.md`, sends corrections, then approves one hash in their own terminal with `approve-gold`. Fixes the Codex judge model and effort. | Phase 3 (grading of the seven existing outputs). |
| 2 | Labels the calibration sample blind (no judge verdicts in the file). Confirms the calibration bar. | `calibrate`. Judges may score outputs only after they pass. |
| 3 | Triggers the six screening arms. | Phase 4 generation. |
| 4 | Confirms the finalists: the best-Q arm and every eligible arm within 2.0 points. | Two more repeats for each finalist. |
| 5 | Reads the report, decides the selection and records the choice. | Nothing is promoted. No full extraction starts. |

## 4. Step by step

Run every command from `services/kb`:

```powershell
cd services/kb
.venv/Scripts/python.exe extraction_benchmark.py <command> [options]
```

`--root` defaults to `bench_root()` (section 2). `--case` defaults to `2026-10-28_Team-A_4eyaH3z_QC8`.
Commands marked **Python** are offline. Commands marked **agent task** start model workers and follow section 5 and section 6.

### Phase 1: offline harness (Python only, no gate)

1. Check the harness and its tests.
   ```powershell
   .venv/Scripts/python.exe -m pytest tests/test_extraction_benchmark.py -q
   .venv/Scripts/python.exe extraction_benchmark.py --help
   ```
   Who: Python.
2. Build the case from the experiment folder. The command checks three source hashes first. A mismatch exits 2 and writes nothing.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py prepare --experiment <EXPERIMENT_DIR> --transcript <TRANSCRIPT_JSON>
   ```
   Who: Python. It copies files; it never moves them.

### Phase 2: gold (after Gate 0)

1. Drafter: one agent task, transcript only. Output `gold/draft.json`. Template T1.
   Who: agent task (drafter model chosen at Gate 0).
2. Gap pass: one agent task of the other model family, transcript plus draft. Output `gold/gap_objections.json`. It never edits the draft. Template T2.
   Who: agent task.
3. The coordinator copies the draft and objections into `<case>/gold/`.
4. Validate the draft. Every error is listed; fix and repeat.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py validate-gold
   ```
   Who: Python.
5. Write the review pack for the human.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py review-pack
   ```
   Who: Python. Output `gold/review.md`: approval hash first, then open questions, facts, note requirements, entities, critical rules, exclusions and the rubric.
6. Corrections from the human go into a new draft revision. Who: agent task (T1 run again with the corrections as an added input). The contract has no separate template for this.

### Phase 2 gate: Gate 1 (human only)

7. The human reads `review.md` and approves in their own terminal. The command needs a real TTY, and it refuses when agent environment variables are set.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py approve-gold --hash <FIRST 12+ HEX OF APPROVAL HASH> --reviewer <NAME> --approval-ref <TEXT>
   ```
   Who: human only. The command asks the human to type the first 12 characters again.

### Phase 3: grade the seven existing outputs and calibrate (after Gate 1)

The seven existing outputs are: DeepSeek, Terra medium, Terra high, Sol high, Luna max, Opus 5.5 high, Sonnet 5.5 medium.

1. Register each output as a retrospective attempt. Run once per output.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py import-output --run <RUN> --file <EXTRACTION_JSON> --label <LABEL> [--provenance <EXECUTION_JSON>]
   ```
   Who: Python.
2. Check the outputs and create the anonymous grading folders.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py validate-run --run <RUN>
   .venv/Scripts/python.exe extraction_benchmark.py prepare-grading --run <RUN>
   ```
   Who: Python.
3. Per output: one inventory task (T5), then two judges each doing packet A (T6) and packet B (T7). That is 5 fresh tasks per output, 35 in total.
   Who: agent tasks, one fresh process each (section 5).
4. Find disagreements and write the exchange packets.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py diff-judgments --run <RUN>
   ```
   Who: Python.
5. Each judge does one exchange task (T8) on its disputed items. The human decides the items still disputed, in `adjudication.json`. Critical-rule disputes go straight to the human. The human spot-checks about 10% of exchange-resolved items.
   Who: agent task (T8), then human.
6. Draw the calibration sample with a fixed seed.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py calibration-sample --run <RUN> --seed <N>
   ```
   Who: Python. About 60 items: all critical rules, plus a spread over F, C, N, E and G. 20 are a held-out check set.
7. Gate 2: the human labels the sample blind, in a JSON file of `{item: verdict}`. Then:
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py calibrate --run <RUN> --labels <LABELS_JSON>
   ```
   Who: human labels; Python calibrates. A judge fails if it misses the bar (section 7) on either set.
8. Score the outputs. This writes `report.json` and `report.md`.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py score --run <RUN> [--prices <PRICE_JSON>] [--baseline <LABEL>]
   ```
   Who: Python. The seven outputs are marked retrospective.

### Phase 4: generation (after Gate 3)

1. Write a matrix JSON with six arms: Terra medium, Terra high, Sol high, Luna max, Sonnet 5.5 medium, Opus 5.5 high. Each arm has `label`, `host`, `model`, `effort`, `repeats` (1 for the screen). Baseline prompt v6 only. DeepSeek is never rerun.
   Who: coordinator.
2. Create the attempt folders.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py prepare-run --run <RUN> --matrix <MATRIX_JSON>
   ```
   Who: Python.
3. Launch each attempt once, following section 5. Who: agent task launcher (T3 for the prompt).
4. If an output is invalid, run the format repair once (T4). If it still fails, the attempt is failed. Failed attempts stay and their cost counts.
5. Check and grade as in Phase 3, steps 2 to 8, with the calibrated judges.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py validate-run --run <RUN>
   ```
   Who: Python and agent tasks.

### Phase 4 gate: Gate 4 (human only)

6. The human confirms the finalists. Each finalist gets two more independent repeats, each a new process. Reusing an output is not a new sample. (The repeat numbering for this step is not specified; see section 11.)

### Phase 5: report and selection (Gate 5)

7. Read the report and check status.
   ```powershell
   .venv/Scripts/python.exe extraction_benchmark.py status
   ```
   Who: Python to show status; the human reads `report.md`.
8. The human decides and records the choice. Nothing is promoted to the production config and no full extraction starts.

## 5. Launch rules for every model task

Every model task, including judges, the inventory agent, the drafter and
the repair worker, follows these rules.

1. **Fresh process or fresh context per task.** No resumed sessions, no shared chat history, no worker reuses another worker's context.
2. **Model and effort set by the launcher.** The launcher sets both explicitly on every call. Never rely on a default.
3. **No API keys.** `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `DEEPSEEK_API_KEY` must be unset in the launching shell. The launcher checks this and aborts if one is set.
4. **Login mode recorded.** Each attempt's `execution.json` records the login mode (subscription) and the host version.
5. **Generation workers** get `prompt.txt` only. They have no tools. Their working folder is an empty temp folder outside the repo. The launcher captures the first complete answer from stdout into `raw.txt`. Never overwrite `raw.txt`.
6. **No best-of-N.** One attempt is one sample. Do not generate extra samples and pick one.
7. **One format repair at most.** The repair is a new fresh process that gets `raw.txt` and the validator error only (T4).
8. **Record requested and reported values.** Record the requested model and effort, and the model and effort the host reports, in `execution.json`. Record the raw usage record in `usage.json`. Record start and finish times.
9. **Judges and the inventory agent** get file read and write access only to the paths their template names.
10. **Hashing.** Source files are hashed as raw bytes. Gold, rubric and judgment files are hashed as canonical JSON: keys sorted, UTF-8, `ensure_ascii` off, separators `,` and `:`, no whitespace. Hash is SHA-256, hex. Coordinators supply the hash values that a task needs (`binds`, `output_sha256`, `config`) in the task message. Workers copy them; they do not compute them.
11. **Judges never learn** which model, effort, host or cost produced an output.

**Exact headless commands are not fixed in this document.** The exact command-line flags for Claude Code and Codex headless runs are confirmed by the Gate 0 probe. They are then written into this section. Do not invent flags.

| Host | Headless command (to be written after Gate 0) |
|---|---|
| Claude Code | `<FLAGS CONFIRMED AT GATE 0>` |
| Codex | `<FLAGS CONFIRMED AT GATE 0>` |

Fixed judges and agents:

| Role | Fixed model | Set by |
|---|---|---|
| Claude judge | Opus 5.5 | Human decision, 2026-11-15. Effort set at Gate 1. |
| Codex judge | Decided at Gate 1 | Human |
| Inventory agent | Opus 5.5 | Human decision, 2026-11-15 |
| Gold drafter and gap pass | Chosen at Gate 0 | Human. The gap pass uses the other model family. |

## 6. Task templates

Each block below is pasted to a worker as the whole task. Placeholders in
`<ANGLE BRACKETS>` are filled in by the coordinator. Every template says
which files may be read, which may not, the output file and its shape, and
that no other model or API may be called.

### T1: gold drafter (transcript only)

```text
TASK: draft the gold reference for one session transcript.

You may read: the transcript only, <TRANSCRIPT_FILE> (or <CASE_DIR>/dialogue.txt).
You must NOT read: any other file in the case folder, any bundle, knowledge or
wiki folder, any extraction output, any audit file, any earlier draft, any file
under a runs folder, or any campaign notes. Do not use what you already know
about this campaign.
Do not call other models or APIs.

Write facts that the transcript states. Include what a speaker reports as a belief
or rumour, marked as such. Do not add rules text as lore. Where the transcript is
ambiguous, write a question instead of a guess.

Output: one file, draft.json, in your working folder. Shape:
{
  "version": 1,
  "entities": [{"id": "<unique id>", "label": "...", "aliases": ["..."], "required": true,
                "accepted": [{"type": "<EntityType value>", "subtypes": ["..."] or null}],
                "evidence": ["S012"]}],
  "facts": [{"id": "<unique id>", "statement": "...", "scene": "...", "subjects": ["<entity id>"],
             "evidence": [{"segment": "S012", "quote": "<exact text of that segment>"}],
             "qualifiers": "", "weight": 1 or 3, "placement": "any" | "recap" | "notes"}],
  "notes": [{"id": "<unique id>", "fact": "<fact id>", "entity": "<entity id>", "weight": 1 or 3}],
  "critical": [{"id": "<unique id>", "description": "...", "trigger": "...",
                "evidence": ["S012"], "rationale": "..."}],
  "questions": [{"id": "<unique id>", "text": "...", "segments": ["S012"], "items": ["<fact id>"]}],
  "excluded": [{"segments": ["S012"], "reason": "..."}]
}

Rules:
- Segment ids are "S" plus three digits: the segment's position in the transcript (S000 to S190).
- Every quote must be an exact substring of the segment it cites.
- Weight is 3 (essential) or 1 (useful). No other value.
- Every required entity has at least one accepted type. Every note points to an existing fact and entity.
- Every critical rule has a non-empty trigger.
Write no other file.
```

### T2: gap pass (transcript plus draft, other model family, never edits the draft)

```text
TASK: review a draft gold reference against the transcript. File objections and
additions. Do not edit the draft.

You may read: the transcript (<TRANSCRIPT_FILE>) and the draft (<CASE_DIR>/gold/draft.json).
You must NOT read: any other file in the case folder, any extraction output, any
audit file, any bundle, knowledge or wiki folder, any runs folder, any campaign
notes. Do not use what you already know about this campaign.
Do not call other models or APIs. Do not edit draft.json.

Look for: facts the transcript states that the draft misses; draft facts the
transcript does not support; wrong weights; quotes that are not exact; wrong
entity, subject or placement; missing critical rules; missing questions.

Output: one file, gap_objections.json, in your working folder. Shape (defined by
this document; the contract does not fix it):
{
  "additions":  [{"statement": "...", "segments": ["S012"], "quote": "<exact text>", "reason": "..."}],
  "objections": [{"draft_id": "<id in draft.json>", "problem": "...", "segments": ["S012"], "reason": "..."}]
}
Use empty lists when there is nothing to report. Write no other file.
```

### T3: generator (prompt only)

```text
TASK: answer the request in your input exactly as it asks.

Your only input is the contents of prompt.txt, which the launcher gives you.
You have no tools. You may not read files, search, or call other models or APIs.
Reply with the JSON object only. No commentary, no notes before or after it.
The launcher captures your reply. Do not write any file.
```

### T4: format repair (raw answer and validator error only)

```text
TASK: fix only the format of a reply that failed validation.

You may read: the reply (raw.txt) and the validator error below. Nothing else.
You must NOT read: prompt.txt, the transcript, the gold, any other attempt, any
judgment or report.
Do not call other models or APIs. You have no tools besides this input.

Change format only: JSON syntax, code fences, brackets and commas, a field's type,
or a single value the error names (for example a timestamp in the wrong form).
For a named value, change only what the error names, as little as possible.
Never change any wording in the recap or in notes. Do not add, remove or reorder
entities, claims or sentences.

Validator error:
<VALIDATOR_ERROR_TEXT>

Reply with the repaired JSON object only. The launcher writes it to repair.raw.txt.
```

### T5: claim inventory (output only, no transcript)

```text
TASK: list the checkable claims in one anonymous output. Output file: inventory.json.

You may read: <GRADING_DIR>/output.json only.
You must NOT read: the transcript, gold, rubric, any judgment file, any exchange
file, any attempt folder, the identity map, any usage file, any other folder.
Do not call other models or APIs.

Split the recap and each entity note into sentences. Each sentence must be
covered by a span of the same location. A span is an exact substring of that
location's text, and the span and the sentence must contain each other.
A sentence that makes no checkable claim gets kind "not_claim" with its own span.
Each checkable sentence gets kind "claim".

Locations: "recap", or "entity:<i>" where i is the 0-based position of the entity
in the output's entities list.
Group: claims that say the same thing, across recap and notes, share one group name.
A claim and its contradiction get different group names.

Output shape:
{
  "output_sha256": "<copy from task message>",
  "config": {<copy from task message>},
  "claims": [{"id": "C001", "loc": "recap", "span": "...", "group": "g01", "kind": "claim" | "not_claim"}]
}
Write no other file.
```

### T6: judge packet A (factual claims and citation locators, transcript only, NO gold)

```text
TASK: judge the factual claims and citation locators of one anonymous output,
against the transcript only.

You may read: <GRADING_DIR>/output.json, <GRADING_DIR>/inventory.json, and the
transcript (<CASE_DIR>/dialogue.txt).
You must NOT read: gold/, any rubric, any other judge's file (A., B. or .x. files),
exchange/, private/, any attempt folder, any usage file, any other folder.
Do not call other models or APIs. You are not told which model made this output.
Do not guess.

Claims: judge each item in inventory.json with kind "claim", using one verdict:
- "supported": the transcript supports it. A faithfully reported belief or rumour is "supported".
- "contradicted": the transcript says the opposite.
- "unsupported": the transcript does not support it. Being absent from what you
  know is NOT a reason for "unsupported". Only the transcript counts.
- "unresolved": you cannot decide from the transcript.
Claims in one group must get the same verdict; if you think they differ, say so in why.

Locators: for each emitted entity (index i), judge its citation timestamp:
- "supported": a passage relevant to the entity or event starts in the cited segment,
  or in the two segments before or after it.
- "not_supported": no such passage.
- "unresolved": unclear.

For every item give "segments" (the segment ids you relied on) and "why" (one or two sentences).

Output: one file, <GRADING_DIR>/A.<YOUR_JUDGE_ID>.json. Shape:
{
  "binds": {"output_sha256": "...", "inventory_sha256": "...", "source_sha256": "...", "rubric_sha256": "..."},
  "judge": {"host": "...", "model": "...", "effort": "...", "prompt_sha256": "..."},
  "claims":   {"<claim id>":    {"verdict": "...", "segments": ["S012"], "why": "..."}},
  "locators": {"<entity index>": {"verdict": "...", "segments": ["S012"], "why": "..."}}
}
Copy "binds" and "judge" from the task message. Allowed claim verdicts: supported,
contradicted, unsupported, unresolved. Allowed locator verdicts: supported,
not_supported, unresolved. Write no other file.
```

### T7: judge packet B (coverage, placement, entities, critical rules, against gold)

```text
TASK: judge one anonymous output against the approved gold and the transcript.
Judge facts, note placement, entity records and critical rules.

You may read: <GRADING_DIR>/output.json, <CASE_DIR>/gold/v<N>.json (approved gold),
and the transcript (<CASE_DIR>/dialogue.txt).
You must NOT read: any other file in the case folder, inventory.json, any A. file,
any .x file, exchange/, private/, any attempt folder, any usage file, any other folder.
Do not call other models or APIs. You are not told which model made this output.

1. Facts (each gold fact id): "present" (stated, with its material qualifiers),
   "partial" (stated, a material qualifier missing), "absent", "conflicting"
   (the output says the opposite), "unresolved". Give "spans" (exact quotes from
   output.json) and "why".
2. Note requirements (each req id): "present" (the fact is in a note of the target
   record), "absent", "wrong_entity" (the fact is in a note of another record),
   "unresolved". "entity_index" = the index of the record where you found it, or null.
3. Emitted entities (index i): "match" is one of "gold:<entity id>" (the same
   entity as a gold entity, aliases included), "extra_supported" (a real entity
   not in gold, with transcript evidence), "duplicate_of:<index>" (the same as
   an earlier record), "unsupported", "unresolved". "type_ok": the record's type is
   in the gold entity's accepted list. "subtype_ok": the subtype is in that list;
   if the gold entity has no subtype list, set true. Give "segments".
4. Critical rules (each rule id): "violated", "not_violated", "unresolved", with
   "spans" and "why".

Output: one file, <GRADING_DIR>/B.<YOUR_JUDGE_ID>.json. Shape:
{
  "binds": {"output_sha256": "...", "source_sha256": "...", "rubric_sha256": "...", "gold_sha256": "..."},
  "judge": {"host": "...", "model": "...", "effort": "...", "prompt_sha256": "..."},
  "facts":    {"<fact id>": {"verdict": "...", "spans": ["..."], "why": "..."}},
  "notes":    {"<req id>":  {"verdict": "...", "entity_index": 0, "why": "..."}},
  "entities": {"<index>":   {"match": "...", "type_ok": true, "subtype_ok": true, "segments": ["S012"]}},
  "critical": {"<rule id>": {"verdict": "...", "spans": ["..."], "why": "..."}}
}
Copy "binds" and "judge" from the task message. Allowed fact verdicts: present,
partial, absent, conflicting, unresolved. Note verdicts: present, absent,
wrong_entity, unresolved. Critical verdicts: violated, not_violated, unresolved.
Write no other file.
```

### T8: evidence exchange (other judge's reasons only, one revision)

```text
TASK: one revision round on items where two judges disagreed. You see only the
other judge's cited parts and reasons. You do not see their verdict.

You may read: <EXCHANGE_FILE> and the item text the coordinator lists for each
item (claim span, fact statement, or rule description), plus only the transcript
segments named in the exchange file.
You must NOT read: any other judge file, any verdict, any other file in the case or run.
Do not call other models or APIs.

For each item, read the other judge's segments or spans and reasons. You may keep
your verdict or change it. You may revise once. Use the same verdict words as the
original packet.

Output: one file, <GRADING_DIR>/<A or B>.<YOUR_JUDGE_ID>.x.json. Same shape as the
original packet, with "binds" copied exactly, and only the revised items present.
Write no other file.
```

## 7. Scoring summary

### Components

Each component is 0 to 100. Q is the weighted sum of the five components.

| Part | What is counted | Denominator | Credit |
|---|---|---|---|
| F (factual correctness) | Claim groups from the inventory | All claim groups | A group counts when its single verdict is "supported" |
| C (coverage) | Gold facts | Sum of the weights of all gold facts | Weight of facts "present" |
| N (note placement) | Note requirements (fact, target entity, weight) | Sum of the weights of all note requirements | Weight of a requirement credited when the fact is "present" in a note of a target record (or a duplicate of one) |
| E (entity quality) | Emitted records and gold entities | See formula below | See formula below |
| G (citation grounding) | One locator per emitted record | All emitted locators | Locators "supported" |

**Q = 0.35 F + 0.20 C + 0.20 N + 0.15 E + 0.10 G** (weights from `rubrics/v1.json`).

**E in detail:**
- Precision = supported identities / emitted records. A supported identity is a required match, an optional match, or an extra supported record.
- Recall = matched required entities / required entities.
- Identity = 2 × precision × recall / (precision + recall), or 0 if either is 0.
- Classification = supported identities with a valid type and subtype / (required entities + matched optional + extras).
- E = 100 × (2/3 × identity + 1/3 × classification).

**Rounding.** No rounding inside the scoring. One decimal place is shown in the report only. Open items are shown as a range, for example `71.2–74.0 (open)`.

### Judgment status

Each attempt gets one status.

| Status | When |
|---|---|
| `invalid` | Attempt state is failed or pending, or the output has zero claim groups. No Q. |
| `provisional` | Any of: gold approval missing or stale; a judge of this output is not calibrated; judgments stale; fewer than two judges; any open item. Bounds are shown, no winner is named. |
| `official` | None of the above. |
| `critical` (separate flag) | A critical rule is resolved "violated". It is listed beside the status. It does not change Q. |

Calibration bar for a judge (default in `rubric["calibration"]`): at least 90% agreement with the human overall, at least 85% on F items, zero critical misses. Both the tuning set and the held-out set must pass.

A configuration (arm) is **eligible** only when every attempt is `official`, none is `critical`, none is `failed`, and none is retrospective.

### Selection policy (decided by the human)

| Step | Rule |
|---|---|
| 1 | Drop configurations that are not eligible from selection. Keep them in the table. |
| 2 | Best quality = highest mean Q across repeats. Print the range and any ties. |
| 3 | Within tolerance = eligible configurations with mean Q at most 2.0 below the best (2.0 is in, 2.01 is out). |
| 4 | Best value = the cheapest standard cost among those, only when every one of them has a known cost. |
| 5 | If a configuration outside tolerance has a max Q at least the best's min Q (a rank flip), there is no best value. |
| 6 | No points-per-dollar figure is produced. The report states the extra cost of the higher-quality option. |

If there is no eligible configuration, both winners are empty.

## 8. Cost

### Two figures

| Figure | Formula per model turn (prices per million tokens) |
|---|---|
| Standardized uncached (primary) | (input_total × input price + output_total × output price) / 1,000,000. No cache surcharge. |
| Observed cache (secondary) | (fresh input × input price + cache read × cache-read price + cache write × cache-write price + output_total × output price) / 1,000,000, where fresh input = input_total − cache read − cache write. |

An attempt's cost is the sum over every model turn of that attempt, including
the repair turn. A configuration's cost is the mean over its valid attempts.
**Cost per valid output** = cost of all attempts, including failed ones, ÷ valid outputs.

Reasoning tokens are shown for information. They are already inside output tokens and are never added again.

### Two provider usage styles

| Style | Used by | Meaning of `input_tokens` | How the harness reads it |
|---|---|---|---|
| openai | DeepSeek, Codex | Includes cached tokens. Cached tokens are a subset. | input_total = input; cache read = cached subset; cache write = 0. Fresh input = input − cached. |
| anthropic | Claude Code | Excludes cache tokens. Cache read and cache write are separate fields. | input_total = input + cache read + cache write. |

The two styles differ because the providers count cache tokens differently.
Reading one style as the other double-counts or drops tokens. The harness
rejects an unknown style.

### What makes a cost unknown

A figure is `unknown` (stored as `None`, never 0) when any of these holds:
- a needed usage field is missing;
- the usage file is missing for a turn, including a repair turn that has a `repair.raw.txt` but no `repair.usage.json`;
- there is no price row for the exact model;
- there are no recorded turns;
- input_total is above the price row's `max_input_tokens` (a context tier).

Each unknown figure carries a reason. A configuration's standard cost is unknown if any of its attempts is unknown.

Retrospectively, only DeepSeek has complete usage. Codex arms have none. Claude arms record only main-turn output. So every subscription arm is **cost unknown** at the retrospective stage.

### Separate ledgers

Grading usage (inventory, judges, exchange) is stored in `usage.*.json` and summed as `grading_cost`. Drafting and coordinator usage are not in the harness and are not counted. The report shows three lines: extraction cost, grading cost and total benchmark cost. Grading cost is never added to extraction cost.

### Prices

- One row per exact model: currency, input, cache read, cache write, output, tier, `max_input_tokens`, source URL and retrieval date.
- Prices come from the provider documents at the time of the run. The human confirms each row. Prices are never hardcoded.
- Check on the DeepSeek retrospective run, using the rates in the plan (off-peak): 12,700 input tokens × $0.66 per MTok + 17,303 output tokens × $1.98 per MTok ≈ $0.043. Re-check the rates before relying on this.

A diagnostic figure (input tokens minus the host's fixed prompt overhead, measured at Gate 0) is shown for information only.

## 9. Limits

The report prints this list in every report.

- One session, 5,072 words. No cross-session confidence interval. The repeat mean and range describe sampling noise on this case only.
- Once failures inform a prompt, this is a regression case, not an unseen test.
- Claims within one output are correlated; they are not independent observations.
- The existing outputs were made with file-tool subagents, not the generation protocol in section 5. They are comparable on quality, not on cost.
- Host harnesses add their own system prompt. Temperature cannot be controlled. Claude and OpenAI effort names are not equivalent.
- API-equivalent dollars are a proxy. They are not the subscription bill or the quota.
- Extraction quality says nothing about synthesis, state or dedup.

## 10. What is out of scope

- More sessions, audio checks, and any change to the transcription pipeline.
- Switching production to a new model or prompt. Nothing is promoted to the production config.
- A full extraction run for the season.
- Converting subscription usage into quota figures.
- Any evaluation platform, database or dashboard.
- Any change to `graph/`, `knowledge/`, `prompts.py`, prompt-version constants or `.claude/hooks/`.
- A DeepSeek rerun. DeepSeek is only the baseline.
- A points-per-dollar figure.
- Any agent-run approval of gold.

## 11. Open items

These points are not settled by the sources. Decide them before the phase that needs them.

1. Exact headless flags for Claude Code and Codex. Gate 0.
2. Drafter and gap-pass models. Gate 0.
3. Codex judge model and effort, and the Claude judge's effort. Gate 1.
4. The gap check against the 20 old audit probes (plan Phase 2, step 3). No command exists yet.
5. The shape of `gap_objections.json` is defined in T2 here, not in the sources.
6. The exchange file (`exchange/`) holds segments and reasons but not the item text. Template T8 assumes the coordinator adds the item text.
7. The location and writer of `adjudication.json`. The human writes it. The location is assumed to be under `runs/<run>/`.
8. Repeat numbering for Gate 4. `prepare-run` numbers repeats from 1. Adding repeats 2 and 3 to a finalist needs a rule.
9. The record of the Gate 5 choice. No command writes it.
10. The plan requires that a best-value winner shows no reliability loss across repeats. The contract's `select` does not check this.
11. The plan asks for "lower bound" labels on partial costs. The contract returns `None` for any unknown figure.
12. The repair similarity check: the plan compares recap and notes only; the contract compares the whole output's letters and digits.
13. Price file location and naming (the plan suggests `prices/<date>.json`).
