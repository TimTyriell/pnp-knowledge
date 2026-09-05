# Incident: the 2026-08 mass rename

**Status:** Resolved, guards in place
**Referenced from:** `cli.py` (`--reextract` warning), `emit.py:check_rename_safety`,
`resolve.py:write_registry` — three code sites point here for the background.

## Summary

Two failures, two weeks apart, with the same outcome: a routine `pnp run`
silently discarded most of the campaign's accumulated identity work and began
regenerating it from scratch. Neither run crashed. Both looked like normal runs
while they were destroying the thing they were maintaining.

The first was caused by the LLM; the second by a path. The second is the more
interesting one, because it defeated the guard written for the first.

## Why this class of failure is dangerous here

Concept ids are *derived* from extracted entity names. That is a deliberate
design choice — it keeps ids readable and avoids a separate id allocator — but
it couples identity to model output. Anything that changes what the model calls
a thing changes where that thing lives:

```
LLM output "Die Hexe vom Turm" -> slug -> npcs/die_hexe_vom_turm
LLM output "Hexe"              -> slug -> npcs/hexe
```

Same entity, different file. Nothing is wrong at any single step; the identity
simply moves. At scale this is indistinguishable from "most of the campaign was
deleted and replaced with strangers."

## Incident 1 — LLM resample reworded the world

**Trigger.** A re-extraction (cache bypassed) resampled the model. The model
reworded a large fraction of entity names — not incorrectly, just differently.
Every reworded name produced a new derived concept id.

**Effect.** The bundle was overwritten with the renamed content. The old concept
files remained as orphans: stale bodies, stale links, still served by the
read-only API and still exported to the wiki as if current.

**Why the existing guard missed it.** `prune_orphans` did have a ratio guard.
But it operates on *the bundle*, and by the time it runs the bundle has already
been overwritten with the renamed content. It was inspecting the aftermath.

## Incident 2 — a wrong path blinded every guard (2026-08-30)

**Trigger.** One wrong `--bundle` argument. A stale `PNP_BUNDLE_DIR` does the
same thing.

**Why that is not a small mistake.** Every knowledge path is derived from the
bundle directory. One wrong value relocates the registry, the rules file, and
`sources/` *together*, consistently. Nothing downstream can distinguish that
from a legitimate first run: a missing registry reads as `{}`, so every
`merge` / `never_merge` / `split` / `canonical_name` / `alias_block` /
`spelling` / `important` rule and every GM ruling simply isn't there. The run
proceeded to regenerate the entire campaign from scratch, cheerfully.

**Why the rename guard did not fire.** Both the rename and prune guards work by
diffing against the previous registry. In this scenario the previous registry
was *also* empty — they were comparing nothing to nothing and finding no
discrepancy. **A guard that diffs against prior state is blind to a failure that
erases the prior state.** That is the transferable lesson from this incident.

**Cost.** A full run plus 32 unintended LLM calls before anyone noticed.

## Remediation

Five changes, deliberately at different stages, because the two incidents proved
that a single checkpoint is not enough.

| Guard | Where | Stage | Catches | Blind to |
|---|---|---|---|---|
| `require_rules()` | `resolve.py` | before resolution | wrong bundle path / missing rules | a genuinely rules-free campaign (documented escape) |
| `check_rename_safety()` | `emit.py:412` | **before any write** | mass rename via resample | first-ever run, bundles under 20 concepts |
| `prune_orphans()` ratio guard | `emit.py:459` | at delete time | over-broad deletion | anything already written |
| `retired:` ledger | `resolve.py:write_registry` | every run | loss of alias memory | — |
| `rules_doctor.py` | standalone | post-incident triage | rules orphaned by a rename | — |

Three of these are worth explaining.

**`require_rules()` uses presence, not comparison.** Because the diff guards were
blinded by empty prior state, the fix could not be another diff. The rules file
is the one artefact that is always present for a real campaign and is never
written by the tool, so *its absence is the signal*. This is the direct answer to
Incident 2's root cause.

**`check_rename_safety()` moved the check one stage earlier.** Same shape as the
prune guard, but it runs against the freshly resolved entity set before a single
file is written — the point at which the damage is still fully preventable rather
than merely detectable. It refuses when more than 10% of previously known concept
ids are absent, skips below a 20-concept floor and on first run, and offers
`--allow-rename` for deliberate cleanups.

**The `retired:` ledger closed the memory leak.** Previously a concept absent from
a run simply vanished from the registry, which erased the alias memory that could
have caught the *next* rename. Now it moves to `retired:` keeping its id, type,
canonical name and aliases, so a later reword can fuzzy-reanchor to it
(`_reanchor_to_retired`). Retirement stopped being amnesia.

### The related structural fix

`entity_registry.yaml` is *generated* — rewritten through a YAML dump on every
run, which strips every comment. Keeping hand-authored rules there meant the tool
erased the reasons for its own rules on each run. Rules therefore moved to
`entity_rules.yaml`, which nothing ever writes.

That split makes an existing invariant real rather than merely intended: **rules
are input, the inventory is output.** The original layout allowed a generated file
to hold hand-authored knowledge, and the erasure followed from that, not from a
coding error.

## Residual damage

A rename orphans the rules that referenced the old ids. `rules_doctor.py`
classifies each dead rule as *inert* (its source text is no longer extracted
anywhere, so the rule can never fire again — safe to delete) or *needs a decision*
(the source text is still live, and the correct successor concept is not
determinable from text alone, so a human must resolve it).

The surviving count is tracked as a quality ratchet — `DEAD_RULES_BASELINE` in
`services/kb/tests/test_rules_applied.py`. See [QUALITY.md](../QUALITY.md). The
incident is therefore not merely documented; its residue is measured, and is not
allowed to grow.

## Recurrence: 2026-09, prompt v6

The `PROMPT_VERSION` bump from `"5"` to `"6"` invalidated every cached LLM output
at once — both caches key on it:

```
key = sha256(PROMPT_VERSION + model + session_id + dialogue)
```

A full re-extraction followed, the model resampled, and names were reworded
exactly as in Incident 1. This time:

```
ERROR pnp_okf.emit: [resolve] refusing to proceed: 432/868 previously known
concept(s) (>10%) are absent from this run's resolved entities
```

432 of 868 concepts — half the bundle — and **nothing was written.** The guard did
its job on the failure mode it was written for, reached by a trigger nobody
anticipated when writing it. `rules_doctor.py` applied unchanged.

Migration handling: [MIGRATION-prompt-v6.md](MIGRATION-prompt-v6.md).

## Lessons

1. **A guard that diffs against prior state is blind to failures that erase prior
   state.** Pair every comparison check with at least one presence check.
2. **Guard placement is a design decision, not a detail.** The prune guard and the
   rename guard implement nearly identical logic; only the one that runs before
   writes can actually prevent damage.
3. **Deriving identity from model output couples the data model to model
   nondeterminism.** That coupling is still worth its benefits here, but it is now
   an explicit, guarded, documented tradeoff rather than an unexamined convenience.
4. **A cache key bump is a re-extraction.** Anything keyed on `PROMPT_VERSION`
   should be treated as a migration with a rollback plan, not a version bump.
5. **Cheerful success is the worst failure mode.** Both incidents exited zero. The
   guards' entire value is converting silent corruption into a loud refusal.
