# ADR-006 — Agent mode: the LLM steps can be answered by a Claude or Codex agent

**Status:** Accepted, 2026-11-12
**Related:** ADR-001 (OKF-in-git as system of record), ADR-005 (rules as hooks,
judgment at gates), `docs/plans/D1-agent-mode.md`, PIPELINE.md §3b

## Context

Every LLM step of `pnp_okf` (extraction, deep and standard synthesis, the
state pass, dedup) calls DeepSeek through `.env`. A full rebuild costs ~$6.5
off-peak, and the team already pays for Claude and Codex subscriptions that
sit idle between sessions. The wish: run the same steps on those
subscriptions, driven from a chat.

Three constraints shape the answer:

- **Same rules, same borders.** Prompts, pydantic validation, caches and the
  resolve → emit → validate chain must not change. Which path produced a
  result must not matter downstream. The prompt-pin test and the cache keys
  already enforce most of this.
- **Per-step control.** Each step picks an API model or an agent label,
  independently.
- **No silent cost.** The guard blocks paid `pnp` runs without `--estimate`.
  An agent run must not be a way around that guard, and must not reach
  DeepSeek by accident.

Two facts about the existing code made the design cheap. Every step builds its
client through one function, `llm_client.build_client(cfg)`, so the choke point
already exists. And the cache key already contains the model, so an agent
label caches exactly like an API model with no new key logic.

## Decision

1. **The handoff client sits at `build_client`.** An agent label
   (`agent:<host>:<model>`) returns a `HandoffClient` that quacks like the
   OpenAI client. On a cache miss it writes the exact request to a queue
   (`<agent_dir>/<step>/<id>.request.json`) and raises `AgentPending`. A
   worker writes the answer next to it; the next run serves that text as the
   completion. Parse, validate and cache code runs unchanged.
2. **The agent label is `cfg.model`.** It is in every cache key already, so
   agent results and API results are cached the same way.
3. **Reuse across models is on by default.** A lookup tries every candidate
   model (configured first, then the other step models, the defaults, and
   every model that has ever written to the cache). The first hit wins.
   Stores use the configured model. `--strict-model` restores per-model
   lookups. Without this, changing `DEEPSEEK_MODEL` or an agent label would
   re-buy every result, which is the cost this ADR is meant to remove.
4. **A skill drives the loop.** Exit 4 means "packets are pending". A chat
   reads the packets, dispatches one worker per packet on the packet's model,
   and reruns the same command until exit 0. The skill is
   `.agents/skills/pnp-agent-run/SKILL.md`; Claude Code reaches it through a
   thin `.claude/skills` pointer.
5. **Emit stays the unchanged deterministic pipeline.** The skill runs the
   final emit on a bundle branch (`ingest/s<NN>`) and a human reviews the PR.
   Agents never write `knowledge/` directly, and never write the registry.
6. **Validation is the existing contract.** `pnp agent status` validates
   each answer with the step's own pydantic model. A bad answer moves to
   `rejected/` with its error, and the packet is re-queued. The run does not
   trust the worker to be well behaved.

## Consequences

**Positive**

- The four LLM steps and dedup run on a subscription at $0 API cost, with the
  same prompts, models and validation as the API path.
- Mixing is free: one step can run on DeepSeek while the others run on Claude
  or Codex, and the cache serves whichever is available.
- Changing a model is no longer a budgeted rebuild by default
  (PIPELINE.md §6, consequence 3).
- Nothing new is trusted: a served answer goes through the same parse and
  validation as an API answer.

**Negative**

- **Temperature is not enforced.** The request records it; the worker may
  ignore it.
- **The model is not verified.** `meta.json` is a self-report, recorded and
  shown by `agent status`, not trusted. The strongest control is the subagent
  `model` parameter in Claude Code, which the skill uses. Codex has no
  equivalent, so it runs one headless process per packet with an explicit
  `-m`.
- **Transcripts go to another provider.** Player names and session dialogue
  reach Anthropic or OpenAI instead of DeepSeek. This is the same exposure
  class as the API path (a third party sees the transcript), and it is the
  human's choice of provider. The queue is gitignored for the same reason the
  cache is.
- **The exit-4 loop needs a chat.** A pure CLI cannot finish an agent run; it
  can only stop and resume. This is by design: agent mode is a chat feature.
- **`history.jsonl` records each pending stop as a failed run.** Until the
  loop completes, the run log shows a series of failures. The record is
  accurate (the run did not finish), but it reads as noise in the dashboard.
- **Usage is not counted.** Served completions carry no token usage, so cost
  reports show agent calls as a count, not tokens.
- **Shell writes bypass the guard.** The path rules see Edit and Write, not a
  shell redirect. The skill's worker prompt forbids other writes; review and
  the PR catch the rest (ADR-005, Consequences).

## Alternatives considered

- **A separate parallel pipeline for agents.** Rejected. It would duplicate
  the prompts, the validation and the cache logic, and the two copies would
  drift. The point of the handoff client is that there is one pipeline with
  one client swapped. "Which path produced a result must not matter" is only
  true while there is one path.
- **An MCP server exposing the queue as tools.** Rejected for v1. It adds a
  long-running process, a second transport and an auth surface, to save a
  file read and a file write per packet. The queue is files on purpose: it
  survives crashes, can be inspected with `ls`, and needs no server. Revisit
  if packet volume makes the file round trip the bottleneck, or if the host
  cannot read local files.
