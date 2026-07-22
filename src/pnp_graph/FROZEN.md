# Frozen

Per ADR-001 (`docs/architecture/ADR-001*`, 2026-07-22): the OKF bundle
(`knowledge/`, owned by `services/kb/`) is the system of record. This
Neo4j GraphRAG pipeline is an optional future *derived index* built only
from the bundle — no feature work planned unless ADR-001's revisit
trigger fires.

Still used read-only for gold-standard comparison via
`reports/load_report_graph.py` (loads report markdown into a separate
Neo4j container for reconciliation) — that's why this stays in place
rather than moving to an archive path, which would break its `sys.path`
wiring across `tests/`, `export_graph.py`, and `compare/run_both.py`
for no benefit.
