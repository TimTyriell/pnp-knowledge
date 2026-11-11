---
name: pnp-agent-run
description: Run the pnp_okf pipeline's LLM steps (extract, deep and standard synthesis, state, dedup) on a Claude or Codex subscription instead of the DeepSeek API, by answering each request packet with a worker agent. Use when the user asks for agent mode, to run pnp "without the API", "on my subscription", on Claude or Codex, or to answer pnp agent packets. Triggers: pnp-agent-run, agent mode, agent packets, pnp agent status, --no-api, agent:claude, agent:codex.
---

# pnp-agent-run

Drives `services/kb` (`pnp_okf`) with agent workers instead of DeepSeek. Design:
`docs/architecture/ADR-006-agent-mode.md`; mechanics: `docs/architecture/PIPELINE.md` §3b.
Run every command from `services/kb` with its venv: `.venv/Scripts/python.exe -m pnp_okf.cli ...`
(below: `pnp ...`). The bundle repo is `../../knowledge` (gitignored, private).

## 1. Confirm with the user

- **Model per step.** Five steps: `extract`, `deep`, `standard`, `state`, `dedup`. `--no-api`
  requires all five to be agent labels, `agent:<host>:<model>`, e.g.
  `agent:claude:claude-opus-5-5` or `agent:codex:gpt-6.1-terra`. Pass them as
  `--model STEP=LABEL` (repeatable).
  Mixed runs (some steps on DeepSeek, some on agents) work the same way but cannot use
  `--no-api`, so they are paid runs: hand the exact command to the human to start, then
  answer the packets it leaves while they rerun it.
- **Scope:** `all`, `active`, `pending`, or comma-separated session ids. Applies to `run` and
  `extract`. If `pnp run --help` does not list `--scope`, stop and tell the user.
- **Commands:** `run` (the pipeline), `state`, `dedup`. Default: `run`, then `state`.
- **NN:** the session number for the bundle branch `ingest/s<NN>`.

## 2. Preflight

```
pnp check
pnp run --estimate --no-api <--model flags> --scope <X>
git -C ../../knowledge branch --show-current
```

- The branch must be `ingest/s<NN>`. If it is `main`, ask for NN, then
  `git -C ../../knowledge switch -c ingest/s<NN>` (or `switch ingest/s<NN>` if it already
  exists). Never commit on `main`. Never push, merge or tag.
- `pnp state` needs `knowledge/state_glossary.yaml`. If it is missing, ask the user before
  running `pnp state --refresh-glossary`: it changes every state cache key.

## 3. The run loop

1. `pnp run --no-api <--model flags> --scope <X>`
2. Exit `0`: go to step 4.
   Exit `4`: packets are pending, or an invalid answer was moved to `rejected/` and re-queued.
   Continue below.
   Exit `2` or `3`: stop and report the output. Do not retry.
3. `pnp agent status --json`. Read the pending packets: packet id, step, model, request path.
4. Dispatch **one worker per packet, on that packet's model**. Run up to 8 in parallel.
   - **Claude Code:** Agent tool with `model` mapped from the label: `claude-opus-*` → `opus`,
     `claude-sonnet-*` → `sonnet`, `claude-haiku-*` → `haiku`, `claude-fable-*` → `fable`.
     If a label does not map, stop and ask the user.
   - **Codex:** a subagent if the host can set its model; otherwise one headless
     `codex exec -m <model> "<worker prompt>"` per packet. The worker must be allowed to write
     into the queue folder.
   - Give each worker the template in section 6 with the packet's request path and id.
5. `pnp agent status`. For each rejected packet, re-dispatch the same packet id on the same
   model, with the text of `<id>.error.txt` added to the worker prompt. Never edit answers or
   request files yourself.
6. Run the same `pnp run --no-api ...` command again. Repeat until exit `0`.

Expect several rounds: extraction must finish before synthesis packets appear.

## 4. State and dedup

- `pnp state --no-api <--model flags>`: sequential, one packet per iteration. Exit `4`:
  dispatch the one pending packet, then rerun. Repeat until exit `0`. Use `--limit N` to bound
  it. `--session` is not accepted by `state`.
- Optional, after state: `pnp dedup --no-api <--model flags>` in the same loop. Dedup writes
  only `knowledge/conflicts/merge_proposals.md`; the registry is not touched. A human confirms
  every merge group.

## 5. Finish

- `pnp validate` (exit `0` expected).
- `git -C ../../knowledge diff --stat`.
- Report the packet counts per step and model, from the `agent status --json` output and the
  run's `agent_calls` in `state/last_run.json`.
- Stop for human PR review. Leave the changes uncommitted unless the user asks for a commit on
  `ingest/s<NN>`.

## 6. Worker prompt template

Use this text verbatim for every worker, filling in the paths and id:

```
You are answering one pnp request packet. The packet is a JSON file at:
<REQUEST_PATH>   (packet id: <ID>, step: <STEP>, model: <MODEL>, response_kind: <KIND>)

1. Read that file. Its "messages" array is the conversation (system, then user). Answer
   exactly as that model call would: obey every instruction in the messages (language,
   schema, format). Do not add commentary.
2. If response_kind is "json", write ONLY the JSON object as the answer.
   If response_kind is "markdown", write ONLY the body text.
3. Write the answer to <ID>.response.json (json) or <ID>.response.md (markdown), in the same
   folder as the request file.
4. Write <ID>.meta.json in the same folder with exactly:
   {"host": "<claude or codex>", "model": "<your exact model id>"}
5. Do not read or write any other file. Run no other command. Never edit anything under
   knowledge/.
```

## 7. Rules

- Never run a pnp step without `--no-api` in this skill. A paid run needs the human. The guard
  blocks it anyway.
- Never edit request files, responses, the cache or `knowledge/` by hand.
- A packet's answer must come from a worker on that packet's model. Do not answer packets
  yourself, or on a different model.
- An exit `4` is a normal stop, not a failure: answer packets and rerun the same command.
- Do not change the model map or scope mid-loop without telling the user.
