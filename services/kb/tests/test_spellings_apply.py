"""Offline unit tests for the spelling-fix mechanism's moving parts:
links.py::apply_spellings, synthesize.py::_link_first_occurrence's genitive
guard, and validate.py::fix_bundle's retro-apply path. No bundle, no LLM —
see test_spelling_sweep.py for the real-bundle proof these actually fired.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pnp_okf.links import apply_spellings
from pnp_okf.resolve import load_spellings
from pnp_okf.synthesize import _link_first_occurrence
from pnp_okf.validate import fix_bundle

# --- apply_spellings ------------------------------------------------------


def test_apply_spellings_leaves_link_target_untouched():
    body = "Willkommen in [Willoch](/locations/willauch.md)."
    out = apply_spellings(body, {"Willoch": "Willauch"})
    assert out == "Willkommen in [Willauch](/locations/willauch.md)."


def test_apply_spellings_rewrites_link_label():
    body = "[Willoch](/locations/willauch.md) liegt im Norden."
    out = apply_spellings(body, {"Willoch": "Willauch"})
    assert out.startswith("[Willauch](/locations/willauch.md)")


def test_apply_spellings_does_not_touch_belege_section():
    body = "Lanra erscheint hier.\n\n# Belege\n- Lanra sagt etwas [01:02:03]"
    out = apply_spellings(body, {"Lanra": "Landra"})
    head, _, tail = out.partition("# Belege")
    assert "Landra" in head and "Lanra" not in head
    assert "Lanra" in tail


def test_apply_spellings_prefers_longer_key_first():
    body = "Die Festung Zebras liegt im Osten."
    out = apply_spellings(body, {"Zebras": "Zebros", "Festung Zebras": "Festung Zebros"})
    assert out == "Die Festung Zebros liegt im Osten."


def test_apply_spellings_respects_word_boundary():
    body = "Leandras Schwert glänzt."
    out = apply_spellings(body, {"Lanra": "Landra"})
    assert out == body  # "Lanra" must not match inside "Leandras"


# --- _link_first_occurrence genitive guard --------------------------------


def test_genitive_tail_normally_links_a_possessive():
    text = "Das ist Voras Amulett."
    out = _link_first_occurrence(text, "Vora", "npcs/vora")
    assert "[Voras](npcs/vora.md)" in out


def test_genitive_tail_suppressed_when_it_collides_with_a_known_name():
    text = "Das ist Voras Amulett."
    known = {"vora", "voras"}
    out = _link_first_occurrence(text, "Vora", "npcs/vora", known)
    assert out == text  # "Voras" must be left for the "Voras" entity to claim


def test_genitive_tail_still_suppressed_leaves_room_for_the_longer_name():
    text = "Voras half der Gruppe. Voras Weisheit war grenzenlos."
    known = {"vora", "voras"}
    linked = _link_first_occurrence(text, "Voras", "npcs/voras", known)
    assert "[Voras](npcs/voras.md)" in linked


# --- fix_bundle retro-apply -------------------------------------------------


def _write_registry_and_rules(tmp_path: Path) -> Path:
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(yaml.safe_dump({"entities": []}), encoding="utf-8")
    rules = tmp_path / "entity_rules.yaml"
    rules.write_text(yaml.safe_dump({"spelling": {"Lanra": "Landra"}}), encoding="utf-8")
    return registry


def test_fix_bundle_applies_spellings_when_registry_path_given(tmp_path: Path):
    bundle = tmp_path / "bundle"
    npcs = bundle / "npcs"
    npcs.mkdir(parents=True)
    (npcs / "landra.md").write_text(
        "---\ntitle: Landra, die Hag\n---\nLanra erschreckt die Gruppe.\n",
        encoding="utf-8",
    )
    registry_path = _write_registry_and_rules(tmp_path)

    fix_bundle(bundle, registry_path)

    assert "Landra erschreckt" in (npcs / "landra.md").read_text(encoding="utf-8")


def test_fix_bundle_leaves_prose_alone_without_a_registry_path(tmp_path: Path):
    bundle = tmp_path / "bundle"
    npcs = bundle / "npcs"
    npcs.mkdir(parents=True)
    (npcs / "landra.md").write_text(
        "---\ntitle: Landra, die Hag\n---\nLanra erschreckt die Gruppe.\n",
        encoding="utf-8",
    )

    fix_bundle(bundle)

    assert "Lanra erschreckt" in (npcs / "landra.md").read_text(encoding="utf-8")


def test_fix_bundle_degrades_a_self_link(tmp_path: Path):
    # fix_bundle computes concept_ids in the same order as files but used to
    # forget to pass self_id to normalize_body -- so a self-link only got
    # degraded on a full `pnp run` (emit.py's callers pass self_id), never on
    # the retro-apply path.
    bundle = tmp_path / "bundle"
    npcs = bundle / "npcs"
    npcs.mkdir(parents=True)
    (npcs / "foo.md").write_text(
        "---\ntitle: Foo\n---\n[Foo](/npcs/foo.md) ist wichtig.\n",
        encoding="utf-8",
    )

    fix_bundle(bundle)

    text = (npcs / "foo.md").read_text(encoding="utf-8")
    assert "[Foo](/npcs/foo.md)" not in text
    assert "Foo ist wichtig." in text


def test_load_spellings_reads_the_sibling_rules_file(tmp_path: Path):
    registry_path = _write_registry_and_rules(tmp_path)
    assert load_spellings(registry_path) == {"Lanra": "Landra"}
