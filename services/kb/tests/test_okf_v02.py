"""OKF v0.2 trust tiers: `generated` (spec §7 actor convention) and `verified`
(spec §5.3 human tier) frontmatter written by ``emit_entity``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
from pnp_okf.emit import emit_entity
from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.okf import split_document

# knowledge-catalog is a sibling repo (vendored OKF spec + reference tooling),
# not a dependency of this one -- see CLAUDE.md's repo table. It may not be
# checked out on a partial clone.
_REFERENCE_DOCUMENT = (
    Path(__file__).resolve().parents[4]
    / "knowledge-catalog" / "okf" / "src" / "reference_agent" / "bundle" / "document.py"
)


def _entity() -> CanonicalEntity:
    return CanonicalEntity(
        concept_id="npcs/testo",
        type=EntityType.NPC,
        canonical_name="Testo",
        mentions=[
            MentionRef(
                session_id="s1", date="2026-01-01", url="http://x",
                citation_ts="00:01:00", note="Ein Testling.",
            )
        ],
    )


def _frontmatter(tmp_path: Path, **emit_kwargs) -> dict:
    emit_entity(
        tmp_path, _entity(), "# Überblick\n\nText.\n\n# Belege\n\n[1] x",
        **emit_kwargs,
    )
    doc = (tmp_path / "npcs" / "testo.md").read_text(encoding="utf-8")
    frontmatter, _body = split_document(doc)
    return frontmatter


def test_generated_at_matches_timestamp(tmp_path: Path):
    fm = _frontmatter(tmp_path)
    assert fm["generated"]["at"] == fm["timestamp"]


def test_generated_by_matches_actor_convention(tmp_path: Path):
    # SPEC.md §7: "<producer>/<version>".
    fm = _frontmatter(tmp_path)
    assert re.match(r"^\S+/\S+$", fm["generated"]["by"])


def test_verified_absent_by_default(tmp_path: Path):
    fm = _frontmatter(tmp_path)
    assert "verified" not in fm


def test_verified_present_when_flagged(tmp_path: Path):
    fm = _frontmatter(tmp_path, verified=True)
    assert fm["verified"] == {"by": "human:gm"}


@pytest.mark.skipif(
    not _REFERENCE_DOCUMENT.exists(), reason="knowledge-catalog not checked out"
)
def test_trust_tier_matches_reference_implementation(tmp_path: Path):
    # The vendored reference implementation is the spec's own consumer, so
    # it's the best oracle for what our frontmatter actually means to a real
    # OKF reader. Loaded by path (not a sys.path entry) since it's a sibling
    # repo, not an installed dependency.
    spec = importlib.util.spec_from_file_location(
        "_okf_reference_document", _REFERENCE_DOCUMENT
    )
    module = importlib.util.module_from_spec(spec)
    # document.py uses `from __future__ import annotations` + @dataclass;
    # dataclasses resolves string annotations via sys.modules[cls.__module__],
    # so the module must be registered there before exec_module runs it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.trust_tier(_frontmatter(tmp_path)) == "unverified"
    assert module.trust_tier(_frontmatter(tmp_path, verified=True)) == "human-reviewed"
