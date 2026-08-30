"""Named regressions from the 2026-08-29 bundle-quality audit.

Unlike the ratchets in test_bundle_invariants.py / test_link_coverage.py /
test_rules_applied.py (a count that must not grow), every assertion here
names a *specific*, individually-verified defect: a concept id that must
stop existing, or a content claim a specific node's body must (or must not)
make. These are expected to be RED on this branch until entity_rules.yaml's
Teil 2 (A-F) is applied *and* a real `pnp run` regenerates the bundle from
it — see docs/audits/2026-08-29-bundle-quality.md. That is intentional: this
file is the proof the fix worked, not a check that passes by construction.

Each duplicate/content claim below was read and confirmed directly in the
committed bundle during the audit (file paths and quoted snippets in the
report); nothing here is inferred from the rules file alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from pnp_okf.models import TYPE_DIR
from pnp_okf.resolve import RULES_FILENAME

KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
RULES = KNOWLEDGE / RULES_FILENAME
BUNDLE = KNOWLEDGE / "bundle" / "splitter_des_ewigen"

pytestmark = pytest.mark.skipif(not REGISTRY.exists(), reason="no bundle checked out")


def _bundle_concepts() -> set[str]:
    return {
        str(p.relative_to(BUNDLE).with_suffix("")).replace("\\", "/")
        for p in BUNDLE.rglob("*.md")
        if p.name not in ("index.md", "log.md")
    }


def _body(concept_id: str) -> str | None:
    path = BUNDLE / f"{concept_id}.md"
    return path.read_text(encoding="utf-8") if path.is_file() else None


# --- duplicates that must be gone (Frage 3 + Frage 2, entity_rules.yaml A/F) -

# Player-character session-zero stubs never folded into their PC (merge:),
# plus self-referencing NPC/item/deity/faction duplicates and bare generic
# nouns that duplicate an ignore:'d article form. Full list and evidence in
# Teil 1, Frage 3 of the audit report.
DUPLICATES_THAT_MUST_BE_GONE = [
    "characters/saris_bendal",
    "characters/celin_cookie",
    "characters/marco_dodo",
    "characters/tim_lindo_laut",
    "characters/esterossa_mikasa",
    "npcs/priesterin_auranie",
    "npcs/captain_lobrecht",
    "npcs/graf_voras",
    "npcs/jorah_vanur",
    "npcs/kinder",
    # factions/fluechtlinge was on this list until 2026-08-30, on the audit's
    # reading that it duplicated factions/fluechtlinge_aus_breska. The GM has
    # since ruled the two are different groups (the bare-noun mention from
    # 2026-01-13 describes refugees "aus verschiedenen Orten", not Roland's
    # Breska group), so the concept is now supposed to exist and the merge:
    # key that folded it was removed. A GM ruling outranks an audit guess;
    # see the never_merge: pair in entity_rules.yaml that now keeps them apart.
    "items/der_streitkolben",
    "items/das_amulett_von_lindo_laut",
    "items/stab_von_lindo_laut",
    "deities/die_alten_goetter",
    "deities/tavok",
    "deities/kol_merefs",
    "npcs/akastrale",
    "npcs/suedrawell",
    "factions/neue_goetter",
    "factions/die_untoten",
    "locations/das_ende",
]


def test_named_duplicates_are_merged_away():
    concepts = _bundle_concepts()
    still_present = sorted(cid for cid in DUPLICATES_THAT_MUST_BE_GONE if cid in concepts)
    assert not still_present, (
        f"these concepts should have been folded away by entity_rules.yaml "
        f"merge:/ignore: entries (Teil 2 A/F) after a `pnp run` — still "
        f"present: {still_present}"
    )


# --- content gates: a specific node must (or must not) say a specific thing -


def test_ring_der_teleportation_describes_lindo_lauts_ring():
    # Kanon_Entscheidungen.md: "Der Ring der Teleportation ist ein Gegenstand
    # von Lindo Laut ... Der Ring, den Dodo zerstört hat, ist ein anderer,
    # nicht verwandter Ring." The node currently describes Dodo's ring
    # instead — the ruling isn't reaching synthesis because entity_rules.yaml
    # folds "lindo lauts ring"/"lindos ring" onto this concept while the
    # actual evidence for those mentions lives under items/ring_von_lindo_laut.
    body = _body("items/ring_der_teleportation")
    if body is None:
        pytest.skip("items/ring_der_teleportation no longer exists")
    assert "Lindo Laut" in body, (
        "items/ring_der_teleportation.md does not mention Lindo Laut — the "
        "ENTSCHEIDUNG: in Kanon_Entscheidungen.md says this concept is his "
        "ring, not Dodo's destroyed one"
    )


def test_hans_split_is_not_recombined_by_a_link():
    # entity_rules.yaml split: rules npcs/hans_soldat_aus_breska and
    # npcs/hans_wirt_zum_gruenen_sichelmond apart as "two unrelated men" — but
    # the soldier's own body links "Hans" straight to the innkeeper's page.
    body = _body("npcs/hans_soldat_aus_breska")
    if body is None:
        pytest.skip("npcs/hans_soldat_aus_breska no longer exists")
    assert "hans_wirt_zum_gruenen_sichelmond" not in body, (
        "npcs/hans_soldat_aus_breska.md links to "
        "npcs/hans_wirt_zum_gruenen_sichelmond.md — the split: rule says "
        "these are two unrelated men, needs a never_merge: pair (Teil 2 C)"
    )


def test_nothing_links_the_merchant_to_the_god_jorah():
    # npcs/jorah_vanur (a mortal Sanddorn merchant, merged into
    # npcs/joar_vanur) linked its own subject's first name to deities/jorah —
    # a live conflation between a person and an unrelated god.
    bad = []
    for cid in ("npcs/joar_vanur", "npcs/jorah_vanur"):
        body = _body(cid)
        if body and "deities/jorah.md" in body:
            bad.append(cid)
    assert not bad, f"still linking the merchant Vanur to deities/jorah: {bad}"


def test_cornivum_links_lenra():
    # locations/cornivum names Lenra as the cause of the location's condition
    # in prose ("## Beziehungen und Verbindungen") but as plain text, not a
    # link — the file has zero markdown links today.
    body = _body("locations/cornivum")
    if body is None:
        pytest.skip("locations/cornivum no longer exists")
    assert "npcs/lenra.md" in body, "locations/cornivum.md does not link npcs/lenra.md"


def test_belorus_links_his_faction():
    body = _body("npcs/belorus")
    if body is None:
        pytest.skip("npcs/belorus no longer exists")
    assert "factions/belorus_untotenarmee.md" in body or "factions/koenigreich_zebros.md" in body, (
        "npcs/belorus.md names his army/kingdom in prose but links neither"
    )


def test_koenigreich_zebros_has_at_least_one_link():
    # The richest faction node in the bundle — zero markdown links today.
    body = _body("factions/koenigreich_zebros")
    if body is None:
        pytest.skip("factions/koenigreich_zebros no longer exists")
    assert re.search(r"\]\([^)\s]*?\.md\)", body), "factions/koenigreich_zebros.md has zero links"


# --- hard pin test: no dead important:/unimportant: entries -----------------


def test_important_pins_name_existing_concepts():
    # Not a ratchet: a pin naming a concept that does not exist is dead on
    # arrival and should never be introduced, let alone accumulate silently
    # inside DEAD_RULES_BASELINE (test_rules_applied.py) where it never
    # surfaces on its own. Caught deities/kol_meref (real id: deities/kollmereth).
    concepts = _bundle_concepts()
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {} if RULES.exists() else {}
    pinned = list(rules.get("important") or []) + list(rules.get("unimportant") or [])
    dead = sorted(cid for cid in pinned if cid not in concepts)
    assert not dead, f"important:/unimportant: pin names a concept that does not exist: {dead}"


# --- no self-links ------------------------------------------------------


def test_no_concept_links_itself():
    # Confirmed today: locations/ringtal links "Ringtal" back to its own
    # page even though its body describes Ringtal as a *different*, larger
    # place than Kleinringtal (the page it's actually on); npcs/der_seraph_vierter
    # likewise. Fix 4 (links.py::normalize_body, self_id=) degrades these to
    # plain text at emit time — this only takes effect after a `pnp run`.
    bad = []
    for etype_dir in TYPE_DIR.values():
        for path in sorted((BUNDLE / etype_dir).glob("*.md")):
            if path.name == "index.md":
                continue
            cid = f"{etype_dir}/{path.stem}"
            text = path.read_text(encoding="utf-8")
            if re.search(rf"\]\(/?{re.escape(cid)}\.md\)", text):
                bad.append(cid)
    assert not bad, f"concept(s) link their own page: {bad}"


# --- PC coverage null-guarantee ------------------------------------------

# The one area the audit found already fully correct (Frage 6): every PC's
# own body mentions every session date that links to them. Named here, not
# just measured, because the entity_rules.yaml merges in this same audit
# touch PC concepts directly (saris_bendal -> saris, etc.) and are the one
# change with real risk of breaking it.
_PCS = (
    "characters/dodo", "characters/lindo_laut", "characters/cookie",
    "characters/esterossa", "characters/rotunas", "characters/lunara_velora",
    "characters/nyrella", "characters/gunther",
    "characters/kaya", "characters/sange", "characters/saris", "characters/bruma_stormrak",
)


def test_every_pc_chronologie_covers_every_linked_session():
    sessions_dir = BUNDLE / "sessions"
    session_texts = {
        p.stem: p.read_text(encoding="utf-8") for p in sorted(sessions_dir.glob("*.md"))
    }
    missing = []
    for cid in _PCS:
        body = _body(cid)
        if body is None:
            continue  # a merge target rename is a different test's job
        slug = cid.rsplit("/", 1)[-1]
        needle = f"/characters/{slug}.md"
        for date, text in session_texts.items():
            if needle in text and date not in body:
                missing.append(f"{cid}: linked by session {date}, but that date is absent from its own body")
    assert not missing, missing
