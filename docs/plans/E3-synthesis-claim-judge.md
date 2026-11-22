# E3 — Synthesis faithfulness by two LLM judges

## Intent

B3 drew 60 sentences from the synthesized bundle, each with the scrubbed ±90 s transcript
window around its citation, and left them for a human to label (~2–3 h). None were labelled,
so synthesis truth is still unmeasured (QUALITY.md, "What this does not measure"). Wanted:
the cheapest credible measurement. The two E2 judges label all 60 claims (one call each);
a human labels 20 blind; the report gives the supported rate per labeller and agreement
as raw rate and Cohen's kappa, because `supported` dominates and inflates raw agreement.

Constraints: the B3 vocabulary and `claims.score` stay unchanged; B3's own ratchet keeps
skipping until ≥ 50 human labels exist; judge verdict files are committed (ids and
verdicts only), reasons and usage stay private. Per-model synthesis comparison is
deferred: it needs frozen synthesis packets from the D1 handoff queue and a mapping from
`[P-nn]` markers to windows, about a week of Pro quota for three models.

## Steps

1. `src/pnp_okf/claims.py`: `agreement(a, b) -> {n, agree, rate, kappa}`. Tests in
   `tests/test_claims.py`.
2. `bench_launch.py`: `PROMPTS["claims"]`, `judge_claims` (writes
   `<stem>.<judge>.json` beside the claim file, keyed by a hash over id, claim and window so
   human labelling does not stale it), `claims_report` (repo-relative paths only), CLI
   `judge-claims` and `claims-report`. Tests in `tests/test_bench_launch.py`.

**HUMAN RUN**:

1. `bench_launch.py judge-claims --claims tests/data/claims/2026-10-26-1234.yaml` (2 calls).
2. Before opening any judge file, label every third claim (c001, c004, …, c058) in the YAML
   `verdict` field. The file is sorted by type, so this spreads the 20 labels across types.
3. `bench_launch.py claims-report --claims tests/data/claims/2026-10-26-1234.yaml --out ../../docs/benchmarks/synthesis.md`;
   commit the report, the labels and both judge files.
4. Optional, 2 more calls: the same for the DeepSeek-Flash sample
   (`.flash-eval-pnp-knowledge/claims-sample.yaml`, private) as a second row.

## Done when

- [ ] `agreement`, `judge_claims` and `claims_report` tests pass.
- [ ] HUMAN: `docs/benchmarks/synthesis.md` shows judge↔judge and judge↔human (n = 20)
      agreement with kappa, committed with `2026-10-26-1234.{opus,sol}.json`.

    cd services/kb
    .venv/Scripts/python.exe -m pytest -q tests/test_claims.py tests/test_bench_launch.py
