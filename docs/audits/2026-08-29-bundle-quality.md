# Datenqualitäts-Audit OKF-Bundle `splitter_des_ewigen` (2026-08-29)

Tiefe Stichprobe entlang 6 Fragen (Länge, Namens-Spezifität, fälschlich getrennt, fälschlich gemerged, Faktion↔Charakter↔Ort-Beziehungen, Hauptcharaktere Gruppe A/B), durchgeführt mit 3 parallelen Sonnet-Subagents; jeder Befund unten wurde im Bundle nachgeprüft, nicht nur aus Subagent-Output übernommen.

**Kernergebnis:** PC-Abdeckung ist vorbildlich, Länge korreliert im Aggregat sauber mit der Belegmenge. Die drei echten Defekte:

1. Die 60 reichsten Nodes (Deep-Tier) sind graph-unsichtbar — der Autolinker lief nur auf Stub-Nodes.
2. ~25 Identitätsdubletten, die keine Konfliktdatei erzeugen und darum unsichtbar bleiben.
3. `important: true` war als Tier-Schalter in beide falsche Richtungen benutzt: aufgesetzt auf Ein-Szenen-Entitäten (Padding), vorenthalten bei wiederkehrenden Figuren (Stubs) — und 7 der 29 Pins zeigten zusätzlich auf eine nicht (mehr) existierende concept_id.

Alle Fixes gehen an die **Eingänge** (`entity_rules.yaml`, `sources/Kanon_Entscheidungen.md`, Pipeline-Code in `services/kb/src/pnp_okf/`) — nie ins generierte Bundle (siehe `knowledge/conflicts/README.md`).

## Bestand

| Typ | Nodes | Median W. | Max | Deep-Tier |
|---|---|---|---|---|
| characters | 36 | 721 | 4088 | 19 |
| deities | 32 | 569 | 1928 | 17 |
| domains | 12 | 154 | 1417 | 1 |
| events | 252 | 72 | 6554 | 0 |
| factions | 43 | 167 | 1272 | 2 |
| items | 149 | 73 | 3742 | 0 |
| locations | 151 | 78 | 3863 | 9 |
| npcs | 229 | 83 | 5905 | 12 |
| **gesamt** | **896** | | | **60** |

Gesund: 0 verwaiste Registry-Einträge, 889 interne Links davon **0 kaputt**, 7 Orphan-Nodes.

## Frage 1 — Länge: im Aggregat korrekt, Tier-Schalter falsch bedient

Wörter vs. `mention_count` sauber monoton: 1 Mention → 75 W (n=765) · 2 → 235 (61) · 3–4 → 357 (33) · 5–9 → 520 (18) · 10+ → 1671 (19). Die Extraktion ist längenproportional; der Fehler sitzt in der **Tier-Zuweisung**.

*Zu lang* — alle 5 Nodes mit ≤1 Mention und >400 W tragen `important: true`: `deities/coram_schildbrecher` (916 W), `deities/akastrale` (800 W — zitiert im eigenen Beleg eine `ENTSCHEIDUNG:`, dass „vorerst kein umfangreicher Eintrag entstehen soll", und widersprach ihr damit), `locations/boragdil` (592 W aus einer ~2-Minuten-Szene), `deities/schlangengott` (569), `deities/heiliger_duran` (497 — über den Gott selbst „wenig bekannt", Rest handelt vom Amulett).

*Zu kurz* — 9 Nodes mit ≥5 Mentions, kein Deep-Tier, kein Flag: `npcs/hal_harl` (5 M, Mitanführer der Silberkerne), `npcs/auranil` (5), `npcs/liam_velora` (7), `npcs/lobrecht` (6), `npcs/miaomani` (6), `locations/ringtal` (6), `locations/banditenlager_der_silberkerne` (5), `factions/silberkerne` (6), `items/amulett_des_heiligen_duran` (7).

Ursache: `DEEP_MENTION_THRESHOLD = 8` (`models.py`) — Klasse 5–7 fiel komplett auf `standard`.

**Fix:** `DEEP_MENTION_THRESHOLD` 8 → 5 (behebt die 9 Stubs strukturell, ohne Handpflege); `unimportant: deities/akastrale` (behebt den einen Fall, den die Schwelle nicht anfasst).

## Frage 2 — Namens-Spezifität: systematisch zu generisch

312 Nodes mit einwortigem Namen. Gattungsbegriffe als Entität, `mention_count = 1` trotz 13–65 Vorkommen in den Session-Recaps: `events/falle` (30) · `locations/dorf` (21) · `locations/pass` (20) · `locations/taverne` (18) · `items/kristall` (18) · `locations/nebel` (16) · `npcs/gnoll` (13) · `domains/daggerheart` (65 — das **Regelsystem**, keine Weltdomäne).

**Beweis, dass das Lücken sind, keine Absicht:** `ignore:` enthielt bereits `npcs/die_kinder` mit exakt dieser Begründung — nur greift die Regel auf exakte Strings, `npcs/kinder` (ohne Artikel) lebte daneben weiter. Eine neue strukturelle Prüfung (`test_article_variant_does_not_slip_past_a_rule`) fand **12** solcher Artikel-Dubletten insgesamt, nicht nur die zwei ursprünglich vermuteten.

Slug/Name-Konflation: `locations/ringtal` heißt im Titel „Kleinringtal", der eigene Body beschreibt Ringtal als *anderen*, größeren Ort — verlinkt aber auf sich selbst (Selbstlink, siehe Frage 5/Fix 4).

**Fix:** 10 Gattungsknoten in `ignore:`, `kristall` als bare-Form in `merge:` (verlinkt bereits auf `items/gruener_kristall`).

## Frage 3 — Fälschlich getrennt: ~22 Dubletten

**Sicher:** 5 PC-Session-Zero-Stubs nie gefaltet (`saris_bendal`↔`saris`, `celin_cookie`↔`cookie`, `marco_dodo`↔`dodo`, `tim_lindo_laut`↔`lindo_laut`, `esterossa_mikasa`↔`esterossa`) — für vier davon faltete `merge:` bereits das VTT-Klassenlabel, nicht den eigenen Stub-Titel. Nodes, die ihre eigene Dublette verlinken (selbstbeweisend): `priesterin_auranie`→`auranil`, `graf_voras`→`voras`, `captain_lobrecht`→`lobrecht`, `das_amulett_von_lindo_laut`→`amulett_des_heiligen_duran`, `das_ende`→`ende_jenseits_der_orkgebiete` (Split-Regel deckte nur Session 2026-03-18, nicht 2025-10-07).

Typ-Splits nach `zebros`-Präzedenzfall: `akastrale`, `suedrawell`, `neue_goetter` (je Deity vs. NPC/Faction). Schreib-/Artikelvarianten: `tavok`, `kol_merefs`, `jorah_vanur`↔`joar_vanur`, `die_alten_goetter`, `der_streitkolben`, `stab_von_lindo_laut`, `die_untoten`, `fluechtlinge`.

**Korrekt getrennt (Gegenprobe bestanden):** `miko`/`myko`, `sage`/`sange`. Bei `miaomani`/`miyamani` ist die `never_merge`-Begründung *inhaltlich veraltet* (nennt Miyamani „Halbling", generierter Node beschreibt einen Katari) — Entscheidung vermutlich noch richtig, Begründung nicht mehr.

**GM-Entscheidung nötig:** `gilde_in_breska` (Faktion oder Ort?), `vora`/`voras`.

**Fix:** alle sicheren Fälle als `merge:`/`split:` in `entity_rules.yaml`.

## Frage 4 — Fälschlich gemerged

**`npcs/hans_soldat_aus_breska`** verlinkt „Hans" auf `npcs/hans_wirt_zum_gruenen_sichelmond` — genau der Mann, den die eigene `split:`-Regel (**bereits vorhanden**) als „zwei unterschiedliche Männer" abgrenzt. Die Regel trennt korrekt, der generierte Body führt sie trotzdem wieder zusammen — braucht einen `pnp run` mit dem neuen `never_merge:`-Paar, um sich zu korrigieren.

**`npcs/jorah_vanur`** verlinkte den Vornamen seines Subjekts auf `deities/jorah` — ein sterblicher Händler wird mit einem Gott konflatiert.

**Ring der Teleportation — korrigierte Einschätzung.** Die ursprüngliche Hypothese dieses Audits war ein Fehlmerge (Dodos Ring fälschlich unter Lindo Lauts Namen). Eine GM-Klarstellung während der Umsetzung korrigiert das: **„Der Ring der Teleportation ist der Ring von Lindo Laut"** — `items/ring_von_lindo_laut` war die tatsächliche Dublette (jetzt gemerged), und der Ring, den Dodo zerstört hat, ist ein *drittes*, unabhängiges Objekt (Abisalis, lila Magie), das laut `Kanon_Entscheidungen.md` bereits im Sammeleintrag „Ringe" geführt werden soll. `sources/Kanon_Entscheidungen.md` wurde um genau diese Präzisierung ergänzt.

**Config-Drift, breiter als ursprünglich gefunden:** die harte Prüfung `test_important_pins_name_existing_concepts` (neu) fand **7** tote `important:`-Pins, nicht nur den einen (`deities/kol_meref`) aus der ersten Stichprobe: `deities/bodrak` (real: `bodrak_gott_der_stille`), `deities/kaleandra_die_rote` (real: `kaleandra`), `locations/burg_zebros` (real: `burg_des_belorus`), `deities/neiraj` (war nie eine concept_id, nur ein Merge-Key-Name), sowie `deities/gruul` und `deities/sitravil` — beide passen zu keinem existierenden Konzept, Alias oder Merge-Key; vermutlich ersatzlos aus dem Bundle verschwunden. Vier korrigiert, zwei mangels Nachfolger entfernt (GM-Frage, siehe unten), einer entfernt (kein Nachfolger nötig, Nerash ist als Deity ohnehin immer Deep-Tier).

## Frage 5 — Beziehungen Faktion↔Figur↔Ort: größter struktureller Defekt

**Messung:** 26 % der 42 Faktions-Nodes verlinken `/characters/`, 31 % `/npcs/`, 38 % `/locations/`; **20 von 42 Faktionen nennen kein einziges Mitglied als Link**. Nur **13,6 %** der 228 NPCs tragen einen `/factions/`-Link.

**Seed Belorius ↔ Untotenarmee ↔ Zebros:** `factions/koenigreich_zebros` — der reichste Faktions-Node — hatte **null Links in der gesamten Datei**. `npcs/belorus` verlinkte weder Armee noch Königreich. `locations/berge_von_zebros` hatte einen Abschnitt „Rolle im Konflikt" über die Untotenbedrohung, verlinkte Belorus aber nicht.

**Seed Hag Landra ↔ Cornivum ↔ Sumpf:** `locations/cornivum` nannte Lenra als Ursache **als Klartext**, null Links in der ganzen Datei. `npcs/lenra` erwähnte Cornivum überhaupt nicht.

**Beweis, dass die Information vorhanden ist:** die Session-Recaps `2025-05-14.md` und `2025-06-03.md` listen alle drei Entitäten korrekt verlinkt. Die Relation existierte in der Quelle und ging **in der Synthese** verloren.

**Root Cause (Code, verifiziert):** `_autolink()` in `synthesize.py` wurde ausschließlich von `render_brief_body()` aufgerufen — `synthesize_entity_body()` (`standard`/`deep`) verließ sich auf das LLM selbst, das in langer strukturierter Prosa faktisch nicht selbst verlinkt.

**Fix (umgesetzt):** `autolink_prose()` — läuft jetzt für alle Tiers, splittet vor `# Belege`, überspringt Überschriftenzeilen, ist idempotent (per Unit-Test in `test_brief_local.py` verifiziert). Wirkt beim nächsten `pnp run` **ohne** neue Modellaufrufe, da der Synthese-Cache den Body *vor* dieser Nachbearbeitung speichert.

**Selbstlinks (Nebenbefund, eigener Fix):** `locations/ringtal` und `npcs/der_seraph_vierter` verlinkten auf sich selbst. Fix: `normalize_body()` bekommt einen `self_id`-Parameter und degradiert einen Link aufs eigene Konzept zu Klartext.

## Frage 6 — Hauptcharaktere Gruppe A/B: gesund und ausgewogen

Gruppenzugehörigkeit ist **nicht** Inferenz: `episodes.yaml` und Session-Frontmatter tragen ein `team:`-Feld, belegt auf 60 von 64 Sessions.

- **Gruppe A** (seit 2025-03-26): Dodo, Lindo Laut, Cookie, Esterossa, Rotunas, Lunara Velora, Nyrella, Gunther
- **Gruppe B** (seit 2026-06-04): Kaya, Sange, Saris, Bruma Stormrak

Exhaustiver Diff „Sessions, die den PC verlinken" gegen „Daten in der eigenen Chronologie" ist für **alle 12 PCs leer** — der einzige Bereich, der bereits vollständig korrekt ist. Der Wortzahl-Abstand A vs. B ist Kampagnenalter, kein Qualitätsdefizit (pro Session normalisiert ist B dichter). Cross-Group-Interaktionen gibt es nicht — die Casts sind sich nie begegnet.

**Abgesichert, nicht nur gemessen:** `test_every_pc_chronologie_covers_every_linked_session` (neu) hält diesen Zustand fest, weil die PC-Merges aus diesem Audit (`saris_bendal`→`saris` usw.) genau diese Nodes anfassen.

## Frage 7 (Zusatz) — Konflikt-Queue greift zu selten

Genau **1** offener Konflikt bei 896 Entitäten. Die Erkennung feuert nur auf Widersprüche *innerhalb* der Belege einer Entität; Identitätsprobleme *zwischen* Entitäten (Fragen 3+4) erzeugen nie eine Konfliktdatei, obwohl `conflicts/README.md` das für genau diesen Fall vorsieht. `pnp dedup` findet sie bereits — es fehlt nur, dass jemand hinsieht. Keine eigene Automatisierung gebaut (YAGNI, bis sich zeigt, dass Hinsehen allein nicht reicht).

---

## Umgesetzt

**Pipeline (`services/kb/src/pnp_okf/`):**
- `synthesize.py` / `cli.py` — `autolink_prose()`, für alle Tiers verdrahtet (Fix 1)
- `links.py` / `emit.py` — `normalize_body(self_id=...)`, degradiert Selbstlinks (Fix 4)
- `models.py` — `DEEP_MENTION_THRESHOLD` 8 → 5 (Fix 2)

**Tests (`services/kb/tests/`):**
- 5 neue Unit-Tests für `autolink_prose` (Idempotenz, Belege-Grenze, Überschriften, bestehende Links) in `test_brief_local.py`
- 4 neue Ratchets: Deep-Tier-Linkabdeckung + Faktions-/NPC-Beziehungsabdeckung (`test_link_coverage.py`), Zitationsabdeckung über alle 3 Formate + Tier-vs-Beleg-Abgleich (`test_bundle_invariants.py`), Artikel-Varianten-Dubletten (`test_rules_applied.py`)
- Neue Datei `test_audit_2026_08_29.py`: benannte Regressionen (22 Dubletten, 4 Inhalts-Gates, harter Pin-Test, Selbstlink-Test, PC-Nullgarantie)
- `test_tiering_and_context.py::test_tiers` an neue Schwelle angepasst

**Regeln:**
- `entity_rules.yaml` — 20 Dubletten gefaltet (`merge:`/`split:`), 10 Gattungsknoten (`ignore:`), 7 tote `important:`-Pins korrigiert/entfernt, `unimportant: deities/akastrale`
- `sources/Kanon_Entscheidungen.md` — Ring-der-Teleportation-Klarstellung nach GM-Rückmeldung

## Nicht gefixt, bewusst

- **5 Nodes ohne Quellenangabe** (`deities/saris_patron`, `locations/casa_del_cookie`, `locations/die_narbe`, `npcs/die_hexe`, `npcs/inaros`) — Ursache liegt in `extract.py` (Mention ohne `citation_ts`), außerhalb dieses Audits. Nur als Ratchet festgehalten.
- **Veraltete `never_merge`-Begründung** `miaomani`/`miyamani` — Prosa-Drift zwischen Kommentar und generiertem Inhalt ist nicht sinnvoll testbar; GM-Frage.
- **Identitätskonflikte landen nicht in der Konflikt-Queue** — `pnp dedup` deckt das bereits ab, Automatisierung ist YAGNI bis sich das Gegenteil zeigt.
- **`deities/gruul`, `deities/sitravil`** — kein Nachfolgekonzept auffindbar, aus `important:` entfernt statt geraten.

## Offene GM-Fragen (`sources/Kanon_Entscheidungen.md`)

`dunkler_paladin`/`belorus` (dieselbe Figur?) · `vora`/`voras` · `gilde_in_breska` (Faktion oder Ort?) · `untote_armee_von_steinbachtal` + `untote_horde_von_zebras` (eigene Verbände oder Teil der einen Armee?) · `rotunas_freunde`/`gefaehrten_von_rotunas` · `schlangenfigur`/`schlangengott` · `miaomani`/`miyamani` (Begründung veraltet) · `ringtal`/„Kleinringtal" (zwei Orte, ein Slug) · `der_waechter`/`waechter_des_berges` · Nachfolger für `deities/gruul` und `deities/sitravil`.

## Verifikationsstatus

Vor jeder Änderung aufgenommen (Ist-Zustand): **2 Tests bereits rot**, unabhängig von dieser Arbeit — `test_every_ruling_reaches_at_least_one_entity` (11 vs. Baseline 9) und `test_unlinked_mentions_have_not_grown` (2485 vs. Baseline 1871). Repo-Drift, nicht Teil dieses Audits.

Nach allen Code- und Regeländerungen, **ohne** `pnp run` (siehe unten):

```
13 failed, 157 passed, 1 xfailed
```

Die 13 roten Tests sind **erwartet und namentlich in `test_audit_2026_08_29.py` sowie den beiden oben genannten Vorbestehenden begründet** — jede prüft entweder eine Bundle-Datei, die erst ein `pnp run` neu schreibt (z. B. `test_named_duplicates_are_merged_away`, `test_ignore_rules_are_honoured`), oder `entity_registry.yaml`, das ebenfalls generierte Ausgabe ist (`test_important_flag_reaches_the_generated_registry`). Keiner davon ist ein Fehler in dieser Umsetzung — sie sind der Nachweis, dass die Regeln korrekt formuliert sind und auf einen Lauf warten.

**Blocker: `pnp run` konnte in dieser Session nicht ausgeführt werden — kein `DEEPSEEK_API_KEY` verfügbar.** Alle Code- und Regel-Änderungen sind fertig und durch Unit-Tests abgesichert; die eigentliche Bundle-Regeneration (Merges vollziehen, neue Deep-Tier-Einträge synthetisieren, Autolinker auf bestehende Cache-Bodies anwenden) steht noch aus. Nächster Schritt für die Person mit API-Zugang:

```
cd services/kb
python -m pnp run
python -m pytest -q   # sollte auf 0 offene test_audit_2026_08_29.py-Fehler sinken
```

Nach dem Lauf: Ratchets in `test_link_coverage.py` (`DEEP_TIER_NO_LINK_BASELINE`, `UNLINKED_MENTION_BASELINE`) und `test_rules_applied.py` (`ARTICLE_VARIANT_BASELINE`, `DEAD_RULES_BASELINE`) neu messen und senken — nie anheben, um einen Test grün zu machen.
