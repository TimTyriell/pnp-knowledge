# Qualitätsanalyse Knowledge-Graph-Extraktion — Session 2025-03-26 (Daggerheart S01)

Analysiert: `neo4j_datav1071120250326.json` (Neo4j-Pfad-Export, dedupliziert: **135 Knoten, 274 Kanten**) gegen das Roh-Transkript `20250326_RF_ROCKGeeRUFw.json` (472 Whisper-Segmente, ~82.500 Zeichen). Als Referenz-Soll diente der manuell erstellte Opus-Report (`Session_Report_S01_20250326.md`).

---

## Executive Summary

Die Extraktion leidet weniger unter klassischen Duplikat-Kanten (es gibt **null** exakte Duplikate mit gleichem Start/Ziel/Typ) als unter drei strukturellen Problemen: **(1)** ~74 % aller Kanten (203 von 274) sind Buchhaltungs-Kanten ohne narrativen Informationswert (`PARTICIPATED_IN`, `MENTIONED_IN`, `IN_SESSION`, `KNOWN_FOR`, `APPEARS_IN`), **(2)** die Ontologie wird nicht durchgesetzt — Relationstypen werden semantisch falsch verwendet (`GM ROLLED Cookie`, `Dodo LOCATED_IN Cookie`, `Dodo HAS_CLASS Daggerheart`) und es existieren Inverse-Paare (`OWNS` + `OWNED_BY`) sowie ein `RELATES_TO`-Sammelbecken, **(3)** die Entity-Ebene ist kontaminiert: mindestens 5 der 10 Character-Knoten sind Halluzinationen oder Duplikate real existierender Figuren (Transkriptions-Rauschen, Twitch-Raid als NPC, Cookies Frosch-Ancestry als eigener NPC), und die dokumentierte Sprecher-Vertauschung wurde ungefiltert übernommen (Dodo `HAS_CLASS` Ranger). Dein Verdacht „Übertracking" bestätigt sich also, aber die größere Baustelle ist Schema-Enforcement + Entity-Resolution, nicht die reine Kantenmenge.

**Nachtrag (bestätigt vom Auftraggeber):** Für diesen Testlauf wurde bewusst nur das letzte Drittel des Transkripts eingespeist (118 von 472 Segmenten, ~30.000 Zeichen, Kampf bis Session-Ende). Der ursprüngliche Befund „Charaktererstellung fehlt komplett" ist damit **kein Extraktionsfehler**, sondern erwartbar für diesen Input, und entfällt als Kritikpunkt. Zugleich erklärt die daraus resultierende Chunk-Größe (~32 Chunks auf diesem Drittel → **~900 Zeichen / ~250 Tokens pro Chunk**) einen Großteil der übrigen Befunde mechanisch: Mikro-Events (43 Events in 33 Spielminuten), Entity-Duplikate durch fehlenden Kontext (Dragonborn/Goblin statt Dodo) und MENTIONED_IN-Spam an Chunk-Grenzen. Details in Abschnitt 4.

**Kennzahlen:**

| Metrik | Wert | Einordnung |
|---|---|---|
| Knoten (unique) | 135 | davon 43 Event + 36 Trait = 59 % „Mikro-Knoten" |
| Kanten (unique) | 274 | Summe der Stats-CSV bestätigt |
| Edge-to-Node-Ratio | **2,03** | für narrative KGs normal (üblich 1,5–3) — das Ratio ist unauffällig; das Problem ist die *Zusammensetzung* |
| „Content"-Kanten (narrativ aussagekräftig) | ~71 (26 %) | Rest: Buchhaltung/Bag-of-Words |
| Exakte Duplikat-Kanten (Start/Ziel/Typ identisch) | **0** | ✅ |
| Semantische Duplikate (gleicher Fakt, mehrfach modelliert) | ≥ 6 Muster | s. Abschnitt 3 |
| Halluzinierte/duplizierte Entitäten | ≥ 8 Knoten | s. Abschnitt 2 |

---

## 1. Ontologie-Sinnhaftigkeit

Grundgerüst (Entity-Label + `type`-Property, Session-Knoten, Player↔Character via `PLAYS`) ist brauchbar. Die Umsetzung bricht aber an vielen Stellen:

| Problem | Beispiel (id / identity) | Empfehlung |
|---|---|---|
| **Trait-Knoten-Inflation**: 36 Trait-Knoten (27 % aller Knoten!), jeder exakt 1× über `KNOWN_FOR` angebunden, teils OOC-Spielerverhalten statt Charaktereigenschaft | `TRAIT_LindoLaut_AsksClarifyingQuestionsAboutGameMechanics`, `TRAIT_LindoLaut_EncouragesPlayerAgencyAndOpenEndedActions` (stammt aus Tims Meta-Feedback am Sessionende, Seg. 467–469 — Spieler-, nicht Charakterverhalten) | Traits als **Array-Property am Character** (`traits: [...]`), nicht als Knoten. Nur promoten, wenn ≥2 unabhängige Belege. OOC-/Meta-Aussagen explizit ausschließen |
| **Relationstypen ohne Domain/Range-Constraints**: Typen werden auf beliebige Knotenpaare angewandt | `CHAR_Deniz_GM -ROLLED-> CHAR_Cookie` (ein Charakter „würfelt" einen Charakter), `CHAR_Dodo -LOCATED_IN-> CHAR_Cookie`, `CHAR_LindoLaut -DECIDED-> CHAR_Dragonborn`, `CHAR_Dodo -RESULTED_IN-> EVT_DodoMovesThePott`, `QUEST_DefeatingTheMonster -RESULTED_IN-> LOC_MonsterSLair` | Pro Relationstyp erlaubte (Quelle→Ziel)-Typpaare definieren und **im Prompt als Tabelle mitgeben + nach Extraktion validieren** (Kante verwerfen bei Verstoß) |
| **`HAS_CLASS` semantisch entkernt** | `CHAR_Dodo -HAS_CLASS-> RULE_SYSTEM_DualityDice`; alle 4 Chars `HAS_CLASS` → `RULE_GAMESYSTEM_Daggerheart` (System ≠ Klasse); `CHAR_Dodo -HAS_CLASS-> RULE_CLASS_Ranger` (falsch: Dodo ist Guardian — Sprecher-Swap) | `HAS_CLASS` nur Character→RuleEntity(subtype=Class). Für System: gar keine Kante (Session-Property genügt) |
| **Inverse Relationspaare koexistieren** | `OWNS` (2×) und `OWNED_BY` (4×) gleichzeitig im Schema; sogar `ITEM_Kessel -OWNS-> ITEM_Beschwoerungsfluessigkeit` (Item besitzt Item) | Eine Richtung festlegen (`OWNS`: Character→Item), Inverse verbieten — Neo4j kann in beide Richtungen traversieren |
| **`RELATES_TO` als Sammelbecken** mit `original_predicate`-Property | `INSPIRES`, `CALLS_FOR`, `SPOKEN_TO`, `TAKES_DAMAGE_FROM`, `FELT_BETTER` (→ `CHAR_Dodo -RELATES_TO{FELT_BETTER}-> ITEM_Melodie`) | Entweder Prädikat auf kleines Whitelist-Vokabular mappen oder Kante verwerfen. Ein Catch-all-Typ macht Queries wertlos |
| **RuleEntity-`subtype`-Wildwuchs** | `"System"`, `"game system"`, `"game-rule"`, `"game-mechanic"`, `"attribute"`, `"weapon trait"`, `"game-resource"`, `"Class"` … zusätzlich Long Rest in 5 Einzelknoten explodiert (`RULE_GAMERULE_TendToAllWounds`, `…ClearAllStress`, `…RepairAllArmor`, `…Prepare`) | Geschlossene Subtype-Enum (Class, Subclass, Ancestry, Community, DomainCard, Feature, Mechanic, System). Long-Rest-Optionen sind Properties eines Knotens, keine 5 Knoten |
| **Nicht-Entitäten als Item/Location** | `ITEM_Melodie` (ein gespielter Song ist kein Gegenstand), `ITEM_Waffe` (generisch, neben `ITEM_Breitschwert` = Duplikat), `LOC_Baum`, `LOC_Gebuesch` (Kulisse, keine Orte), `LOC_LocationWhereTheMonsterWasDefeated` (identity 30 — beschreibende Phrase als Knoten-ID) | Item nur bei Besitz-/Verwendungs-Relevanz über die Szene hinaus; Location nur benannte, wiederbesuchbare Orte |
| **Event-Begriff zu weit**: 43 Events, darunter Überlegungen, Regelerklärungen, Stream-Meta | `EVT_DodoConsidersUsingAHealingAbilityInTheirNextTurn`, `EVT_CookieQuestionsEngagement…`, `EVT_WuerfelwaechterAreMentioned`, `EVT_GMAcknowledgesInabilityToMoveInCinemaMode`, `EVT_ClarificationOfHopePointRule` | Event nur bei **Zustandsänderung** (Schaden, Item-Erwerb, Quest-Statuswechsel, folgenreiche Entscheidung). Regelerklärungen → gar nicht oder als OOC-Flag. Ziel: 5–10 Kern-Events pro Session statt 43 Mikro-Events (Events hängen weiterhin nur an `Session`, keine Zwischenebene) |
| **Fehlende Typen/Entitäten** (False Negatives auf Ontologie-Ebene) | Kein Companion-Knoten (Parry!), keine Faction/Gruppe, keine Quest-Knoten für „Belohnung abholen"/„Botschaft verfolgen", kein Decision-Typ, kein Troubadour, kein Ribbet | Companion, Quest (mit `status`), Decision als Typen aufnehmen — der Opus-Report zeigt das Zielschema bereits |

**Event vs. Kante:** Die Trennung ist im Prinzip da (RollEvents, Kampf-Events), wird aber doppelt geführt: derselbe Fakt existiert oft als Event-Knoten *und* als direkte Kante *und* als Trait (Beispiel unten: „reliable"). Faustregel fürs Schema: Fakten mit Zeitpunkt/Verlauf → Event-Knoten; zeitlose Zuordnungen (Klasse, Besitz, Mitgliedschaft) → Kante; Beobachtungen/Deskriptives → Property.

---

## 2. Datenqualität im Vergleich zum Transkript

Stichproben via `evidence_chunks` + Volltextsuche im Transkript. Positiv: viele Kampf-Events sind akkurat (z. B. `EVT_DodoMovesThePott` ↔ Seg. 316 „du schaffst es tatsächlich, den Pott zu bewegen… Gebräu stark am Brodeln"; `EVT_DefeatingTheMonster` ↔ Seg. 441 „direkt in sein großes Glubschauge… Monster legt sich schlafen"; `EVT_MonsterWithTackleMarkingIdentified` ↔ Seg. 445). Aber:

| Node/Relation (identity) | Diskrepanz zum Transkript | Schweregrad |
|---|---|---|
| `EVT_ChickenAppears` (51) + Kante `CHAR_Deniz_GM -TRIGGERED->` | **Korrigiert nach erneuter Prüfung mit vollständigem Chunk-Kontext:** keine freie Erfindung, sondern Vermischung von VTT-Bedienungssprache und Fiktion. Wörtlicher Beleg: GM sagt beim Kampfstart „Wir gehen in den Kampfmodus, Turn-Based-Mode. Aber da ist nur das Chicken drin", Marco: „Jawohl, nur ich und das Chicken" — gemeint ist vermutlich ein Platzhalter-Token/Demo-Figur im Talespire-Turn-Tracker, nicht das eigentliche Tentakel-Monster. Der Extraktor hat Tool-Bedienung und Spielfiktion zu einem Event verschmolzen, weil der kleine Chunk beides im selben Satzfenster enthält, ohne dass Regel-/Werkzeug-Sprache von Fiktion getrennt wird | 🟠 mittel (Fehlklassifikation Tool-Talk↔Fiktion, keine reine Halluzination) |
| `CHAR_Kieler` (24, role „NPC") | Existiert nicht. Einziger Beleg Seg. 433: „…und Kieler mitbeugen von Marco…" — unverständliches ASR-Rauschen wurde zum NPC samt `TARGETS`-Kante (`CHAR_LindoLaut -TARGETS-> CHAR_Kieler`) | 🔴 hoch |
| `CHAR_Wuerfelwaechter` (22, role „NPC") | „Würfelwächter" ist die **Twitch-Community, die die Runde geraidet hat** (Seg. 389: „Wir wurden gerade geraidet"), kein NPC der Spielwelt. Dazu ein eigenes Event `EVT_WuerfelwaechterAreMentioned` | 🔴 hoch |
| `CHAR_Frosch` (25, role „NPC") | „der Frosch" = Cookie (Ribbet-Ancestry, Seg. 165, 435). Duplikat eines PCs als NPC | 🔴 hoch |
| `CHAR_Dragonborn` (21, role „PC", is_pc=true) + `CHAR_Goblin` (23, role „adversary"!) | Beides Fragmente von **Dodos Ancestry** („halb Goblin, halb Drache"). Folge: Dodo existiert 3× als Akteur; `EVT_DragonbornChargesAtMonster` dupliziert `EVT_DodoAttacksAMonsterWithTheBreitschwert`; absurde Kante `CHAR_Dodo -HAS_ANCESTRY-> CHAR_Dragonborn` (Character als Ancestry-Ziel); Goblin als „Gegner" ist schlicht falsch | 🔴 hoch |
| `EVT_GMEndsSessionTemporarily` (54) | „The GM announces they are going to sleep and asks Dodo to continue" — tatsächlich verabschiedet sich **Chat-Zuschauer Jonas** (Seg. 359: „Jonas, das ist der Zeitpunkt, an dem ich schlafen gehe" = GM liest Chat vor). Verzerrte Zusammenfassung eines Nicht-Ereignisses | 🟠 mittel |
| `EVT_MarcoTakesTheHitInsteadOfDodo` (61) + `EVT_EnemyFocusesOnMarco` (62) | Marco **ist** Dodos Spieler — „Marco fängt den Treffer statt Dodo ab" ist logisch unmöglich. Real: Dodo schützt Lindo Laut via „I Am Your Shield". Spieler- und Charakternamen wurden als getrennte Akteure geführt | 🔴 hoch |
| `CHAR_Dodo -HAS_CLASS-> RULE_CLASS_Ranger` | Dodo ist Guardian, Ranger ist Cookie — direkte Folge der dokumentierten **Sprecher-Label-Vertauschung**, ungefiltert übernommen. Gleiches Muster: `TRAIT_Dodo_PlaysMusicOften` (116), `TRAIT_Cookie_InspiringWords` (120), `TRAIT_Cookie_PlaysMelodieOften` (143) — Musik/Inspiring Words gehören zum Barden Lindo Laut | 🔴 hoch |
| `confidence`-Property | Praktisch alles „high", auch die Halluzinationen: `CHAR_Kieler -APPEARS_IN-> SESS` mit confidence=high, `TRIGGERED-> EVT_ChickenAppears` high. Confidence ist **nicht kalibriert** und aktuell wertlos als Filter | 🟠 mittel |
| `evidence_chunks` | Die 3 PCs haben pauschal `[1…32]` (= „überall"), der GM dagegen nur `[5,10,14,21,23]` — invertiert zur Realität (der GM redet am meisten). Als Beleg-Referenz unbrauchbar | 🟠 mittel |
| ~~False Negatives: Charaktererstellung fehlt komplett~~ **(entfällt — kein Fehler)** | Chunk 1 ≈ Seg. 311 („Pott bewegen"), Chunk 31 ≈ Seg. 465 (Long Rest) deckt exakt den bewusst gewählten Test-Input ab (letztes Drittel, Kampf bis Sessionende). Dass Companion (Parry), Troubadour, Ribbet, Ancestry/Community-Zuordnungen, Experiences und der „Zwiebelringe"-Gag fehlen, liegt am Input, nicht an der Pipeline. Im Vollbetrieb (ganzes Transkript) muss dieser Teil erneut geprüft werden | ⚪ n/a |

---

## 3. Edge-Redundanz und Übertracking

**Exakte Duplikate (gleiches Knotenpaar, gleicher Typ, mehrere Relationship-IDs): 0.** Dein Verdacht bestätigt sich trotzdem — als *strukturelles* Übertracking:

Redundante/informationsarme Edge-Patterns (nach Volumen):

1. **`PARTICIPATED_IN` (69 Kanten, 25 % aller Kanten)** — GM-Rauschen: `CHAR_Deniz_GM` „beteiligt" an **28 von 31** Events mit Teilnehmern — nur weil er als GM jede Szene narriert. Diese 28 Kanten tragen null Information (der GM leitet per Definition alles). Beispiel: `CHAR_Deniz_GM -PARTICIPATED_IN-> EVT_DodoMovesThePott` — der GM hat den Pott nicht bewegt. Nur 2 Events haben alle 3 PCs als Teilnehmer, d. h. das Muster „jeder Anwesende an jedes Event" liegt (noch) nicht vor — es ist spezifisch ein **GM-Problem** plus Teilnahme = „hat im Chunk gesprochen".
2. **`MENTIONED_IN` (45 Kanten)** — Bag-of-Words-Kanten „Sprecher X hat Begriff Y im Chunk erwähnt", Richtung zudem verdreht (Character→RuleEntity heißt hier „Character mentioned in RuleEntity"?). Allein die Session-End-Rekapitulation (Chunks 31–32) erzeugt **~25 Kanten** wie `CHAR_Deniz_GM -MENTIONED_IN-> RULE_GAMERULE_RepairAllArmor`. Empfehlung: Typ komplett streichen; Erwähnungen gehören als `evidence_chunks`-Property an den Zielknoten.
3. **`IN_SESSION` (43 Kanten)** — jedes Event → den einen Session-Knoten, während *jeder* Knoten zusätzlich die Property `session_id: "2025-03-26"` trägt. Doppelte Buchführung; eins von beiden reicht (Empfehlung: Kante behalten für Cross-Session-Queries, Property als Index-Feld ok — aber dann `APPEARS_IN` für Characters konsistent halten statt drei Mechanismen).
4. **`KNOWN_FOR` (36 Kanten)** — 1:1-Anhängsel der Trait-Knoten-Inflation (jede Kante genau einmal benutzt). Fällt mit Traits-als-Property ersatzlos weg.
5. **Inverse-Paar-Duplikat:** `ITEM_Schriftrolle -OWNED_BY-> CHAR_Cookie` (relId 15) **und** `CHAR_Cookie -OWNS-> ITEM_Schriftrolle` (relId 170) — derselbe Fakt als zwei Kanten zwischen demselben Knotenpaar. Das ist das einzige echte „Duplikat", nur eben über zwei Typnamen versteckt.
6. **Mehrfachmodellierung desselben Fakts über Ebenen** — Paradebeispiel „reliable": (a) Trait-Knoten `TRAIT_ITEMWaffe_Reliable` (130) + `KNOWN_FOR`, (b) `ITEM_Waffe -HAS_FEATURE-> RULE_WEAPONTRAIT_Reliable`, (c) Event `EVT_DodoSWeaponHasAReliableTrait` — **ein Fakt, drei Knoten + drei Kanten**. Ebenso Rally: `CHAR_LindoLaut -HAS_FEATURE-> RULE_FEATURE_Rally` (relId 183) + `-USES->` (relId 184) + `RULE_FEATURE_Rally -RESULTED_IN-> EVT_LindoLautUsesRallyFeature` + Trait `TRAIT_LindoLaut_UsesRallyFeature…`.
7. **Entity-Duplikate erzeugen Folge-Kanten-Duplikate:** `ITEM_Pott` (33) vs. `ITEM_Kessel` (40) — dasselbe Objekt; `ITEM_Waffe` (36) vs. `ITEM_Breitschwert` (35); `CHAR_Dodo` vs. `CHAR_Dragonborn` (21) führt zu `USES ITEM_Breitschwert` **zweimal** (einmal pro Alias).

**Bilanz:** 203 von 274 Kanten (74 %) entfallen auf die Typen 1–4. Nach Bereinigung (GM-Teilnahmen raus, MENTIONED_IN raus, KNOWN_FOR raus, Traits als Properties, Entity-Merge) bliebe ein Graph von grob **~55–65 Knoten / ~100–120 Kanten** mit gleichem oder höherem Informationsgehalt — nahe am Opus-Referenzreport (40 Knoten / 30 Kanten, bewusst kompakter).

---

## 4. Chunking als Root Cause

Bestätigt durch den Auftraggeber: Der Testlauf verarbeitete nur das letzte Drittel des Transkripts (118 von 472 Segmenten, ~30.000 Zeichen, ~33 Spielminuten) in 32 Chunks — **~900 Zeichen bzw. ~250 Tokens pro Chunk**, das entspricht 3–4 Sprechersegmenten. Diese Chunk-Größe erklärt mechanisch drei der oben beschriebenen Befunde:

1. **Mikro-Events statt Szenen-Events.** Ein Chunk pro ~60 Sekunden Gespräch zwingt den Extraktor, aus jeder Überlegung ein Event zu machen („Dodo considers healing options"), weil er pro Chunk „etwas liefern" soll. Ergebnis: 43 Events auf 33 Minuten = ein Event alle 46 Sekunden, viele davon ohne Zustandsänderung (s. Abschnitt 1).
2. **Entity-Duplikate durch fehlenden Kontext.** Chunk 8 enthält nur „der Dragonborn bzw. der halb Goblin, halb Drache darf anfangen" — ohne den Kontext, dass das Dodo ist (der aus einem früheren Chunk bekannt wäre, den der Extraktor aber nicht mehr sieht). So entstehen `CHAR_Dragonborn`, `CHAR_Goblin`, `CHAR_Frosch` als scheinbar neue Figuren, weil jeder Chunk isoliert mintet, was er nicht auflösen kann.
3. **`MENTIONED_IN`-Spam an Chunk-Grenzen.** Kleine Chunks bedeuten viele Chunk-Grenzen; jede Begriffserwähnung wird pro Chunk neu verkantet, statt einmal pro Entität konsolidiert zu werden.

**Empfehlung: größere, an Szenengrenzen ausgerichtete Chunks für die Extraktion — aber Szenen bleiben ein reines Chunking-Konstrukt und tauchen NICHT als Knoten im Graphen auf.** Konkret:

- Chunkgröße auf **2.000–4.000 Tokens mit ~15 % Overlap** erhöhen. Für dieses Drittel wären das 3–5 Chunks statt 32.
- Vor der eigentlichen Extraktion einen billigen Pass laufen lassen, der Szenenwechsel im Transkript markiert (Kampfbeginn, Kampfende, Loot/Untersuchung, Wrap-up — hier ~4–5 Abschnitte). Diese Szenengrenzen dienen **ausschließlich als Chunk-Trennlinien für die Verarbeitung**, damit der Extraktor pro Aufruf eine abgeschlossene Handlungseinheit mit genug Kontext sieht.
- **Im Graphenschema selbst gibt es dafür keinen `Scene`-Knotentyp.** Die einzige Meta-/Container-Referenz bleibt `Session`. Events, Rolls, Decisions etc. hängen weiterhin direkt über `IN_SESSION` an der Session — nicht an einer Zwischenebene „Szene". Falls eine zeitliche Verortung innerhalb der Session gewünscht ist, reicht ein optionales Property am Event (z. B. `sequence`, `approx_time` oder ein informeller `phase`-String), aber kein eigener Knoten mit Kanten.
- **Map-Reduce statt Direkt-Ingest:** Pro (größerem) Chunk zunächst nur Kandidaten extrahieren; danach ein Konsolidierungs-Pass über alle Kandidaten einer Session (Entity-Merge, Event-Zusammenfassung, Kanten-Dedup), und erst dessen bereinigter Output wird nach Neo4j geschrieben. Das verhindert, dass pro Chunk unabhängig in den Graphen geschrieben wird.
- **Laufende Entity-Liste in den Prompt geben** (s. Vorschlag A unten), damit auch bei größeren Chunks Aliasse wie „Dragonborn/Goblin-Drache" korrekt auf `CHAR_Dodo` gemappt werden.

Wichtig: Die Chunkgröße erklärt Granularität und Entity-Duplikate, aber nicht alles — das kaputte Relations-Vokabular, die unkalibrierte Confidence und die ungefilterte Übernahme der Sprecher-Vertauschung (Abschnitte 1–3) sind unabhängige Prompt-/Schema-Probleme, die auch mit optimaler Chunk-Größe bestehen bleiben. Beide Hebel sind nötig.

---

## 5. Konkrete Vorschläge für Extraktions-Prompt & Schema

**A. Zwei-Stufen-Extraktion mit Cast-Registry (wichtigster Fix).**
Gib dem Extraktor pro Session eine kanonische Besetzungsliste mit Aliassen mit (aus Session 1 bootstrappen, danach fortschreiben):
```json
{"cast": [
  {"id":"CHAR_LindoLaut","player":"Tim","aliases":["der Barde","die Fee"],"class":"Bard"},
  {"id":"CHAR_Dodo","player":"Marco","aliases":["Dragonborn","halb Goblin halb Drache","der Guardian"],"class":"Guardian"},
  {"id":"CHAR_Cookie","player":"Celin","aliases":["der Frosch","der Ranger"],"class":"Ranger"},
  {"id":"COMP_Parry","owner":"CHAR_Cookie","aliases":["das Schnabeltier"]}
]}
```
Regel im Prompt: *„Neue Character-Knoten nur anlegen, wenn die Figur nicht per Alias auf die Cast-Liste mappt UND in ≥2 Chunks handelnd auftritt. Spielernamen (Tim, Marco, Celin, Deniz) sind NIEMALS eigene Akteure in Events — immer auf den Charakter mappen."* Das eliminiert Kieler, Frosch, Dragonborn, Goblin, Marco-als-Akteur in einem Schlag. Chat-Zuschauer und Twitch-Meta (Raids, Begrüßungen) explizit als „ignorieren" deklarieren.

**B. Geschlossenes Relations-Vokabular mit Domain/Range, hart validiert.**
Etwa 10 Typen genügen:

| Relation | Quelle → Ziel | Ersetzt |
|---|---|---|
| `APPEARS_IN` | Character → Session | APPEARS_IN, IN_SESSION (für Chars) |
| `IN_SESSION` | Event/Quest → Session | — |
| `PLAYS` | Player → Character | — |
| `HAS_CLASS` / `HAS_SUBCLASS` / `HAS_ANCESTRY` / `HAS_COMMUNITY` | Character → RuleEntity (passender Subtype!) | HAS_FEATURE-Missbrauch |
| `OWNS` | Character → Item/Companion | OWNED_BY |
| `PERFORMED` | Character → Event | PARTICIPATED_IN, RESULTED_IN (Char→Evt), TRIGGERED (Char→Evt) |
| `TARGETS` | Event → Character/Item | TARGETS (Char→Char) |
| `RESULTED_IN` | Event → Event/Item/Quest | Location→Event u. ä. |
| `AT_LOCATION` | Event → Location; `LOCATED_IN` Location → Location | LOCATED_IN (Char→Char) |
| `MEMBER_OF` | Character → Faction | — |

Nach der Extraktion ein deterministischer Validierungsschritt (kein LLM): Kante gegen die Tabelle prüfen, bei Verstoß verwerfen und loggen. Das allein hätte `GM ROLLED Cookie`, `Dodo LOCATED_IN Cookie`, `Char RESULTED_IN Event` und alle HAS_CLASS-Entgleisungen abgefangen.

**Wichtig zum Schema-Umfang:** `Session` ist der einzige Meta-/Container-Knotentyp. Es gibt bewusst **keinen `Scene`-Knoten** — auch wenn die Extraktion intern szenenweise chunkt (s. Abschnitt 4), werden diese Szenengrenzen nicht als Graphstruktur persistiert. Alles, was an eine Szene gebunden wäre, hängt stattdessen direkt an `Session` (über `IN_SESSION`) oder trägt höchstens ein einfaches Ordnungs-Property am Event (z. B. `sequence`), niemals eine eigene Knotenebene.

**C. Event-Schwelle definieren.**
Prompt-Regel: *„Ein Event nur anlegen, wenn mindestens eines zutrifft: (a) HP/Stress/Zustand eines Akteurs ändert sich, (b) ein Item wechselt Besitz oder wird entdeckt, (c) eine Quest ändert ihren Status, (d) eine Entscheidung mit fiktionaler Konsequenz fällt. Regelerklärungen, Überlegungen ohne Ausführung, Chat-Interaktionen und Stream-Technik sind KEINE Events."* Zielgröße nennen: 5–10 Events pro Session. Optional Roll-Details in eine separate CSV (wie im Opus-Report) statt als Knoten.

**D. GM-Sonderbehandlung.**
*„Der GM erhält genau zwei Kanten: PLAYS (Player→GM-Persona) und APPEARS_IN (→Session). Der GM ist niemals PERFORMED-Teilnehmer eines Events, außer er spielt einen benannten NPC."* Spart ~28 der 69 PARTICIPATED_IN-Kanten ersatzlos.

**E. `MENTIONED_IN` und `KNOWN_FOR` streichen.**
Erwähnungen → `evidence_chunks`-Property am erwähnten Knoten. Traits → `traits`-Array-Property am Character, mit Promotion-Regel (≥2 Belege, in-character, keine Meta-Aussagen). Reduziert den Graphen um 81 Kanten + 36 Knoten.

**F. Confidence kalibrieren, evidence erzwingen.**
*„confidence=high nur bei wörtlichem Beleg im Chunk; medium bei Paraphrase; low bei Inferenz. Jede Kante braucht ≥1 konkreten evidence_chunk; Knoten mit evidence_chunks = ‚alle Chunks' sind unzulässig."* Zusätzlich hilfreich: pro Entität ein wörtliches `quote`-Feld verlangen — freie Erfindungen (z. B. `CHAR_Kieler`) können dann kein Zitat liefern, und Vermischungen wie beim Chicken-Event würden durch das Zitat sofort als Tool-Talk statt Fiktion erkennbar.

**G. Im Vollbetrieb das gesamte Transkript verarbeiten.**
Für diesen Testlauf wurde bewusst nur das letzte Drittel eingespeist — kein Bug. Für den produktiven Einsatz aber beachten: Die Charaktererstellung ist für eine Kampagnen-KB die dichteste Faktenquelle der Session (Klassen, Ancestries, Communities, Companion, Experiences). Der Opus-Report belegt, was dort extrahierbar ist — das sollte im nächsten Testlauf mit vollständigem Transkript verifiziert werden.

**H. Post-Processing-Merge als Sicherheitsnetz.**
Nach jeder Session ein Merge-Pass: Knoten mit identischem normalisiertem Namen oder Alias-Treffer (Pott/Kessel, Waffe/Breitschwert) via `apoc.refactor.mergeNodes` zusammenführen; Inverse-Paare auflösen; verwaiste Ein-Kanten-Knoten (Trait-Muster) reporten.

---

*Analyse erstellt am 2026-07-11. Alle identity-Angaben beziehen sich auf den Export (elementId-Präfix `4:cd8406ef-…`). Zahlen reproduzierbar aus dem deduplizierten Pfad-Export; die Stats-CSV (Summe 274) stimmt mit dem Export überein.*