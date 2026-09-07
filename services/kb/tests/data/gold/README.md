# Hand-labelled ground truth

Empty on purpose. Nothing here can be generated — the whole point is that a
human decides what the model *should* have extracted.

```bash
cd services/kb
python make_gold_stub.py 2025-03-26 > tests/data/gold/2025-03-26.yaml
```

Then correct the stub: mark hallucinated entities `wrong`, fix bad names with
`rename` + `should_be`, and add what the model missed as `missed`. Three to
five sessions is enough to clear the ~30-example floor below which a
precision/recall number means nothing.

`tests/test_extraction_quality.py` skips while this directory is empty, and
says so in its skip reason — a missing measurement, not a passing test.
