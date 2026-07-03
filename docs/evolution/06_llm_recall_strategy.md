# 06 — LLM Recall Strategy on a local 14B (WP7)

The "more knowledge" dial lives here. `qwen3:14b` at `NUM_CTX=8192` is capable if driven well and kept honest by the downstream resolution/validation layer.

## Principle: extract generously, resolve deterministically

Correctness is **not** the LLM's job — it's enforced downstream by `resolve.py` (canonical ids), vocab validation (`04`), endpoint validation (`03`), and SRD linking (`05`). That separation lets you push extraction toward Graph-1-level recall without inheriting Graph 1's mess. Do **not** prune inside the prompt.

## Techniques

1. **Two-role extraction, not one mega-prompt.** Per chunk, run two smaller structured-output calls:
   - **(a) entity + rules pass** — characters, NPCs, locations, items, factions, and SRD references (classes, cards, ancestries).
   - **(b) event pass** — events, rolls, decisions, and the causal edges among them, referencing only entities named in pass (a).
   Two small schemas keep a 14B reliable and raise recall vs. one overloaded call. Cost is 2 calls/chunk — still **one model in VRAM**, within the 12 GB budget.

2. **Optional Graph 1 candidate feed.** You already run `../ai-knowledge-graph` in `compare/`. Reuse its raw triples as a *candidate generator*: every triple passes through resolution + vocab-mapping + endpoint validation before anything lands. **Raw output never writes directly.** This buys recall cheaply without the sprawl.

3. **SRD gazetteer as a recall multiplier.** Feed the SRD class/card/ancestry names (from `srd.py`) into the entity-pass prompt as a controlled vocabulary so the model tags them consistently instead of paraphrasing — improves both recall and linkability.

4. **Retry/repair (PLAN.md phase 5).** On structured-output parse failure: one retry with a "return valid JSON only" reminder; second failure → dump to `state/failures/<sid>/<chunk>.json` and continue. Partial session > no session.

5. **Determinism/idempotency:** keep `temperature=0`, `reasoning=False` (already set), and the pinned `NUM_CTX=8192` (its comment documents the runaway-generation lesson — don't remove it).

6. **Language split:** content stays **German** (PLAN.md decision); relationship **types** and **confidence** values are English tokens. Enforce that split so the vocabulary doesn't fork by language (`hoch` vs `high` was a real Graph 2/3 mismatch).

## Acceptance (WP7)

Per-session fact count materially exceeds Graph 3's 27 (target: richer than the hand-authored report, leaner than Graph 1's 670) **while all QA checks in `07` stay green** — i.e. more knowledge, still clean.

## Cost note

Two passes/chunk roughly doubles LLM time per session. On the target hardware that's acceptable for a batch/offline ingest. If it becomes a bottleneck, the entity pass can be cached per chunk (it changes less across re-runs than the event pass).
