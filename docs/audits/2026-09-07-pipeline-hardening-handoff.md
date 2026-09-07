# Handoff — pipeline hardening branch, for review

**Branch:** `chore/docs-ci-and-instrumentation`
**Commits:** `2729057` … `a4d8d7a` (10)
**Tests:** 244 → 266 passed, 1 skipped, 1 xfailed
**Spend:** $0. No `pnp run`, no LLM call.

This is *what and why*, not how. A reviewer should read it, then attack the
claims in §7 — those are the ones I am least sure of.

---

## 1. What prompted this

Three runs on 2026-09-05 failed in three different ways, and the third one was
only noticed by a human reading link targets days later:

| | |
|---|---|
| 08:49 | refused: 432 of 868 concept ids had moved after a re-extraction |
| 09:55 | succeeded, ~$6.45, the prompt-v6 rebuild |
| ~15:37 | **killed mid-synthesis. No run record. 54 dangling links left on disk.** |
| 13:36 | died on a connection error |
| 16:20 | warm re-emit, 18 calls, ~$0.05 |

The user asked for an analysis of what went wrong and a plan to stop it
recurring, with three constraints: tests first, no bloat, and get the cost
down — "the $8 mark has to be avoided".

## 2. What the analysis concluded

Five distinct failure classes, and one economic fact that reframes all of them:

**A rebuild costs ~130× a warm re-emit.** The pipeline is cheap to run and
expensive to *invalidate*. The $8 was never the price of running it; it was the
price of a one-character change to `PROMPT_VERSION`. So cost control belongs at
the cache, not at the model.

I had each failure class externally reviewed against current practice
(GitHub, engineering blogs, vendor docs, papers). Verdicts: **1 confirm, 4
steer.** The research changed the plan in four places, and those changes are
the most interesting thing here:

| Claim I made | What review found |
|---|---|
| Opaque stable ids are too expensive; defer | The systems that actually solve this (Graphiti/Zep, Cognee) all mint one; the ones that derive ids from names list disambiguation as unsolved. The cheap hybrid is *smaller* than the work I'd already planned |
| Fix the fuzzy link resolver | Delete it from that path instead — silently resolving a broken link to the nearest match is an anti-pattern, and fail-the-build is the tooling default (Docusaurus throws by default) |
| Reorder writes; staging is too big a diff | Reorder is right, but staging is not merely expensive — **no OS can atomically replace a non-empty directory** |
| Ratchets are our quality gate | Ratchets gate *defect classes*, never correctness. No output-quality eval existed at all — the loudest gap |

Three independent reviewers ranked the same change #1: **wire the validator
into the exit code.** It was buried mid-plan; it became Phase 0.

## 3. What changed, and why

### The validator gated nothing
It ran on every run and its result was discarded. `broken_links` was asserted
by zero tests. Now `pnp run` exits 3 on structural breakage.

Deliberately narrow: gating on the full `report.ok` would fail *every* run,
because a healthy bundle always carries some fuzzy findings (10 suspected
person duplicates today). A gate that always fails gets switched off within a
week, so `integrity_ok` covers only breakage — broken links, dangling links,
missing types, duplicate ids.

### A killed run left no trace
Run status was written only at the end, so a hard kill wrote nothing. Now a
marker is written before the first bundle write and cleared on completion; the
next run finds it and records the death. Chose a separate file over a status
field because `last_run.json` is a documented cross-repo contract.

### Session links discarded the resolver's work
Session pages built links by re-slugifying the raw LLM name, throwing away
every split/merge/ignore decision, with a fuzzy resolver rescuing the wreckage.
Measured over 1846 mentions: 320 landed correctly *only* via that rescue, **7
pointed at the wrong entity**, 4 were dropped. Now 100% exact.

The 7 matter more than the number suggests: a link with the right label
pointing at the wrong entity is invisible to a reader and to every test.

### The crash window
Session files were written *before* the 25–95 minute synthesis phase that
produces the pages they link to. Now nothing is written until synthesis
completes, and each write follows what it references: entities → sessions →
registry. The registry moved from first to nearly last for the same reason.

**Residual risk, stated plainly:** writes are still bare `write_text`. A kill
inside the now-seconds-long write phase reproduces the same breakage, just
rarely. That is the honest cost of shrinking the window rather than protecting
it, and directory-level protection is not available (see §2).

### Identity
Concept ids are `slugify(whatever the model typed)`, so re-extraction renames
things and detaches rules keyed on ids. Closed the reachable modes: reanchor
against *live* aliases (previously only retired ones), incumbent ids win fuzzy
folds, token-order-insensitive matching, guard tightened 10% → 2%, and a churn
ratchet.

**This does not fix the root cause** and ADR-004 says so explicitly. It is an
admission, with four triggers that should reverse the decision.

### Cost
- Cache paths are content-addressed, so an experiment is now revertible for $0 instead of $6.50. **The existing cache was migrated and verified** — 66/66 sessions confirmed still hitting before the originals were deleted.
- The structured-outputs probe was uploading a full transcript per worker thread to learn one boolean. Now serialised only while the capability is unknown.
- Probe tokens bypassed the ledger entirely, so every cost ever recorded was an undercount in the flattering direction.
- `pnp run --estimate` prints the bill before you pay it.

### Extraction quality
Nothing measured whether the extraction was *correct* — only the shape of the
output. Built the harness; it skips until hand-labelled sessions exist and says
so rather than passing silently.

## 4. Decisions taken, with reasons

| Decision | Why |
|---|---|
| **Not** switching extraction to a cheaper model | Measured saving is ~15% of a rebuild, not the 3× the headline suggests — deep-tier synthesis *completion* tokens dominate. Against that: small models don't omit entity names, they **invent** them, at 1–2 orders of magnitude higher false-discovery rate. Wrong trade while identity is still fragile. The knob exists (`DEEPSEEK_EXTRACT_MODEL`); the default is unchanged |
| **Not** converting allowlist ratchets to `{id: reason}` dicts | Review flagged frictionless-append allowlists as the broken form — but these already carry per-entry justifications as comments. Machinery to enforce a convention already followed |
| **Not** preserving `last_run.json` across failures | Nothing was lost; `history.jsonl` has every run. The real gap was the *absence* of a record, fixed differently |
| **Not** deleting `ConceptIndex.resolve` | Session bullets no longer need it, but prose autolinking genuinely does — "Vasul" in German prose must still reach `deities/vharzul` |
| **Not** adopting DeepEval / Great Expectations / LiteLLM | At this scale each replaces a few lines with a service to operate |

## 5. What is left

- **Phase 4 needs human labels.** Three stubs are generated (70 entities, ~40 min). An LLM grading its own extraction measures nothing, which is why this stops here.
- **Phase 6 (cheaper extraction) is closed for now** by the decision above.
- Per-file `os.replace` in `write_if_changed` remains the named upgrade for the residual crash risk.

## 6. How to verify without spending anything

```bash
cd services/kb
.venv/Scripts/python.exe -m pytest -q                    # 266 passed, 1 skipped
.venv/Scripts/python.exe -m pnp_okf.cli validate --bundle ../../knowledge/bundle/splitter_des_ewigen
.venv/Scripts/python.exe -m pnp_okf.cli run --estimate --transcripts ../../../pnp-crawl/transcripts_final --bundle ../../knowledge/bundle/splitter_des_ewigen
```

Current state: 6382 links, 0 broken, 0 dangling; 66 + 241 cache entries warm;
estimate reports the run is free.

## 7. Attack these — the claims I am least sure of

1. **The churn baseline of 35 is not churn.** I claim it is the registry lagging `entity_rules.yaml` by one run, evidenced by `items/notiz_von_tyrex` (a Whisper mishearing) where a fresh resolve now yields `items/notiz_von_tyrael`. If that reading is wrong, the baseline is meaningless. It should drop toward 0 after the next real run — **if it doesn't, I was wrong.**
2. **The live-alias reanchor did not move the metric it was built for** (35 before, 35 after). I argue it prevents *future* churn that these cached extractions cannot exercise. That is unfalsifiable until a real re-extraction happens. A reviewer could reasonably call it speculative.
3. **The cache migration touched ~$6.50 of paid-for output** and is not in git (`.cache/` is ignored). I verified 66/66 hits before deleting the originals, but there is no undo. Worth independently re-verifying.
4. **`integrity_ok` is a judgement call** about which failure classes should block a run. I excluded the fuzzy heuristics deliberately; someone could argue duplicate ids belong in the advisory set, or that cross-type slugs belong in the blocking one.
5. **The registry write moved to near-last** on my reading that `load_spellings` is order-independent because `spelling:` lives only in `entity_rules.yaml`. I verified the registry carries only `entities` and `retired`. If some other consumer reads the registry mid-run, this is wrong.
6. **Two errors were found in my own documentation during this work** — I attributed `dropped_links: 137` to session links when it counts entity-body prose, and I told a subagent to move `emit_sessions` past the synthesis join when it needed to go past the entity-emit loop. Both were caught by measurement and by a test respectively. Assume there are more.
