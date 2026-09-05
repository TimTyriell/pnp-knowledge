"""Turn "no bundle checked out" skips into a hard failure when PNP_REQUIRE_BUNDLE=1.

Nine test files guard themselves with
``pytest.mark.skipif(not <bundle path>.exists(), reason="no bundle checked out")``.
Locally that is right: no bundle, no bundle tests.

In CI it is a trap. On a shallow or partial checkout the entire quality suite
passes by not running, and a green badge that means "the tests vanished" is
worse than a red one. Set PNP_REQUIRE_BUNDLE=1 in CI so a missing bundle is an
error instead.

This keys off the skip *reason* rather than re-deriving the bundle path, so it
stays correct however each file spells its own guard (registry file, conflicts
dir, rules file, ...) and needs no edits to the ratchet tests themselves.
"""

from __future__ import annotations

import os

import pytest

SKIP_REASON = "no bundle checked out"


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PNP_REQUIRE_BUNDLE") != "1":
        return
    absent = sorted(
        {
            item.nodeid.split("::")[0]
            for item in items
            for mark in item.iter_markers("skipif")
            if mark.kwargs.get("reason") == SKIP_REASON and any(mark.args)
        }
    )
    if absent:
        raise pytest.UsageError(
            f"PNP_REQUIRE_BUNDLE=1 but the knowledge bundle is missing, so "
            f"{len(absent)} test file(s) would have silently skipped: "
            + ", ".join(absent)
            + ". Check out the full repo (no shallow/partial clone) or unset "
            "PNP_REQUIRE_BUNDLE."
        )
