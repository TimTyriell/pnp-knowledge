"""Turn "no bundle checked out" skips into a hard failure when PNP_REQUIRE_BUNDLE=1.

Nine test files guard themselves with
``pytest.mark.skipif(not <bundle path>.exists(), reason="no bundle checked out")``.
Locally that is right: no bundle, no bundle tests.

Where the bundle should be there, it is a trap: a missing or half-cloned
knowledge/ makes the entire quality suite pass by not running. Set
PNP_REQUIRE_BUNDLE=1 on a machine with the bundle so its absence is an error.
CI does not set it: the bundle is a private repo and CI has none.

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
