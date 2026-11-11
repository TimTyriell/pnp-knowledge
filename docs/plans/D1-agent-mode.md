# D1 — Agent mode: run the LLM steps on a Claude/Codex subscription

Branch: `feat/agent-mode` · Needs: C1 merged (#41) · Cost: $0 · Who: agent + human (guard edit, smoke run)

## Intent

Every LLM step of `pnp_okf` (extraction, deep/standard synthesis, state pass,
dedup) calls DeepSeek through `.env`. Agent mode lets the same steps be
answered by Claude Code or Codex agents on the human's subscription, driven
from a chat by a skill.

Constraints:

- **Same rules and borders.** Same prompts, same pydantic validation, same
  caches, same resolve → emit → validate, same guards. Which path produced a
  result must not matter downstream.
- **Per-step model control.** `extract`, `deep`, `standard`, `state`, `dedup`
  each pick an API model or an agent label, independently. Mixing is allowed.
- **Session scope.** all / active (not frozen) / pending (no extraction yet) /
  named sessions.
- Agent mode may need a chat to drive it (it is not a pure CLI feature).
- No prompt text, no `*_PROMPT_VERSION`, no `knowledge/` edits.

Human decisions (2026-11-11): v1 covers all four steps; when a step's model
changes, results for **unchanged inputs are reused from any model by default**
(`--strict-model` restores per-model semantics); the skill runs the final
emit on an `ingest/s<NN>` bundle branch and the human reviews the PR.

Precedent: `services/kb/.cache/manual_terra_shadow/run.py` (untracked) did
synthesis this way once — captured the exact messages with a fake client,
agents wrote bodies, real emit + `validate_bundle` gave `integrity_ok=true`.

## Design

All four steps build their client through `llm_client.build_client(cfg)`
(`extract_session`, `synthesize_entity_body`, `run_state`, `llm_candidates`).
Agent mode is one branch there:

```
pnp run --no-api        cache miss for model "agent:claude:claude-opus-5-5"
  HandoffClient.create  writes state/agent/<step>/<id>.request.json, raises AgentPending
  stage collects them   exit 4 "N packets pending" -- before any bundle write
skill (in chat)         workers on the requested model write <id>.response.{json,md}
pnp agent status        validates responses with the step's own pydantic model
pnp run --no-api        HandoffClient returns the response as a completion; the
                        existing parse/validate/cache code runs unchanged -> exit 0
```

- Agent label: `agent:<host>:<model>`, e.g. `agent:claude:claude-opus-5-5`,
  `agent:codex:gpt-6.1-terra`. It is `cfg.model`, so it is in every cache key
  already: agent results cache exactly like API results.
- Packet id: `sha256(json({model, messages}, sort_keys))[:16]`. A changed
  prompt or context is a new id; stale packets just stop matching.
- Extraction: the handoff client's `beta...parse` raises, so the existing
  structured-outputs probe falls back to the JSON-prompt path, which already
  appends the schema and validates with `model_validate_json`.
- A response that fails validation triggers tenacity's retry, i.e. a second
  request for the same id on the same client → move the response to
  `rejected/` and raise non-retryable `AgentResponseInvalid`.
- `AgentPending` is not retryable → propagates at once. The stage order
  (PIPELINE.md §3, §7: all LLM work before the first durable write) means
  exit 4 never leaves a half-written bundle.
- Queue lives in `PNP_AGENT_DIR`, default `<PNP_STATE_DIR or ./state>/agent`
  (gitignored; holds transcript text with player names).
- Not guaranteed in agent mode: temperature, and the model itself (the
  worker's self-report is recorded, not trusted). Claude Code's subagent
  `model` parameter is the strongest control available.

## Steps

Tests first (`.claude/skills/test-driven-development`). Run from
`services/kb`; reuse the fake-client patterns in `tests/test_llm_retry.py`,
`tests/test_state_runner.py`, `tests/test_pipeline_offline.py`.

### Phase 1 — routing, handoff client, exit 4

1. `config.py` `DeepSeekConfig`
   - New fields `step: str = ""`, `dedup_model: str = DEFAULT_LIGHT_MODEL`.
   - `from_env`: each step reads `PNP_MODEL_<STEP>` first, then the old var:
     extract ← `PNP_MODEL_EXTRACT` | `DEEPSEEK_EXTRACT_MODEL` | model;
     deep (`model`) ← `PNP_MODEL_DEEP` | `DEEPSEEK_MODEL`;
     standard (`light_model`) ← `PNP_MODEL_STANDARD` | `DEEPSEEK_LIGHT_MODEL`;
     state ← `PNP_MODEL_STATE` | `DEEPSEEK_STATE_MODEL` | model;
     dedup ← `PNP_MODEL_DEDUP` | light_model.
   - `DEEPSEEK_API_KEY` is required only when some step model does not start
     with `agent:`.
   - `for_tier(tier)` sets `step=tier` on the returned config and accepts
     `"dedup"`. Keep the existing `deep`/`standard` behaviour.
   - New `is_agent(model) -> bool` and `DeepSeekConfig.step_models() -> dict`.
2. New `pnp_okf/handoff.py`: `AgentPending(step, packet_id, path)`,
   `AgentResponseInvalid`, `AgentWorkPending(pending: list)`,
   `agent_dir()`, `packet_id(model, messages)`, `HandoffClient(cfg)` with
   `chat.completions.create(**kw)` and `beta.chat.completions.parse(**kw)`
   (raises `NotImplementedError`). Response kind: `json` when
   `response_format` is passed, else `markdown` (file `<id>.response.json` /
   `<id>.response.md`). Request file: `{id, step, model, response_kind,
   temperature, messages, created}`. Served completion:
   `choices[0].message.content` (and `.parsed=None`), `usage=None`.
   Module-level `AGENT_CALLS: Counter[(step, model)]`, incremented on serve.
3. `llm_client.build_client`: `if is_agent(cfg.model): return HandoffClient(cfg)`.
4. `dedup._ask_chunk`: its `except Exception` swallows everything — add
   `except (AgentPending, AgentResponseInvalid): raise` before it.
   `cli.cmd_dedup`: use `cfg.for_tier("dedup")` instead of `for_tier("standard")`.
5. `cli.py`
   - `_extract_all._one` and `_run_pipeline._synth`: catch `AgentPending`,
     record it, return a placeholder; after the pool joins, if any were
     recorded raise `AgentWorkPending(all of them)`. (Synthesis can only
     start once extraction is complete, so a run with pending extraction
     stops after extraction.) Same in `cmd_dedup` via the exception from
     `llm_candidates` — collect per chunk there (`llm_candidates` gathers
     `AgentPending` per chunk and raises `AgentWorkPending` at the end).
   - `run_state` is sequential: the first `AgentPending` propagates; wrap it
     as `AgentWorkPending([it])` in `cmd_state` / `_run_pipeline` callers.
   - `_add_common`: `--model STEP=LABEL` (append), `--no-api`,
     `--strict-model`. `main()` applies `--model` by setting
     `os.environ["PNP_MODEL_<STEP>"]` before dispatch (every
     `DeepSeekConfig.from_env()` call site then sees it), rejects unknown
     steps, and for `--no-api` raises `ConfigError` unless every step model
     is `agent:`.
   - `main()` catches `AgentWorkPending`: log one line per step+model with
     the count and the queue dir, return **4**.
   - `_write_run_status` counts gain `agent_calls` (from `AGENT_CALLS`, as
     `{"<step>|<model>": n}`) when non-empty.

### Phase 2 — reuse across models (default on)

6. New helper in `config.py` (or a small `pnp_okf/reuse.py`):
   `candidate_models(cfg, cache_dir) -> list[str]`: `[cfg.model]` when
   `PNP_STRICT_MODEL=1` (set by `--strict-model`), else unique, in order:
   `cfg.model`, every value of `cfg.step_models()`, `DEFAULT_MODEL`,
   `DEFAULT_LIGHT_MODEL`, lines of `<cache_dir>/models.txt`.
   `remember_model(cache_dir, model)` appends a new model to `models.txt`.
7. Lookups try each candidate with `dataclasses.replace(cfg, model=m)`; the
   first hit wins; stores always use the configured model and call
   `remember_model`:
   - extraction: new `find_cached_extraction(cache_dir, t, cfg, frozen=None)
     -> tuple[SessionExtraction, Path] | None`; `load_cached_extraction` and
     `extract_session` (when not `force`) use it.
   - synthesis: same inside `synthesize_entity_body`; expose
     `find_cached_body(...) -> tuple[str, Path] | None`.
   - state: in `run_state`, try candidates for the key before calling.
8. `cache_gc.live_entries` must add the **path that was hit**, not the
   configured-model path — otherwise GC sweeps the reused entries. Use the
   new `find_*` helpers. Extend `test_live_set_matches_what_a_run_writes`
   (or add a test) for a reused entry.
9. `_estimate_run` prints `cached / reused (<model>) / to call` per step.

### Phase 3 — session scope

10. `--scope all|active|pending|<id,id,...>` on `run` and `extract`
    (default `all`). It limits which sessions may be **sent to a model**;
    everything else still loads from frozen/cache, and the run stays a full
    run (rename guard on). `--session` / `--limit` keep their old
    partial-run meaning.
    - `active`: `frozen.season_of(sid) is None` (note: nothing is frozen
      today, so active == all until `pnp freeze` runs).
    - `pending`: no frozen extraction and no `find_cached_extraction` hit.
    - ids: matched like `_select` (session id, date, first 10 chars).
    - An out-of-scope session with no frozen/cached extraction: `ConfigError`
      naming the sessions (never silently dropped).

### Phase 4 — `pnp agent status`, citation ranges

11. `pnp agent status [--json]`: pending requests grouped by step + model;
    validates every present response with the step's own contract —
    extract `SessionExtraction` plus "recap but zero entities" rule, state
    `SessionState`, dedup `dedup._MergeResponse`, synthesis non-empty
    markdown. Invalid → move request-matching response to `rejected/` with an
    `<id>.error.txt`; exit 1 if any were invalid. Warn when `<id>.meta.json`
    `model` differs from the packet's label.
12. Agents write `[1–3]`; `episodes.relabel_citations` only handles
    comma lists. Port `expand_citation_ranges` from the prototype
    (`.cache/manual_terra_shadow/run.py:18-33`) into `episodes.py` and apply
    it first inside `relabel_citations`. Test with `[1–3, 5]` and a
    `[2-4](x.md)` link that must stay untouched.

### Phase 5 — skill, docs

13. `.agents/skills/pnp-agent-run/SKILL.md` (canonical; Codex reads
    `.agents/skills`) and `.claude/skills/pnp-agent-run/SKILL.md` (frontmatter
    + "Read and follow `.agents/skills/pnp-agent-run/SKILL.md`"). Flow:
    confirm step→model map and scope → `pnp check` → bundle repo branch
    must be `ingest/s<NN>` (create from its main if missing; never commit on
    main) → loop `pnp run --no-api ...` / exit 4 / `pnp agent status --json` /
    dispatch one worker per packet on the packet's model (Claude: Agent tool
    `model` from the label; Codex: per-packet `codex exec -m <model>` when the
    chat cannot pick a subagent model) / `pnp agent status` → until exit 0 →
    `pnp state --no-api` loop → optional `pnp dedup --no-api` →
    `pnp validate` + `git -C knowledge diff --stat` → stop. Worker contract:
    read the request, follow its messages verbatim, write only
    `<id>.response.*` and `<id>.meta.json` (`{host, model}`).
14. Docs: PIPELINE.md new §3b "Agent mode" + §6 consequence 3 (reuse is now
    the default) + §12 exit code 4; `.env.example` `PNP_MODEL_*` block;
    `docs/architecture/ADR-006-agent-mode.md` (choke point, reuse default,
    what is not guaranteed; agent mode sends transcripts to Anthropic/OpenAI
    instead of DeepSeek — same exposure class, human's choice).

### HUMAN — guard

15. `.claude/hooks/guard.ps1` blocks `pnp run|extract|state|dedup` without
    `--estimate`. Allow them with `--no-api`; add cases to
    `.claude/hooks/test_guard.py`. Needs `PNP_ALLOW_GUARD_EDIT=1`.

### HUMAN RUN — smoke

16. In a Claude chat: `/pnp-agent-run` with `--scope pending` against a
    throwaway bundle (`PNP_BUNDLE_DIR` relative override), then compare with
    the API bundle as in the Terra comparison.

## Done when

- [ ] Agent label routes to the handoff client; API labels unchanged
- [ ] Pending work exits 4 and leaves the bundle byte-identical
- [ ] Served responses go through the unchanged parse/validate/cache code for all four steps
- [ ] Reuse across models on by default, off with `--strict-model`; GC keeps reused entries
- [ ] `--scope` all/active/pending/ids works; out-of-scope gaps error
- [ ] `pnp agent status` validates and rejects
- [ ] Prompt pins unchanged; full suite and ruff green

    cd services/kb && .venv/Scripts/python.exe -m pytest -q
    cd services/kb && .venv/Scripts/python.exe -m pytest -q tests/test_prompt_pins.py tests/test_handoff.py tests/test_model_reuse.py tests/test_scope.py
    ruff check .
