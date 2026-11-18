"""docs/QUALITY.md quotes every ratchet's number; this keeps those quotes true.

The ratchet tests themselves skip in CI (no bundle), and their baselines move with every
regeneration, so the doc drifted: the churn row said 23 two moves after the constant became
14, and every file:line reference had gone stale. This test needs no bundle: it reads each
`file::CONSTANT` source cell, parses that test file, and compares the number.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
DOC = TESTS.parents[2] / "docs" / "QUALITY.md"
ROW = re.compile(r"^\|[^|\n]+\|\s*([0-9][0-9.]*)[^|\n]*\|\s*`services/kb/tests/(\w+\.py)::([A-Z][A-Z0-9_]+)`", re.M)


def _constants(path: Path) -> dict[str, object]:
    out: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        target = node.targets[0] if isinstance(node, ast.Assign) else getattr(node, "target", None)
        if isinstance(target, ast.Name) and isinstance(getattr(node, "value", None), ast.Constant):
            out[target.id] = node.value.value
    return out


def test_every_constant_row_quotes_the_current_value():
    rows = ROW.findall(DOC.read_text(encoding="utf-8"))
    assert len(rows) >= 15, "QUALITY.md lost its file::CONSTANT source cells"
    for value, file, name in rows:
        constants = _constants(TESTS / file)
        assert name in constants, f"{file}::{name} no longer exists"
        assert float(value) == constants[name], f"QUALITY.md: {value} for {file}::{name}; test: {constants[name]}"


def test_no_line_number_references():
    # Line numbers drift with every edit above them; constant and test names do not.
    assert not re.search(r"services/kb/tests/\w+\.py:\d", DOC.read_text(encoding="utf-8"))
