# Agent mode — how to use it

Run the pipeline's LLM steps on a Claude Code or Codex subscription instead of
the DeepSeek API. The rules do not change: same prompts, same validation, same
caches, same emit. Only *who answers the model call* changes.

Background: [ADR-006](architecture/ADR-006-agent-mode.md) (why it works this
way) and [PIPELINE.md §3b](architecture/PIPELINE.md) (mechanics).

## The short version

In a Claude Code or Codex chat opened on this repo:

```
/pnp-agent-run
```

The skill asks which model runs which step and which sessions to process. Then
it loops until the bundle is written, and stops so you can review the diff.
Everything below explains what it does, so you can drive it by hand or check
its work.

## 1. Choose a model per step

There are five LLM steps:

| Step | What it does | Default (API) |
|---|---|---|
| `extract` | transcript → entity mentions + recap, one call per session | `deepseek-v4-pro` |
| `deep` | prose for important entities | `deepseek-v4-pro` |
| `standard` | prose for the rest (brief entities never call a model) | `deepseek-v4-flash` |
| `state` | threads, status and attitude changes, one session at a time | `deepseek-v4-pro` |
| `dedup` | merge proposals (`pnp dedup` only) | `deepseek-v4-flash` |

Each step takes an API model or an **agent label**, `agent:<host>:<model>`:

```
agent:claude:claude-opus-5-5
agent:claude:claude-sonnet-5-5
agent:codex:gpt-6.1-terra
```

Set them per command with `--model STEP=LABEL` (repeatable), or permanently in
`services/kb/.env`:

```
PNP_MODEL_EXTRACT=agent:claude:claude-opus-5-5
PNP_MODEL_DEEP=agent:claude:claude-opus-5-5
PNP_MODEL_STANDARD=agent:claude:claude-sonnet-5-5
PNP_MODEL_STATE=agent:claude:claude-sonnet-5-5
PNP_MODEL_DEDUP=agent:claude:claude-haiku-5-5
```

`PNP_MODEL_*` wins over the older `DEEPSEEK_*` variables, and `--model` wins
over both. `DEEPSEEK_API_KEY` is only needed while some step still uses the
API.

**`--no-api`** makes a command refuse to start unless all five steps are agent
labels. That is the mode the skill uses, and the only one an agent may start on
its own: a run with any DeepSeek step costs money and is the human's to start.

## 2. Choose which sessions

`--scope` (on `run` and `extract`) decides which sessions may be **sent to a
model** for extraction:

| `--scope` | Sends to a model |
|---|---|
| `all` (default) | every session that has no cached extraction |
| `active` | only sessions outside a frozen season |
| `pending` | only sessions with nothing frozen or cached yet |
| `2026-11-08,2026-11-01` | only the named sessions (id, date or first 10 chars) |

Every transcript is still loaded and the bundle is still written in full, so
the rename guard keeps working. A session outside the scope must already have
an extraction; if it has none, the run stops with exit 2 and names it.

Scope limits extraction only. Synthesis, state and dedup still ask for
whatever is not cached: a new session changes the entities it mentions, so
their prose is re-written.

(`--session` / `--limit` still mean a *partial* run, which disables the rename
guard. Prefer `--scope`.)

## 3. Results from other models are reused

A cached result is reused whenever its input is unchanged, **whichever model
made it**. Switching extraction from DeepSeek to Claude therefore re-does only
new or changed sessions, not the whole corpus, and existing concept ids stay
where they are.

`--strict-model` turns this off: only results from the configured model count,
so a model change re-does everything (the old behaviour; a budgeted event, see
PIPELINE.md §6). This applies to API runs too.

See what a run would do, for free:

```
cd services/kb
.venv/Scripts/python.exe -m pnp_okf.cli run --estimate --no-api <--model flags> --scope pending
```

It prints, per step, `N cached, R reused (<model>: n), M to call`.

## 4. The loop

All commands run from `services/kb` with its venv
(`.venv/Scripts/python.exe -m pnp_okf.cli …`, shortened to `pnp …` here).

```
pnp run --no-api <--model flags> --scope pending
```

1. Every cache miss becomes a **packet**: the exact request the API would have
   received, written to `state/agent/<step>/<id>.request.json`. The run ends
   with **exit 4** before anything is written to the bundle.
2. `pnp agent status --json` lists the pending packets with step, model and
   path.
3. One worker per packet, **on the packet's model**, reads the request and
   writes `<id>.response.json` (JSON steps) or `<id>.response.md` (prose),
   plus `<id>.meta.json` `{"host": …, "model": …}`. In Claude Code the skill
   uses the Agent tool's `model` parameter. In Codex it uses a subagent, or
   `codex exec -m <model>` per packet.
4. `pnp agent status` validates each answer against the same schema the
   pipeline uses. A bad answer goes to `rejected/` with the reason in
   `<id>.error.txt`, and the packet is open again.
5. Run the same command again. Answers are served as if the API had returned
   them, then cached under the agent label.

Repeat until exit 0. Expect at least two rounds: synthesis packets only appear
once every extraction is answered. On exit 0 the bundle is written and
validated exactly as after an API run.

Then, if wanted:

```
pnp state --no-api <--model flags>    # sequential: one packet per round
pnp dedup --no-api <--model flags>    # writes only knowledge/conflicts/merge_proposals.md
```

`pnp state` needs `knowledge/state_glossary.yaml`. `--refresh-glossary` writes
it, but changes every state cache key, so it is a human decision.

### Exit codes

| Code | Meaning | Next |
|---|---|---|
| 0 | done, bundle written and validated | review the diff |
| 2 | configuration error, rename guard, scope gap | read the message, fix, rerun |
| 3 | bundle failed integrity validation | stop, investigate |
| 4 | packets pending, or a bad answer was rejected | answer the packets, rerun |

## 5. Review and merge

Run agent mode on an `ingest/s<NN>` branch of the bundle repo, never on its
`main`. The skill checks this and stops after:

```
pnp validate
git -C ../../knowledge diff --stat
```

You review the bundle diff and merge it as a PR, like any ingest
([RELEASING.md](RELEASING.md)).

## Mixing API and agents

Allowed: for example, extraction on DeepSeek and synthesis on Claude. Leave out
`--no-api` and pass the `--model` flags you want. Because it calls DeepSeek, a
mixed run is a paid run: you start it yourself, and the agent answers the
packets it leaves behind between your reruns.

## What agent mode cannot guarantee

- **Temperature.** The API runs at 0.1–0.3; an agent runs at whatever its host
  uses.
- **The model.** `meta.json` records what the worker reports about itself; it
  is not proof. In Claude Code, the Agent tool's `model` parameter is the
  strongest control there is. `pnp agent status` warns when the report
  disagrees with the label.
- **Where the data goes.** Packets contain transcript text with player names,
  and are sent to Anthropic or OpenAI instead of DeepSeek. `state/agent/` is
  gitignored.
- **History noise.** Every exit-4 stop is recorded in `history.jsonl` as a
  failed run.

## Files

| Path | What |
|---|---|
| `.agents/skills/pnp-agent-run/SKILL.md` | the skill (canonical, read by Codex); `.claude/skills/pnp-agent-run/` points to it |
| `services/kb/src/pnp_okf/handoff.py` | the handoff client: request/response files, exit-4 exceptions |
| `services/kb/src/pnp_okf/reuse.py` | which models' cache entries a lookup may use |
| `services/kb/src/pnp_okf/agent_status.py` | `pnp agent status` |
| `services/kb/state/agent/` | the packet queue (`PNP_AGENT_DIR` overrides) |
