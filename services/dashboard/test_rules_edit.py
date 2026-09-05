"""Plain-assert tests for rules_edit.py — pytest-collectible, no fixtures/mocks.

Fixture reproduces the real entity_rules.yaml's shape at small scale: a
merge: block with an interleaved GM-ruling comment and a trailing comment
that belongs to the *next* block, a canonical_name: block, and a comment
right before a later top-level key.
"""

from __future__ import annotations

import yaml
from rules_edit import EditConflict, apply_edits, block_bounds, validate

FIXTURE = """\
merge:
  cookie: characters/cookie
  # GM ruling: Lenra is the Hag.
  hack: npcs/lenra
  sumpfhexe: npcs/lenra
  # trailing note about the next section
canonical_name:
  npcs/lenra: Landra, die Hag
# trailing comment before important
important:
- npcs/lenra
"""


def _rules() -> dict:
    return yaml.safe_load(FIXTURE)


def _sources() -> dict:
    return {
        "npcs/lenra": [
            ("Landra, die Hag", "canonical"),
            ("hack", "merge"),
            ("sumpfhexe", "merge"),
        ]
    }


def test_rename_replaces_in_place():
    new_text, warnings = apply_edits(
        FIXTURE, [{"op": "rename", "concept_id": "npcs/lenra", "name": "Die Hag Lenra"}], _rules(), _sources()
    )
    assert "npcs/lenra: Die Hag Lenra" in new_text
    assert "npcs/lenra: Landra, die Hag" not in new_text
    # Everything else, including the trailing comment before `important:`,
    # survives untouched.
    assert "# trailing comment before important" in new_text
    assert new_text.count("\n") == FIXTURE.count("\n")
    assert not warnings


def test_add_alias_appends_before_trailing_comment_not_after():
    new_text, _ = apply_edits(
        FIXTURE, [{"op": "add_alias", "concept_id": "npcs/lenra", "alias": "Moorhexe"}], _rules(), _sources()
    )
    lines = new_text.split("\n")
    new_idx = lines.index("  moorhexe: npcs/lenra")
    comment_idx = lines.index("  # trailing note about the next section")
    assert new_idx < comment_idx


def test_delete_alias_removes_exactly_one_line_and_comment_survives():
    new_text, warnings = apply_edits(
        FIXTURE,
        [{"op": "delete_alias", "concept_id": "npcs/lenra", "alias": "hack", "unfold_ack": True}],
        _rules(),
        _sources(),
    )
    assert "  hack: npcs/lenra" not in new_text
    assert "  sumpfhexe: npcs/lenra" in new_text
    # The GM ruling comment above "hack" is not deleted along with it.
    assert "# GM ruling: Lenra is the Hag." in new_text
    assert warnings


def test_delete_alias_without_ack_hides_only_and_keeps_merge_rule():
    # Safe default: without explicit unfold_ack, a merge-sourced alias is
    # only hidden (alias_block), the merge: rule and folding are untouched.
    new_text, warnings = apply_edits(
        FIXTURE, [{"op": "delete_alias", "concept_id": "npcs/lenra", "alias": "hack"}], _rules(), _sources()
    )
    assert "  hack: npcs/lenra" in new_text
    assert "alias_block:" in new_text
    assert "- hack" in new_text
    assert not warnings


def test_reapplying_same_edit_is_idempotent():
    edits = [{"op": "rename", "concept_id": "npcs/lenra", "name": "Die Hag Lenra"}]
    once, _ = apply_edits(FIXTURE, edits, _rules(), _sources())
    twice, _ = apply_edits(once, edits, _rules(), _sources())
    assert once == twice


def test_conflicting_add_alias_raises():
    try:
        # "cookie" is already a merge key for a different concept.
        apply_edits(
            FIXTURE, [{"op": "add_alias", "concept_id": "npcs/lenra", "alias": "Cookie"}], _rules(), _sources()
        )
        raise AssertionError("expected EditConflict")
    except EditConflict:
        pass


def test_result_is_valid_yaml_and_passes_validate():
    new_text, _ = apply_edits(
        FIXTURE, [{"op": "add_alias", "concept_id": "npcs/lenra", "alias": "Moorhexe"}], _rules(), _sources()
    )
    data = yaml.safe_load(new_text)
    assert data["merge"]["moorhexe"] == "npcs/lenra"
    validate(FIXTURE, new_text)  # must not raise


def test_block_bounds_finds_merge_block():
    lines = FIXTURE.split("\n")
    start, end = block_bounds(lines, "merge")
    assert lines[start] == "merge:"
    assert lines[end] == "canonical_name:"


def test_unpin_removes_the_canonical_name_line():
    new_text, _ = apply_edits(FIXTURE, [{"op": "unpin", "concept_id": "npcs/lenra"}], _rules(), _sources())
    assert "npcs/lenra: Landra, die Hag" not in new_text
    # The now-empty canonical_name: block itself is left alone, not deleted.
    assert "canonical_name:" in new_text


def test_set_important_false_adds_to_unimportant_not_just_removes():
    # npcs/lenra starts important: true. Turning it off must not just delete
    # the important: entry — resolve.py's ratchet means a past registry run
    # can re-flag it regardless, so unimportant: has to win explicitly.
    new_text, _ = apply_edits(
        FIXTURE, [{"op": "set_important", "concept_id": "npcs/lenra", "important": False}], _rules(), _sources()
    )
    data = yaml.safe_load(new_text)
    assert "npcs/lenra" not in (data.get("important") or [])
    assert "npcs/lenra" in data["unimportant"]


def test_set_important_true_undoes_a_prior_suppression():
    suppressed = FIXTURE + "unimportant:\n- npcs/lenra\n"
    new_text, _ = apply_edits(
        suppressed, [{"op": "set_important", "concept_id": "npcs/lenra", "important": True}], yaml.safe_load(suppressed), _sources()
    )
    data = yaml.safe_load(new_text)
    assert "npcs/lenra" in data["important"]
    assert "npcs/lenra" not in (data.get("unimportant") or [])


def test_set_important_true_on_fresh_entity_is_idempotent():
    edits = [{"op": "set_important", "concept_id": "characters/cookie", "important": True}]
    once, _ = apply_edits(FIXTURE, edits, _rules(), _sources())
    twice, _ = apply_edits(once, edits, _rules(), _sources())
    assert once == twice
    assert "characters/cookie" in yaml.safe_load(once)["important"]


if __name__ == "__main__":
    import sys

    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
    sys.exit(1 if failures else 0)
