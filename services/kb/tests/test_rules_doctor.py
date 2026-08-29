"""Unit test for rules_doctor's inert-vs-needs-decision classifier, over a
small fixture registry/rules/bundle instead of the real (large) knowledge
tree — see test_rules_applied.py for the checks against the real bundle.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rules_doctor import classify, session_names  # noqa: E402


def _write(path: Path, doc: dict) -> None:
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_classifies_inert_vs_needs_decision(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "npcs").mkdir(parents=True)
    (bundle / "npcs" / "lord_kalidarn_von_willau.md").write_text("live", encoding="utf-8")

    registry = tmp_path / "entity_registry.yaml"
    _write(registry, {"entities": [{
        "concept_id": "npcs/lord_kalidarn_von_willau",
        "type": "NPC",
        "canonical_name": "Lord Kalidarn von Willau",
        "aliases": ["Lord von Willauch"],
    }]})

    rules = tmp_path / "entity_rules.yaml"
    _write(rules, {
        # source name still extracted (as an alias of the live concept) ->
        # needs a decision, not inert, even though its recorded target died.
        "merge": {"lord von willauch": "npcs/lord_kalidarn_von_willauch"},
        # source name extracted nowhere any more -> inert.
        "canonical_name": {"npcs/some_gone_concept": "A Name Nobody Says Any More"},
    })

    result = classify(registry_path=registry, rules_path=rules, bundle_dir=bundle,
                       cache_dir=tmp_path / "no-cache")

    assert result["merge"]["live"] == {"lord von willauch": "npcs/lord_kalidarn_von_willauch"}
    assert result["merge"]["inert"] == {}
    assert "npcs/some_gone_concept" in result["canonical_name"]["inert"]
    assert result["canonical_name"]["successors"] == {}


def test_canonical_name_successor_is_found_by_pinned_display_name(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "npcs").mkdir(parents=True)
    (bundle / "npcs" / "harald_neu.md").write_text("live", encoding="utf-8")

    registry = tmp_path / "entity_registry.yaml"
    _write(registry, {"entities": [{
        "concept_id": "npcs/harald_neu",
        "type": "NPC",
        "canonical_name": "Freibeuter Harald",
        "aliases": [],
    }]})
    rules = tmp_path / "entity_rules.yaml"
    _write(rules, {"canonical_name": {"npcs/harald_alt": "Freibeuter Harald"}})

    result = classify(registry_path=registry, rules_path=rules, bundle_dir=bundle,
                       cache_dir=tmp_path / "no-cache")
    assert result["canonical_name"]["successors"] == {"npcs/harald_alt": "npcs/harald_neu"}


def test_never_merge_and_important_are_always_needs_decision(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "npcs").mkdir(parents=True)
    (bundle / "npcs" / "a.md").write_text("live", encoding="utf-8")

    registry = tmp_path / "entity_registry.yaml"
    _write(registry, {"entities": [{"concept_id": "npcs/a", "type": "NPC", "canonical_name": "A"}]})
    rules = tmp_path / "entity_rules.yaml"
    _write(rules, {
        "never_merge": [["npcs/a", "npcs/gone"]],
        "important": ["deities/gone_deity"],
    })

    result = classify(registry_path=registry, rules_path=rules, bundle_dir=bundle,
                       cache_dir=tmp_path / "no-cache")
    assert result["never_merge"]["dead"] == [["npcs/a", "npcs/gone"]]
    assert result["important"]["dead"] == ["deities/gone_deity"]


def test_split_is_live_when_the_generic_name_is_still_a_known_alias(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "npcs").mkdir(parents=True)
    (bundle / "npcs" / "abisalis_harald.md").write_text("live", encoding="utf-8")

    registry = tmp_path / "entity_registry.yaml"
    _write(registry, {"entities": [{
        "concept_id": "npcs/abisalis_harald",
        "type": "NPC",
        "canonical_name": "Abisalis Harald",
        "aliases": ["Harald"],
    }]})
    rules = tmp_path / "entity_rules.yaml"
    _write(rules, {"split": [
        {"name": "harald", "session": "2026-04-14", "concept_id": "npcs/harald_daemon"},
    ]})

    result = classify(registry_path=registry, rules_path=rules, bundle_dir=bundle,
                       cache_dir=tmp_path / "no-cache")
    assert len(result["split"]["live"]) == 1
    assert result["split"]["live"][0]["name"] == "harald"
    assert result["split"]["inert"] == []


def test_session_names_reads_the_cached_extraction_by_date_prefix(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "2026-04-14_RF_x.json").write_text(
        '{"extraction": {"entities": [{"name": "Abisalis Harald"}]}}', encoding="utf-8"
    )

    assert session_names("2026-04-14", cache) == {"abisalis harald"}
    assert session_names("2099-01-01", cache) == set()
