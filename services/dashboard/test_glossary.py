"""Plain-assert tests for glossary.py — pytest-collectible, no fixtures/mocks."""

from __future__ import annotations

import json
from pathlib import Path

import glossary

SCRATCH = Path(__file__).parent / "_test_scratch_glossary"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_name_key_splits_apostrophe_and_case():
    assert glossary.name_key("Vhar'Zul") == ("vhar", "zul")
    assert glossary.name_key("HACK") == glossary.name_key("hack")


def test_entity_name_sources_precedence_and_dedup():
    entities = [
        {
            "concept_id": "npcs/lenra",
            "canonical_name": "Die Hag Lenra",
            "aliases": ["Hack", "Sumpfhexe"],
        }
    ]
    rules = {"merge": {"hack": "npcs/lenra", "lanra": "npcs/lenra"}}
    sources = glossary.entity_name_sources(entities, rules)
    names = sources["npcs/lenra"]
    by_name = {n: s for n, s in names}
    assert by_name["Die Hag Lenra"] == "canonical"
    # merge: keys are stored lowercase in entity_rules.yaml, so the display
    # name inherits that case. "hack" is both a merge key and a registry
    # alias -> merge wins, appears once.
    assert by_name["hack"] == "merge"
    assert sum(1 for n, _ in names if n.lower() == "hack") == 1
    assert by_name["lanra"] == "merge"
    assert by_name["Sumpfhexe"] == "registry"


def test_count_names_whole_word_case_insensitive():
    d = SCRATCH / "transcripts_final"
    _write(
        d / "2026-01-01_RF_x.json",
        json.dumps(
            {
                "segments": [
                    {"text": "Die Hexe heisst Hack, sagte Hack laut."},
                    {"text": "Cracker ist kein Treffer."},
                ]
            }
        ),
    )
    counts = glossary.count_names(d, {("hack",)})
    assert counts[("hack",)] == 2
    _cleanup()


def test_count_names_multiword_alias():
    d = SCRATCH / "transcripts_final"
    _write(
        d / "2026-01-01_RF_x.json",
        json.dumps({"segments": [{"text": "Vhar Zul erschien im Amulett."}]}),
    )
    counts = glossary.count_names(d, {("vhar", "zul")})
    assert counts[("vhar", "zul")] == 1
    _cleanup()


def test_build_end_to_end(tmp_path=None):
    knowledge = SCRATCH / "knowledge"
    crawl = SCRATCH
    _write(
        knowledge / "entity_registry.yaml",
        "entities:\n"
        "- concept_id: npcs/lenra\n"
        "  type: NPC\n"
        "  canonical_name: Die Hag Lenra\n"
        "  aliases: [Sumpfhexe]\n"
        "  mention_count: 9\n",
    )
    _write(
        knowledge / "entity_rules.yaml",
        "merge:\n"
        "  hack: npcs/lenra\n"
        "canonical_name:\n"
        "  npcs/lenra: Die Hag Lenra\n",
    )
    _write(
        crawl / "transcripts_final" / "2026-01-01_RF_x.json",
        json.dumps({"segments": [{"text": "Hack Hack die Sumpfhexe"}]}),
    )
    result = glossary.build(knowledge, crawl)
    assert result["entities"][0]["concept_id"] == "npcs/lenra"
    assert result["entities"][0]["pinned"] is True
    assert result["entities"][0]["mention_count"] == 9
    by_name = {a["name"]: a["count"] for a in result["entities"][0]["aliases"]}
    assert by_name["hack"] == 2
    assert by_name["Sumpfhexe"] == 1
    assert result["entities"][0]["total_count"] == 3
    assert result["types"] == ["NPC"]
    _cleanup()


def _cleanup() -> None:
    import shutil

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)


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
