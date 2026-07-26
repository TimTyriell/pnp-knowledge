"""Apply the confirmed merge groups from the dedup sweep to the registry.

Allowlist by design: only the groups listed here are written. The sweep
proposed 230 candidates and most were false positives from shared name
prefixes ("kampf_gegen_die_goblins" vs "kampf_gegen_die_mimic"), so silence
must mean "reject", never "accept".

Each entry is ``canonical_concept_id: [absorbed_concept_ids]``. Run once:

    python apply_merges.py            # dry run, prints what would change
    python apply_merges.py --write    # update knowledge/entity_registry.yaml
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pnp_okf.config import DeepSeekConfig, Paths  # noqa: E402
from pnp_okf.extract import _cache_key, _cache_path, _load_cached  # noqa: E402
from pnp_okf.ingest import load_transcripts  # noqa: E402
from pnp_okf.resolve import resolve_entities  # noqa: E402

# --- confirmed groups -------------------------------------------------------
# Sources: LLM semantic proposals + string candidates, hand-triaged, plus four
# explicit user decisions (Willau = one city; only the Dwarfmaster/Ehrenfels
# guild merges; Abisalis and Splitterwelt are ONE domain — superseding the
# Phase 1 split; generic entries fold into the most-mentioned specific).
ACCEPTED: dict[str, list[str]] = {
    # -- deities: transcription drift on the same god -------------------------
    "deities/vharzul": ["deities/vasur_vasul", "deities/warzul_varsurs", "deities/valsur"],
    "deities/korn": ["deities/blutgott", "deities/born", "deities/core"],
    "deities/tarvok_der_erdrichter": ["deities/tavok_erdrichter"],
    "deities/vorgul_tar": [
        "deities/volgultar",
        "deities/vorgultar_herr_der_tausend_seelen",
    ],
    "deities/alter_schlangengott": ["deities/schlangengottheit"],
    "deities/heiliger_duran": ["deities/duran"],
    "deities/neue_goetter": ["deities/die_neuen_goetter"],
    # -- domains --------------------------------------------------------------
    # User decision: one domain, not two (supersedes the Phase 1 separation).
    "domains/splitterwelt": ["domains/abyssalis_splitterwelt", "domains/abisalis"],
    "domains/materielle_ebene": ["domains/materielle_plaene"],
    # -- characters -----------------------------------------------------------
    "characters/miko": ["characters/myko"],
    "characters/carlos": ["characters/kalos"],
    # -- factions -------------------------------------------------------------
    # User decision: the party's home guild only. Gilde der Schilde (Tiefwasser),
    # Brabarant, Banditengilde and Gilde Breska stay separate organisations.
    "factions/dwarfmaster_gilde": [
        "factions/die_gilde",
        "factions/gilde",
        "factions/dwarfmasters",
        "factions/zwergenmeistergilde",
        "factions/die_zwergenmeister_gilde",
        "factions/ehrenfels_gilde",
        "factions/gilde_ehrenfels",
        "factions/berggilde",
    ],
    "factions/fluechtlinge_aus_breska": ["factions/die_fluechtlinge"],
    "factions/goblins": ["factions/goblinhorde", "factions/goblins_der_minen"],
    "factions/hack": ["factions/die_hack"],
    "factions/kultisten": ["factions/kultisten_von_varsurs"],
    "factions/rotunas_helden": ["factions/rotunas_bande"],
    "factions/untotenarmee": ["factions/untote_armeen"],
    "factions/die_neuen_goetter": ["factions/die_neuen"],
    "factions/alte_goetter": ["factions/die_alten"],
    # -- items ----------------------------------------------------------------
    "items/amulett_des_heiligen_duran": [
        "items/amulett_der_vier",
        "items/amulett_des_duran",
        "items/amulett_medaillon",
        "items/amulett_stimmen",
        "items/die_geister_im_amulett",
    ],
    "items/der_heilige_streitkolben": [
        "items/cepros_heiliger_streitkolben",
        "items/dodos_heiliger_streitkolben",
        "items/dodos_streitkolben",
    ],
    "items/phoenixfeder": ["items/der_phoenixfeder"],
    "items/kaputter_kompass": ["items/cookies_kaputter_kompass"],
    "items/leuchtringe": ["items/leuchtende_ringe_cookie"],
    "items/lindos_stab": ["items/stab_lindos_stab", "items/stab"],
    "items/schattenfinger": [
        "items/schattenfinger_kenku_kralle",
        "items/schattenfinger_klaue",
    ],
    "items/gegengifte": ["items/gegengift_aus_dem_sumpf"],
    "items/heilige_pfeile": ["items/heilige_pfeile_holy_arrows"],
    "items/seelenstein": ["items/der_gruene_seelenstein"],
    "items/gruener_kristall": ["items/der_kristall"],
    "items/magische_handschellen": ["items/goettliche_handschellen"],
    "items/ring_der_teleportation": ["items/der_ring"],
    "items/magischer_schluessel": ["items/schluessel", "items/der_stab_schluessel"],
    "items/schriftrolle_von_nerash": ["items/schriftrolle"],
    "items/notiz_findet_einen_suendenbock": ["items/notiz"],
    # -- locations ------------------------------------------------------------
    # User decision: all one city. Its arena, tavern and library stay separate.
    "locations/willau": [
        "locations/willauch",
        "locations/willoch",
        "locations/willau_willoch",
        "locations/willauer",
        "locations/vilauch",
    ],
    "locations/fluechtlingslager": ["locations/das_fluechtlingslager"],
    "locations/kapelle": ["locations/die_kapelle"],
    "locations/sumpf": ["locations/der_sumpf", "locations/der_nebelsumpf"],
    "locations/bruecke": ["locations/die_bruecke"],
    "locations/banditenlager": [
        "locations/das_banditenlager",
        "locations/banditenlager_festung",
        "locations/banditenfestung",
    ],
    "locations/turm": ["locations/der_turm", "locations/der_alte_turm"],
    "locations/mine": ["locations/die_mine"],
    "locations/ringtal": ["locations/kleinringtal"],
    # Berg Zebros (the mountain) is NOT Burg Zebros (the castle ruin).
    "locations/berg": ["locations/berg_zebras", "locations/zebras_berg"],
    "locations/katakomben": ["locations/der_katakomben_dungeon"],
    "locations/kathedrale": ["locations/kathedrale_von_steinbachtal"],
    "locations/altarraum": ["locations/der_altarraum_des_ohoriaks"],
    "locations/gruft": ["locations/die_gruft_des_grafen"],
    "locations/boragdil": ["locations/boragdil_brocadil"],
    "locations/arena_von_willau": ["locations/die_arena"],
    # -- npcs -----------------------------------------------------------------
    "npcs/nairuk": [
        "npcs/naeruk",
        "npcs/nai_ruck",
        "npcs/nairook_nayruk",
        "npcs/nyruk",
        "characters/nyruk",
        "characters/naeruk",
    ],
    "npcs/lobrecht": [
        "npcs/kahnfuehrer_lobrecht",
        "npcs/kapitaen_lobrecht",
        "npcs/miyamani_und_kaept_n_lobrecht",
    ],
    "npcs/gildenmeister": ["npcs/der_gildenmeister", "npcs/enox_gildenmeister"],
    "npcs/hack": ["npcs/die_hack", "npcs/moorhexe_hack"],
    "npcs/hexe": ["npcs/heck_die_hexe"],
    "npcs/lenra": ["npcs/leandra"],
    "npcs/geist_von_rotunas": ["npcs/geist", "npcs/der_geist"],
    "npcs/slix_vasul": ["npcs/slicks"],
    "npcs/seraphen": ["npcs/seraph"],
    "npcs/belorus": ["npcs/geistergestalt_bote_von_belorus"],
    "npcs/lord_kalidarn_von_willau": ["npcs/lord_kaledan", "npcs/lord_von_willauch"],
}

# Rejected on purpose — kept so a later reviewer sees these were considered,
# not overlooked. Each is a distinct entity the string matcher confused.
REJECTED_NOTES = {
    "deities/nerash + deities/seras": "different gods; 0.73 string similarity only",
    "deities/alte_goetter + deities/neue_goetter": "explicit opposites",
    "npcs/tyrael + npcs/tyrex": "a lich and a soul in the amulet",
    "npcs/elisa + npcs/lia + npcs/lisa": "three separate villagers",
    "npcs/hal + npcs/harl + npcs/harald": "three separate bandit leaders",
    "events/der_erste_arenakampf + der_zweite_arenakampf": "explicitly sequential",
    "locations/ehrenfels + taverne_in_ehrenfels": "a city and a tavern inside it",
    "locations/berg_zebras + burg_zebros": "the mountain vs the castle ruin",
    "items/dokument_mit_siegel + dolch_mit_siegel": "a document and a dagger",
    "items/amulett_des_heiligen_duran + morgenstern_des_heiligen_duran": "different relics",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="Write the registry")
    args = ap.parse_args()
    logging.disable(logging.WARNING)

    paths = Paths.resolve(
        "C:/dev/pnp/pnp-crawl/transcripts_final",
        "C:/dev/pnp/pnp-knowledge/knowledge/bundle/splitter_des_ewigen",
        "C:/dev/pnp/pnp-knowledge/services/kb/.cache",
    )
    cfg = DeepSeekConfig.from_env()
    transcripts = load_transcripts(paths.transcript_dir)
    extractions = {
        t.session_id: c
        for t in transcripts
        if (c := _load_cached(_cache_path(paths.cache_dir, t), _cache_key(t, cfg)))
    }
    entities = resolve_entities(
        extractions, {t.session_id: t for t in transcripts}, paths.registry_path
    )
    by_id = {e.concept_id: e for e in entities}

    new_merges: dict[str, str] = {}
    missing: list[str] = []
    absorbed = 0
    for canonical, losers in ACCEPTED.items():
        if canonical not in by_id:
            missing.append(f"canonical missing: {canonical}")
            continue
        for loser in losers:
            e = by_id.get(loser)
            if e is None:
                missing.append(f"  absorbed missing: {loser}")
                continue
            absorbed += 1
            for name in [e.canonical_name, *e.aliases]:
                if name:
                    new_merges[name.strip().lower()] = canonical

    print(f"entities now         : {len(entities)}")
    print(f"groups accepted      : {len(ACCEPTED)}")
    print(f"concepts absorbed    : {absorbed}")
    print(f"name->concept entries: {len(new_merges)}")
    print(f"projected entity count: ~{len(entities) - absorbed}")
    if missing:
        print(f"\n!! {len(missing)} listed id(s) not found (already merged or renamed):")
        for m in missing[:25]:
            print("   ", m)

    if not args.write:
        print("\nDry run. Re-run with --write to update the registry.")
        return 0

    raw = paths.registry_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(raw) or {}
    merge = doc.get("merge") or {}
    before = len(merge)
    merge.update(new_merges)
    doc["merge"] = merge
    # Split on the 'merge:' key at column 0 — the comment block above it also
    # contains the literal "merge:", so a naive split would eat the header.
    header = re.split(r"^merge:", raw, maxsplit=1, flags=re.MULTILINE)[0]
    paths.registry_path.write_text(
        header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"\nregistry merge entries: {before} -> {len(merge)}")
    print(f"written: {paths.registry_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
