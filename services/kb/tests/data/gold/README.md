# Hand-labelled ground truth

Three sessions, 71 names. Nothing here can be generated — the whole point is
that a human decides what the model *should* have extracted. Caveat recorded in
`tests/test_extraction_quality.py`: these labels were AI-drafted from the same
extraction they score and then corrected by hand, so they guard against
regression, not for truth. The model comparison uses a separate, human-approved
gold under the private benchmark root (`docs/EXTRACTION-BENCHMARK.md`).

```bash
cd services/kb
python make_gold_stub.py 2025-03-26 > tests/data/gold/2025-03-26.yaml
```

Then correct the stub: mark hallucinated entities `wrong`, fix bad names with
`rename` + `should_be`, and add what the model missed as `missed`. Three to
five sessions is enough to clear the ~30-example floor below which a
precision/recall number means nothing.

`tests/test_extraction_quality.py` skips when this directory is empty or the
transcript corpus is missing (CI), and says so in its skip reason — a missing
measurement, not a passing test.
