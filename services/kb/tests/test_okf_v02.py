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


# --- sources[] frontmatter (OKF v0.2 SPEC.md §5.1) --------------------------
#
# Deliberately lean (id/resource/last_modified only) and deliberately not the
# spec's `[^footnote]` syntax -- pnp-export-data/md2wiki.py's `_CITE_ID`
# parses exactly `P-\d+|S\d+-\d+-[A-Za-z]+`, so the marker stays the keyed
# `[P-08]` form cli.py's citation_labels/relabel_citations already produce.


def test_sources_id_matches_inline_citation_marker(tmp_path: Path):
    # The id in sources[] has to be the same token the body's inline marker
    # uses, or a reader following [P-08] into sources[] finds nothing.
    body = "# Überblick\n\nErwähnt in [P-08].\n\n# Belege\n\n[P-08] Session 2026-01-01 @ 00:01:00 (http://x)"
    emit_entity(tmp_path, _entity(), body, labels=["P-08"])
    doc = (tmp_path / "npcs" / "testo.md").read_text(encoding="utf-8")
    frontmatter, rendered_body = split_document(doc)
    marker = re.search(r"\[([^\]]+)\]", rendered_body).group(1)
    assert frontmatter["sources"][0]["id"] == marker
    assert re.match(r"^(P-\d+|S\d+-\d+-[A-Za-z]+)$", marker)


def test_sources_fall_back_to_positional_when_labels_is_none(tmp_path: Path):
    # citation_labels is all-or-nothing: ~122 concepts have at least one
    # mention URL missing from episodes.yaml and get None back, never a
    # partially-filled list. sources[] must fall back the same way, not call
    # episodes.id_for_url per mention to paper over the gap.
    fm = _frontmatter(tmp_path, labels=None)
    assert fm["sources"] == [
        {"id": "1", "resource": "http://x", "last_modified": "2026-01-01T00:00:00Z"}
    ]


def test_sources_last_modified_and_resource_from_mention(tmp_path: Path):
    fm = _frontmatter(tmp_path, labels=["P-08"])
    source = fm["sources"][0]
    assert source["resource"] == "http://x"
    assert source["last_modified"] == "2026-01-01T00:00:00Z"


def test_belege_backfill_uses_labels_so_body_and_sources_agree(tmp_path: Path):
    # Step 1 regression: cli.py relabels the body's inline numeric citation
    # markers to episode ids ("[3]" -> "[P-08]") *before* calling emit_entity.
    # But a model body that omits its own "# Belege" section gets one
    # backfilled from render_belege_section -- and until this fix, that
    # backfill was always the unlabelled "1. Session ..." form, so a body
    # marker like "[P-08]" cited against a list that never says "P-08"
    # anywhere. Zero occurrences in the current bundle, but it fired
    # historically (see test_bundle_invariants.py's
    # test_emit_entity_backfills_a_missing_belege_section).
    entity = _entity()
    body = "# Überblick\n\nErwähnt in [P-08].\n"  # no "# Belege" section
    emit_entity(tmp_path, entity, body, labels=["P-08"])
    doc = (tmp_path / "npcs" / "testo.md").read_text(encoding="utf-8")
    assert "[P-08] Session 2026-01-01 @ 00:01:00 (http://x)" in doc


def test_belege_citation_line_still_matches_ratchet_and_session_date(tmp_path: Path):
    # Two independent regexes must keep matching the labelled form:
    # test_bundle_invariants.py's citation-coverage ratchet, and
    # pnp-export-data/02_extract.py's `Session (\d{4}-\d{2}-\d{2})` extraction
    # that gates wiki page creation on MIN_SESSIONS.
    ratchet = re.compile(r"^(\[[^\]]+\]|\d+\.)\s*\[?Session\s", re.MULTILINE)
    count_sessions = re.compile(r"Session (\d{4}-\d{2}-\d{2})")
    emit_entity(tmp_path, _entity(), "# Überblick\n\nText.\n", labels=["P-08"])
    doc = (tmp_path / "npcs" / "testo.md").read_text(encoding="utf-8")
    assert ratchet.search(doc)
    assert count_sessions.search(doc).group(1) == "2026-01-01"
