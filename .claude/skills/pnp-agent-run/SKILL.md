---
name: pnp-agent-run
description: Run the pnp_okf pipeline's LLM steps (extract, deep and standard synthesis, state, dedup) on a Claude or Codex subscription instead of the DeepSeek API, by answering each request packet with a worker agent. Use when the user asks for agent mode, to run pnp "without the API", "on my subscription", on Claude or Codex, or to answer pnp agent packets. Triggers: pnp-agent-run, agent mode, agent packets, pnp agent status, --no-api, agent:claude, agent:codex.
---

Read and follow `.agents/skills/pnp-agent-run/SKILL.md` (canonical, shared with Codex). It holds the inputs, preflight, run loop, worker prompt and rules; do not work from this file alone.
