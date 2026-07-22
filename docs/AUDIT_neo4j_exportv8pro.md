# Forensischer Audit — Neo4j Knowledge-Graph-Export `neo4j_exportv8pro.json`

**Prüfgegenstand:** 1 Graph-Export (383 Nodes / 1358 Relationships) gegen 12 Session-Transkripte (2025-03-26 bis 2025-06-17, Whisper-Segmente).
**Prüfdatum:** 2026-07-12 · **Methode:** Deterministische Struktur-/Identitäts-/Temporalanalyse des Exports + Volltext-Verifikation gegen die Transkripte.

> **Wichtige Rahmenbedingung / Zuordnung:** Der Export ist **nicht** eine einzelne Session, sondern der **kampagnenweite Graph über alle 12 Sessions**. Die `evidence_chunks`-Integer verweisen auf **abgeleitete Semantic-Chunks**, deren Grenzen weder im Export noch in den Transkripten enthalten sind. Belegprüfung erfolgte daher per **Volltextsuche pro Session**, nicht per Chunk-Index. Der im Architekturkonzept beschriebene **Vector-/`:Chunk`-Layer samt `MENTIONS`-Kanten ist in diesem Export vollständig abwesend** — alle 383 Nodes tragen ausschließlich das Label `:Entity`. Das Bindeglied der beschriebenen GraphRAG-Struktur ist damit hier nicht auditierbar.

---

## 1. Executive Assessment

- **Gesamturteil: REVIEW ERFORDERLICH** (kanonisch nutzbar, aber vor RAG-Einsatz bereinigungsbedürftig)
- **Datenqualität: 6/10**
- **Evidenztreue: 7/10** — Kernfakten gut belegt; punktuelle Überinterpretation + mind. 1 erfundener Name + 1 Scheinentität
- **Ontologie-Konsistenz: 5/10** — Freitext-Status, nicht-eindeutiger Alias-Index, granulare Singleton-Kantentypen
- **Redundanzrisiko: hoch** — 880 von 1358 Kanten (65 %) sind reine Teilnahme-/Session-Telemetrie
- **Zeitlichkeitsrisiko: mittel** — `valid_from/valid_to`-Versionierung ist vorhanden und funktioniert, aber `status` als Freitext untergräbt die Validierbarkeit

**Wichtigste drei Befunde:**
1. Der **Alias-Index ist nicht eindeutig** (10 Namensstrings zeigen auf mehrere Character-Nodes) und es existieren **mehrere bestätigte Duplikate** (Tindra/Tindrael, Perry, Belorus, Zebros) — das gefährdet Entity-Resolution und RAG-Retrieval direkt.
2. **65 % aller Kanten sind Telemetrie**: `PARTICIPATED_IN` (614) + `IN_SESSION` (266); `IN_SESSION` **dupliziert die `session_id`-Property** der Nodes und enthält mindestens **eine widersprüchliche Kante** (Event 2025-06-03 → Session 2025-03-26).
3. **`Item.status` ist unkontrollierter Freitext** (ganze Sätze statt Enum) und die Entität **„Brass" ist eine Scheinentität**, entstanden aus einer als Name fehlinterpretierten Umgangssprach-Interjektion.

---

## 2. Modellinventar

| Elementtyp | Typ/Label | Anzahl | Beobachtung |
|---|---|---:|---|
| Node | `:Entity` (alle) | 383 | Einheitliches Label; kein `:Chunk`/Vector-Layer im Export |
| Node.type | Event | 130 | Makro-Events; `significance` = Freitext-Begründung (kein Level) |
| Node.type | Character | 79 | 5× `is_pc=true` (siehe F-D10: Esterossa fehlt); 20 generische Platzhalter |
| Node.type | Location | 51 | `description`+`valid`-Versionierung teils vorhanden |
| Node.type | Item | 41 | `status` = **Freitext** (siehe F-O4) |
| Node.type | RuleEntity | 29 | Daggerheart-SRD (`session_id="SRD"`) — Regel-/Provenance-Layer |
| Node.type | Quest | 22 | `status` ∈ {open, completed, new} |
| Node.type | Session | 12 | 1 Node pro Transkript |
| Node.type | Faction | 12 | — |
| Node.type | Player | 7 | Deniz=GM, 6 Spieler; getrennt von Character (gut) |
| Rel | PARTICIPATED_IN | 614 | Character→Event (610); **45 % aller Kanten** — Teilnahme-Telemetrie |
| Rel | IN_SESSION | 266 | Event→Session (131) + Character→Session (135); **redundant** (F-R1) |
| Rel | LOCATED_IN | 160 | Character→Location (125, temporal), Location→Location (19, Containment), Item→Location (13) |
| Rel | AT_LOCATION | 93 | Event→Location — Schauplatz; **nicht** redundant zu LOCATED_IN |
| Rel | OWNED_BY | 43 | Item→Character, mit valid_from/valid_to |
| Rel | HOSTILE_TO / ALLIED_WITH | 40 / 18 | gerichtet, keine inverse Dopplung |
| Rel | KNOWS | 22 | 3 Paare **bidirektional doppelt** gespeichert (symmetrisch) |
| Rel | USES / HAS_FEATURE / HAS_CLASS / HAS_ANCESTRY / HAS_SUBCLASS / USES_CARD | 21/10/4/6/2/3 | Character→RuleEntity (Char-Sheet); teils Singleton |
| Rel | MEMBER_OF / SUBQUEST_OF / DIRECTS | 16 / 12 / 12 | DIRECTS = 12× Deniz→Session (F-R8) |
| Rel | RESULTED_IN / TRIGGERED / FEARS | 6 / 1 / 3 | **TRIGGERED = Singleton** (1 Kante) |

**Konfidenz-Verteilung der Nodes:** `high` 53 / `medium` 330 (86 % medium) — hohe Extraktionsunsicherheit, spricht für systematisches Human-Review der `medium`-Klasse.

**Konzept↔Implementierung-Drift:** Das Architekturdokument nennt `narrative_significance_reasoning`, `character_summary`, `rolls_by_scene`. Im Export existieren stattdessen `significance` (= die Reasoning-Prosa), `pending_notes` (Character-Zusammenfassung) und **kein** Roll-Property. Würfelwürfe werden vollständig verworfen — konform zur „keine Telemetrie"-Regel, aber abweichend vom dokumentierten Feldnamen.

---

## 3. Befundliste

| ID | Schwere | Typ | Export-Referenz | Transkript-Evidenz | Befund | Empfehlung | Sicherheit |
|---|---|---|---|---|---|---|---|
| R1 | HOCH | REDUNDANT_RELATIONSHIP | `IN_SESSION` (266 Kanten) | — (strukturell) | Event→Session dupliziert `Event.session_id` (130/131 identisch); Character→Session zu 128/135 aus PARTICIPATED_IN ableitbar | REMOVE (Event→Session) / DEFER (Character→Session als Provenance prüfen) | hoch |
| R2 | HOCH | TEMPORAL_ERROR | `IN_SESSION`: `EVT …Tentakel-Monster` (session_id 2025-06-03) → `SESS_2025-03-26` | Event gehört inhaltlich zu 2025-06-03 | Kante widerspricht der Node-Property → Datenintegritätsfehler; belegt das Risiko redundanter Provenance | REMOVE / REQUIRE_REVIEW | hoch |
| R3 | MITTEL | REDUNDANT_RELATIONSHIP | `PARTICIPATED_IN` (614) | z. B. Dodo in 9/12 Sessions belegt | 45 % aller Kanten; korrekt, aber Volumen-Treiber. Nutzen v. a. für „wer war in Szene" | KEEP, aber als kompaktes Event-Attribut (`participant_ids[]`) statt Einzelkanten erwägen | mittel |
| O4 | HOCH | ONTOLOGY_ISSUE | `Item.status` (41 Items) | — | `status` ist Freitext (ganze Sätze, z. B. „bei Cookie — enthält Informationen darüber, warum es im Schloss Untote gibt") statt Enum → nicht abfragbar/validierbar | CONVERT: kontrolliertes Enum + Freitext in `status_note` | hoch |
| R5 | MITTEL | ONTOLOGY_ISSUE | `TRIGGERED`(1), `HAS_SUBCLASS`(2), `USES_CARD`(3), `FEARS`(3) | — | Singleton-/Kaum-belegte Kantentypen blähen das Vokabular auf | MERGE/RENAME in generischere Typen (z. B. TRIGGERED→RESULTED_IN-Invers; Card/Feature/Class→`HAS_TRAIT{kind}`) | mittel |
| R6 | NIEDRIG | ONTOLOGY_ISSUE | `USES`: Character→RuleEntity (20) + Character→Item (1) | — | Ein Kantentyp mischt Regelnutzung und Item-Nutzung; Item-Fall überlappt OWNED_BY | CONVERT: USES nur für RuleEntity; Item-Nutzung über OWNED_BY/Event | mittel |
| R7 | NIEDRIG | REDUNDANT_RELATIONSHIP | `KNOWS` (3 Paare doppelt) | — | Symmetrische Beziehung in beiden Richtungen gespeichert | REMOVE Duplikat / als ungerichtet behandeln | hoch |
| R8 | NIEDRIG | REDUNDANT_RELATIONSHIP | `DIRECTS` 12× Deniz→Session | „…als GM Deniz…" | „Deniz ist GM" als 12 Kanten kodiert; `Player.role='GM'` existiert bereits | CONVERT_TO_PROPERTY / DEFER | hoch |
| D1 | HOCH | DUPLICATE | `Tindra` (2025-04-09) ↔ `Tindrael` | „Wer ist dieser Tindrael? Tindrael ist der Grabwächter"; Alias von Tindrael enthält „Tindra" | Zwei Nodes für einen NPC (Grabwächter/Bruder Tindrael) | MERGE → Tindrael | hoch |
| D2 | HOCH | DUPLICATE | `Perry` (2025-04-01) ↔ `Perry das Schnabeltier` (2025-05-27) | „Parry das Schnabeltier" (03-26), „das ist Perry" (04-01) | Selbe wiederkehrende Begleiter-Kreatur | MERGE → Perry | hoch |
| D3 | HOCH | DUPLICATE | `Belorus` ↔ `Belorus der Stille` (beide 2025-05-14) | „dem lieben Belorus dem Stillen … ehemaliger General von Zebros … Belorius, der Belorus" | Selbe Figur (Death Knight / Lord der Burg) | MERGE → Belorus der Stille | hoch |
| D4 | MITTEL | DUPLICATE | `Zebros` ↔ `König Zebros` (2025-05-14) | „König Zebros"; zugleich „Berge von Zebros" (Ort!) | Character-Duplikat; **zusätzlich** Zebros als Region ungemodelt | MERGE (Character) + CONVERT_TO_NODE (Location „Berge von Zebros") | mittel |
| D5 | MITTEL | WRONG_ENTITY / DUPLICATE | `Die Hexe`, `Die grüne Dame` (beide 2025-06-17), `Lanra` (2025-04-15) | Aliasüberlappung „die Hexe"/„die Hack"; „vermeintliche Hexe" (06-17) | Antagonistin über Sessions fragmentiert; Die Hexe ≡ Die grüne Dame sehr wahrscheinlich | MERGE (Hexe/grüne Dame) + REQUIRE_REVIEW (ob = Lanra) | mittel |
| D6 | MITTEL | NAMING_INCONSISTENCY | `Die grüne Dame` | **0 wörtliche Treffer** in allen 12 Transkripten | Node-Name ist nicht transkriptbelegt (Aliase „die Hexe"/„die Hack" schon) | RENAME → „Die Hexe" | mittel |
| D7 | HOCH | WRONG_ENTITY / UNSUPPORTED | `Brass` (Character, 2025-06-03) | „Brass, also der Rodeck antwortet, Brass, entspannt euch" | „Brass" ist eine Umgangssprach-Interjektion (Ärger/Stress), als Name fehlgeparst; zudem als Alias in `Rodek` und `Der Fischer (Cornivum)` injiziert | REMOVE Node + Aliase bereinigen | mittel |
| D8 | MITTEL | DUPLICATE | `Elisa` / `Die Jägerin` / `Die Bogenschützin` | Alias-Kette „die Jägerin"→{Die Jägerin, Elisa}; „Die Bogenschützin"→{Die Bogenschützin, Die Jägerin} | 2–3 Nodes für vermutlich 1–2 NPCs | REQUIRE_REVIEW / MERGE | mittel |
| D9 | HOCH | NAMING_INCONSISTENCY | Alias-Index (10 kollidierende Strings) | — | 10 Namensstrings zeigen auf ≥2 Nodes (u. a. „die katze"→{Adjani,Günther}, „das frettchen", „der magier", „die hack", „tindra", „perry") | Alias-Uniqueness erzwingen (Constraint) + kollidierende Aliase disambiguieren | hoch |
| D10 | MITTEL | WRONG_ENTITY | `Esterossa` `is_pc=false` | „den lieben Basti als Esterossa"; `PLAYS Basti→Esterossa` existiert | PC fälschlich als NPC markiert; 5 `is_pc` vs 6 `PLAYS`-Kanten | CONVERT: `is_pc=true` | hoch |
| D11 | MITTEL | ONTOLOGY_ISSUE | 20 generische Character-Nodes (`Bauer`,`Kerl`,`Dame`,`Wirt`,`Schmied`,`Das Kind`,…) | teils Einmal-Erwähnungen | Widerspricht „keine generischen Entitäten"-Prinzip des Konzepts; `Das Kind` vs `Das gerettete Mädchen` evtl. identisch | REVIEW: Pruning oder Merge nicht-wiederkehrender Platzhalter | mittel |
| O1 | MITTEL | OVERINTERPRETED | `Lanra.pending_notes` | „Mein Name ist Lanra"; „Breschka" nur 1× erwähnt | Name belegt, aber „hinter den Angriffen auf Breschka … per Altar teleportieren" ist kausale Schlussfolgerung, nicht explizit | MARK_AS_CLAIM (niedrigere Konfidenz) | mittel |
| O2 | MITTEL | DUPLICATE | `Kampf gegen den Geist` ↔ `Kampf gegen den Seelengeist` (beide 2025-06-17) | — | Wahrscheinlich dieselbe Szene doppelt als Makro-Event (verletzt „1 Szene = 1 Node") | REQUIRE_REVIEW / MERGE | mittel |
| P1 | HINWEIS | PROVENANCE_GAP | Gesamtexport | — | Kein `:Chunk`/Vector-Layer, keine `MENTIONS`-Kanten → GraphRAG-Bindeglied nicht enthalten/auditierbar | ADD_PROVENANCE (Chunk-Layer exportieren) | hoch |
| P2 | HINWEIS | ONTOLOGY_ISSUE | `pending_notes` (76 Character) | — | Workflow-Statusname („pending") als kanonisches Summary-Feld; 86 % Nodes `confidence=medium` | RENAME → `character_summary` + Review-Gate für `medium` | mittel |

---

## 4. Nicht belegte Graph-Fakten

| Export-Referenz | Graph-Fakt | Einordnung | Empfehlung |
|---|---|---|---|
| `Die grüne Dame` (Name) | Entität heißt „Die grüne Dame" | Nicht ausreichend interpretierbar (0 wörtliche Treffer; Aliase belegt) | RENAME → „Die Hexe" |
| `Brass` (Character) | Eigenständige Figur „Brass" | Widerspricht dem Transkript (Interjektion, kein Eigenname) | REMOVE |
| `Lanra.pending_notes`: „hinter den Angriffen auf Breschka" | Lanra ist Urheberin der Angriffe auf Breschka | In dieser Session unbelegt (kausal erschlossen) | MARK_AS_CLAIM |
| `IN_SESSION` EVT Tentakel-Monster → SESS 2025-03-26 | Event fand in Session 2025-03-26 statt | Widerspricht dem Transkript (Event ist 2025-06-03) | REMOVE |
| `RuleEntity` (29, `session_id="SRD"`) | Daggerheart-Regelentitäten | Wahrscheinlich Vorwissen/SRD (nicht Session-Evidenz) | KEEP als Regel-/Provenance-Layer, klar getrennt |

> Hinweis: „Kein Beleg" führt hier **nicht** zur Löschung von Fakten, die aus früheren Sessions oder dem SRD stammen können. Gelöscht/umbenannt werden nur klar widersprüchliche oder erkennbar fehlgeparste Elemente.

---

## 5. Fehlende oder falsch modellierte Transkript-Fakten

| Transkript-Evidenz | Erwartete Modellierung | Tatsächlicher Zustand im Export | Empfehlung |
|---|---|---|---|
| „den lieben Basti als Esterossa" | Esterossa = PC (`is_pc=true`) | `is_pc=false` | CONVERT (D10) |
| „Berge von Zebros" (Region) | Location „Berge von Zebros" | Nur Character `Zebros`/`König Zebros` | CONVERT_TO_NODE (Location) |
| „Tindrael ist der Grabwächter" | 1 NPC-Node | 2 Nodes (Tindra + Tindrael) | MERGE (D1) |
| „Parry/Perry das Schnabeltier" (wiederkehrend) | 1 Begleiter-Node | 2 Nodes | MERGE (D2) |
| Würfelwürfe (zahlreich, z. B. „Investigation … Eine 13") | bewusst verworfen bzw. `rolls_by_scene` laut Konzept | Kein Roll-Feld vorhanden | KEEP (konform zu „keine Telemetrie"), aber Konzept-Feldname angleichen |
| GraphRAG-Chunks / `MENTIONS` | `:Chunk`-Layer + MENTIONS | Fehlt komplett | ADD_PROVENANCE (P1) |

---

## 6. Redundanz- und Ontologieanalyse

**Welche Relationship-Typen erzeugen unnötiges Graphwachstum?**
`PARTICIPATED_IN` (614) und `IN_SESSION` (266) machen zusammen **65 %** aller Kanten aus. `IN_SESSION` ist der klarste Kandidat: Event→Session dupliziert exakt `Event.session_id` (130/131), Character→Session ist zu 128/135 aus `PARTICIPATED_IN` ableitbar. `DIRECTS` (12) kodiert eine einzelne Tatsache (Deniz=GM) als 12 Kanten.

**Welche Kanten sind doppelt/überlappend?**
`KNOWS` speichert 3 symmetrische Paare doppelt. `USES` überlappt für den Item-Fall mit `OWNED_BY`. `AT_LOCATION` (Event→Location) und `LOCATED_IN` (Character/Item→Location) sind **nicht** redundant — unterschiedliche Endpunkttypen, klare Semantik. `TRIGGERED`(1)/`RESULTED_IN` sind semantisch invers und könnten zusammengeführt werden.

**Welche Teilnahme-Kanten haben langfristigen Nutzen?**
`PARTICIPATED_IN` hat kanonischen Nutzen („wer war in welcher Szene") und sollte **bleiben**, idealerweise verdichtet als Event-Attribut `participant_ids[]` statt als 610 Einzelkanten. `IN_SESSION` ist reine Provenance und gehört in den Provenance-/Claim-Layer (oder gelöscht, da via Property/PARTICIPATED_IN rekonstruierbar).

**Welche Entitäten zusammenführen/umbenennen?**
MERGE: Tindra→Tindrael, Perry→Perry das Schnabeltier, Belorus→Belorus der Stille, Zebros→König Zebros, Die grüne Dame→Die Hexe. REMOVE: Brass. REVIEW: Elisa/Die Jägerin/Die Bogenschützin, Lanra↔Hexe, 20 generische Platzhalter.

**Welche Properties/Relationships temporal versionieren?**
`Item.status` (aktuell Freitext, `status_valid_from` teils vorhanden) → Enum + Versionierung. `MEMBER_OF` (Fraktionswechsel) und `HOSTILE_TO`/`ALLIED_WITH` sollten konsequent `valid_to` führen (bei LOCATED_IN/OWNED_BY bereits vorbildlich umgesetzt: 0 exklusive Zustandskonflikte gefunden).

**Top-5-Ontologie-Regeln mit größtem Qualitätshebel:**
1. **Alias-Eindeutigkeit erzwingen** — jeder Alias/Name darf auf genau einen `:Entity`-Node zeigen (Constraint + Merge-Resolver).
2. **Kontrolliertes Vokabular für `status`** — Enum {found, owned, used, lost, destroyed}; Freitext nur in `*_note`.
3. **`IN_SESSION` abschaffen/degradieren** — Session-Zugehörigkeit lebt in `session_id`-Property + `PARTICIPATED_IN`.
4. **Kantentyp-Konsolidierung** — Singletons (TRIGGERED, USES_CARD, HAS_SUBCLASS) in ein kompaktes Vokabular (`HAS_TRAIT{kind}`, `RESULTED_IN`) überführen.
5. **Name-Provenance-Regel** — Node-`name` muss ein transkriptbelegter String sein; abgeleitete Labels kommen in `descriptor`, nicht in `name`.

---

## 7. Zielbild für diese Pipeline

- **Behalten im kanonischen Graphen:** Characters (nach Merge), Factions, Locations (inkl. Location→Location-Containment), Quests, Makro-Events, `PARTICIPATED_IN` (verdichtet), `OWNED_BY`/`LOCATED_IN`/`MEMBER_OF` mit Versionierung, RuleEntity-Char-Sheet-Kanten.
- **Als Claim mit Provenance speichern:** kausale/erschlossene Aussagen (Lanra↔Breschka), alle `confidence=medium`-Nodes bis zur Bestätigung, Antagonisten-Identität Lanra↔Hexe.
- **Nur im RAG-/Quellenlayer behalten:** `:Chunk`+`MENTIONS` (nachliefern!), Würfelprotokolle, wörtliche Dialoge, `IN_SESSION`-Provenance.
- **Nur nach Human Review übernehmen:** Merges D5/D8, Event-Zusammenlegung O2, Pruning der 20 generischen Platzhalter (D11).
- **Deterministisch validieren:** Alias-Uniqueness, `status`-Enum, `IN_SESSION`↔`session_id`-Konsistenz, `is_pc`↔`PLAYS`-Konsistenz, keine zwei „current"-Zustände exklusiver Relationen.

---

## 8. Priorisierter Maßnahmenplan

| Priorität | Maßnahme | Kategorie | Erwarteter Nutzen | Aufwand |
|---|---|---|---|---|
| 1 | Duplikate mergen (D1–D4) + Brass entfernen (D7) | Datenbereinigung dieser Session | Korrekte Entity-Resolution, saubere Retrieval-Anker | mittel |
| 2 | Alias-Uniqueness-Constraint + Disambiguierung (D9) | Neo4j-Constraints/Schema | Verhindert Mis-Resolution im RAG | mittel |
| 3 | `Item.status` → Enum + `status_note` (O4) | Ontologie | Abfragbar/validierbar; temporale Prüfung möglich | mittel |
| 4 | `IN_SESSION` löschen/degradieren, Konsistenz-Check zu `session_id` (R1/R2) | Deterministische Validierung | −20 % Kanten, behebt widersprüchliche Provenance | niedrig |
| 5 | `is_pc`↔`PLAYS`-Abgleich (Esterossa, D10) | Deterministische Validierung | Korrekte PC/NPC-Trennung | niedrig |
| 6 | Extraktionsprompt: Name-Provenance-Regel + „Interjektion ≠ Name" (D6/D7) | Extraktionsprompt | Weniger erfundene/fehlgeparste Entitäten | mittel |
| 7 | Kantentyp-Konsolidierung (Singletons) (R5/R6) | Ontologie | Kompaktes, wartbares Vokabular | mittel |
| 8 | Chunk-/`MENTIONS`-Layer exportieren (P1) | RAG/Provenance | GraphRAG-Bindeglied auditierbar & nutzbar | hoch |
| 9 | Human-Review-Gate für `confidence=medium` + Event-Merge O2 (P2) | Human-in-the-loop | Reduziert Überinterpretation | laufend |

### Drei Akzeptanztests für die nächste Session

1. **Alias-Eindeutigkeit:** Eine Cypher-Prüfung findet **0** Namens-/Alias-Strings, die (case-insensitiv) auf mehr als einen `:Entity`-Node zeigen. *(Aktuell: 10 Kollisionen — Test schlägt fehl.)*
2. **Provenance-Konsistenz:** Für **jede** `IN_SESSION`-Kante (falls beibehalten) gilt `startNode.session_id == endNode.session_id`, und jeder `PLAYS`-Zielnode hat `is_pc=true`. *(Aktuell: 1 IN_SESSION-Widerspruch + Esterossa `is_pc=false` — Test schlägt fehl.)*
3. **Kontrolliertes Vokabular:** `Item.status` und `Quest.status` enthalten **ausschließlich** Werte aus dem definierten Enum; jeder Freitext liegt in `*_note`. *(Aktuell: `Item.status` ist Freitext — Test schlägt fehl.)*

---
*Methodik-Transparenz: Alle strukturellen Zahlen stammen aus deterministischer Auswertung des Exports; alle Zitate aus Volltextsuche in den 12 Whisper-Transkripten. Fehlende Chunk-Grenzen bedeuten, dass einzelne `evidence_chunks`-Verweise nicht positionsgenau, sondern nur inhaltlich verifiziert wurden.*
