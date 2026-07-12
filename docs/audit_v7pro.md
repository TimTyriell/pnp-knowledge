# Forensisches Audit — Neo4j Knowledge-Graph-Export **v7-pro** (DeepSeek Pro)

**Kampagne:** „Dwarf Masters" (Daggerheart / TaleSpire, DE) · **Sessions:** 2025-04-01, 2025-04-09, 2025-04-15
**Primärevidenz:** 3 Whisper-Transkripte (Speaker-Labels vorhanden)
**Export:** 355 Nodes (247 `:Chunk`, 108 `:Entity`), 2701 Relationships · **Extraktionsmodell:** DeepSeek Pro
**Methodik:** bidirektionaler Abgleich Graph ↔ Transkript, konservativ, quellenbasiert. Transkript = Primärevidenz, Graph = abgeleitet.

> Eigenständiges Audit des empfohlenen Modells. Enthält zusätzlich einen **Token-/Kosten-Optimierungsplan** (§8), da Pro input-lastig ist (viele Cache-Misses).

---

## 1. Executive Assessment

- **Gesamturteil: PASS (mit kleinen Auflagen)**
- **Datenqualität: 8,5/10**
- **Evidenztreue: 9/10**
- **Ontologie-Konsistenz: 8/10**
- **Redundanzrisiko: niedrig**
- **Zeitlichkeitsrisiko: mittel** (temporale Kanten-Properties vorhanden, aber selten „geschlossen")

**Der Graph ist produktionsnah.** Pro liefert einen sauberen GraphRAG-Hybrid: reines `:Entity`-Skelett, `:Chunk`-Vektorlayer, `MENTIONS`-Brücke. Die schweren Probleme früherer Versionen (Decision-Knoten, Quest-Wildwuchs, Regel-Halluzinationen, Rules-Layer-Verschmutzung, 04-01-Lücke) sind gelöst. Besonders stark: **kein Regel-Node trägt Welt-/Kampfkanten** (0 Verstöße), Lugasch ist korrekt als Gottheit in die `Goblin-Götter`-Faction gefaltet (Stream-Mechanik, belegt `[2300]`), Whisper-Duplikate (Tendril, Wirt) sind vermieden, Session-Provenance stimmt (Schleichfurz/Perry → 04-01), und Pro extrahiert sogar korrekt die Ziege **Bertie** (`[1552]` „Ihr habt Bertie gefunden").

**Wichtigste drei offene Auflagen:**

1. **Temporale Zustandskanten werden fast nie geschlossen** (`valid_to` meist null) → veraltete Positionen gelten als „aktuell" (z. B. `Lanra → Krypta`, obwohl sie flieht `[7173]`; `Schleichfurz → Goblinlager` offen seit Session 1). Siehe §7 (R-NEU-9).
2. **Fragwürdige Allianz** `ALLIED_WITH: Goblin-Götter → alle 5 PCs` — die Götter greifen chaotisch/feindlich ein (`[3291]`), „verbündet" ist überinterpretiert.
3. **Handlungsrelevante Kleinst-NPCs fehlen als Knoten** — das gerettete Kind (Quest-Ziel), Schmied und Bauernpaar sind in Events gefaltet; für quest-/retrieval-Zwecke sollten sie materialisiert werden.

---

## 2. Modellinventar

| Elementtyp | Typ/Label | Anzahl | Beobachtung |
|---|---|---:|---|
| Node | `:Chunk` | 247 | RAG-Vektorlayer. Sauber via Label getrennt. |
| Node | `:Entity` | 108 | Weltmodell-Skelett, dedupliziert. |
| Entity | `RuleEntity` | 29 | **Reiner SRD-Kanon** (`source=SRD`, conf=high). Keine Session-Halluzinationen mehr. |
| Entity | `Event` | 28 | Makro-Events, narrativ kohärent segmentiert; keine leeren „Ich bin's!"-Events. |
| Entity | `Character` | 20 | Sauber; PC/NPC via `role`/`is_pc`. Kleinst-NPCs bewusst in Events gefaltet (§5). |
| Entity | `Item` | 10 | `status` als (zeitloser) String → §7. |
| Entity | `Location` | 7 | Gut gemergt (Krypta/Dungeon/Bossraum → 1). |
| Entity | `Player` | 7 | Ohne `session_id` (korrekt kampagnenübergreifend). |
| Entity | `Faction` | 3 | Gilde, Goblin-Armee, Goblin-Götter (inkl. Lugasch). |
| Entity | `Quest` | 1 | 1 Kampagnen-Arc; Sub-Quests (Krypta) nicht separat abbildbar (§6). |
| Rel | `MENTIONS` | 2177 | RAG-Provenance `:Chunk`→`:Entity`. Erwartungskonform. |
| Rel | `IN_SESSION` / `APPEARS_IN` | 275 / 24 | Zwei Provenance-Prädikate (Event vs. Character) → §6. |
| Rel | `PARTICIPATED_IN` | 117 | Character→Event; 04-01-PCs korrekt verknüpft. |
| Rel | `LOCATED_IN` / `AT_LOCATION` | 22 / 21 | Positions- vs. Event-Ort-Kante → §7. |
| Rel | `RESULTED_IN` | 4 | Event→Quest-Konnektivität (gut für Retrieval). |
| Rel | `OWNED_BY` / `MEMBER_OF` / `ALLIED_WITH` / `HOSTILE_TO` | 9 / 4 / 8 / 2 | Zustandskanten → §7; `HOSTILE_TO` rauschfrei. |
| Rel | `KNOWS` | 9 | Soziale Kanten (Tindrael↔Wachen, Leandras↔Berthold). |
| Rel | `HAS_CLASS`/`HAS_FEATURE`/`HAS_SUBCLASS`/`USES` | 5/4/2/2 | Leichtes Vokabular-Spread → §6. |
| Rel-Props | `valid_from` / `valid_to` | 83 / 2 | Temporal-Ansatz vorhanden, aber Schließung fehlt (§7). |

---

## 3. Befundliste (offene Auflagen für Pro)

Referenzen = `props.id`. Transkript = `[Sekunde]`.

| ID | Schwere | Typ | Export-Referenz | Transkript-Evidenz | Befund | Empfehlung | Sicherheit |
|---|---|---|---|---|---|---|---|
| P-1 | HOCH | TEMPORAL_ERROR | volatile Kanten (`LOCATED_IN` u. a.) | `[7173]` Lanra flieht; Lager 04-01 befreit | 21/22 `LOCATED_IN`, 8/8 `ALLIED_WITH`, 4/4 `MEMBER_OF` sind **offen** (`valid_to=null`) → veraltete Zustände gelten als aktuell. | Supersession erzwingen (§7) | hoch |
| P-2 | MITTEL | OVERINTERPRETED | `ALLIED_WITH: Goblin-Götter→{Cookie,Dodo,Lindo,Rotunas,Esterossa}` | `[3291]` Lugasch (Goblin-Gott) will Dodos Freund einen Stein an den Kopf werfen | „Allianz" mit allen PCs widerspricht dem chaotisch-feindlichen Eingreifen der Götter. | REMOVE bzw. als `AFFECTS`/Claim | hoch |
| P-3 | MITTEL | MISSING | Kind/`Bauer`/`Schmied` nur in Events | `[4118]`/`[5540]` gerettetes Kind (Quest-Ziel); `[Schmied]` liefert Bärenfallen | Quest-/handlungsrelevante NPCs nicht als Knoten materialisiert → nicht abfragbar. | CONVERT_TO_NODE (nur quest-relevante) | mittel |
| P-4 | MITTEL | NAMING/DUPLICATE | `NPC_Lanra` `aliases=[Lenra,Linda,Linder,Norlinda,Norlinder]` | `[6955]` „Mein Name ist **Lara**"; `ITEM_BuchMitNamensliste` = **Namensliste** | (a) Kanonik sollte „Lara" sein (Selbstvorstellung), `role` `adversary` statt `NPC`. (b) Die Buch-Namen könnten **mehrere Personen** sein, nicht alle Alias der Hexe → Over-Merge-Risiko. | RENAME→Lara + REQUIRE_REVIEW der Buch-Namen | mittel |
| P-5 | NIEDRIG | ONTOLOGY_ISSUE | `IN_SESSION` (275) + `APPEARS_IN` (24) | — | Zwei Prädikate für Session-Provenance (nur nach Typ getrennt). | Vereinheitlichen | mittel |
| P-6 | NIEDRIG | REDUNDANT_RELATIONSHIP | `ALLIED_WITH` Character→Character (3) | — | Party-Zusammenhalt als paarweise Kanten statt via Party-`MEMBER_OF`. | Party-Faction | mittel |
| P-7 | HINWEIS | ONTOLOGY_ISSUE | `HAS_CLASS/HAS_FEATURE/HAS_SUBCLASS/USES` | — | Leichtes Vokabular-Spread bei Character→RuleEntity (geringer als in v7-Flash). | kompaktes `HAS_RULE {role}` (DEFER) | niedrig |

---

## 4. Nicht belegte / überinterpretierte Graph-Fakten

| Export-Referenz | Graph-Fakt | Einordnung | Empfehlung |
|---|---|---|---|
| `ALLIED_WITH: Goblin-Götter→Party` | Götter mit Party verbündet | Widerspricht dem Transkript (`[3291]`) | REMOVE/qualifizieren |
| `NPC_Lanra` aliases `Linda/Norlinda…` | Alle Buch-Namen = die Hexe | Nicht ausreichend interpretierbar (Namensliste) | REQUIRE_REVIEW |
| `Lanra → Krypta` (offen) | Lanra ist aktuell in der Krypta | Widerspricht dem Transkript (`[7173]` Flucht) | via §7 schließen |

> Der Rules-Layer ist sauber (`source=SRD`); keine „Vorwissen"-Löschungen nötig.

---

## 5. Fehlende oder falsch modellierte Transkript-Fakten

| Transkript-Evidenz | Erwartete Modellierung | Zustand in Pro | Empfehlung |
|---|---|---|---|
| `[4118]`/`[5540]` gerettetes Kind (Quest-Ziel „Kind zurückbringen") | eigener `Character`-Node | in Event gefaltet | CONVERT_TO_NODE |
| `[Schmied]` liefert Bärenfallen (Verteidigungsressource) | `Character`-Node (optional) | in Event gefaltet | REVIEW |
| `[6955]` „Mein Name ist Lara" | canonical=Lara, aliases Lanra/Lenra | canonical=Lanra | RENAME |
| Krypta-Auftrag (Recap 04-15) | Sub-Quest unter dem Arc | nicht als Quest vorhanden | REVIEW |

---

## 6. Redundanz- und Ontologieanalyse

**Unnötiges Wachstum:** gering. `MENTIONS` (2177) ist gewollte RAG-Provenance. Verbliebene Kandidaten: paarweise `ALLIED_WITH` (P-6), Doppel-Provenance `IN_SESSION`/`APPEARS_IN` (P-5), `HAS_*`-Spread (P-7).

**Positiv:** keine bidirektionalen Dublettenkanten, keine semantisch überlappenden inversen Kanten, `HOSTILE_TO` rauschfrei (2 echte), Event→Quest via `RESULTED_IN` verbunden.

**Quest-Granularität:** 16→1 ist konsistent, aber die Krypta-Teilmission ist als eigenständige Quest verschwunden — „welche Quests sind in Session X offen?" ist nicht mehr beantwortbar. Empfehlung: **1 Kampagnen-Arc + Sub-Quests** (leichte Erweiterung, kein Rückschritt zur v6-Redundanz).

**Top-5 Ontologie-Regeln (Hebel):**
1. **Supersession für volatile Kanten** (§7) — größter Qualitäts-Hebel für Retrieval-Aktualität.
2. **Quest-/handlungsrelevante NPCs immer materialisieren** (behebt P-3 ohne Flash-Rauschen).
3. **Ein Provenance-Prädikat** (`IN_SESSION`) für alle Typen; `APPEARS_IN` streichen.
4. **Kontrolliertes `role`-Vokabular** (Boss = `adversary`, Gottheiten = Faction/Deity — bereits gut).
5. **Namenslisten-Guard:** aus einer Item-Namensliste extrahierte Namen nicht automatisch als Aliases einer Entität mergen (P-4).

---

## 7. Temporale Gültigkeit von Positions-/Zustandskanten (Auflage R-NEU-9, HOCH)

**Problem (datenbelegt).** `valid_from`/`valid_to` existieren als **Session-Index** (1=04-01, 2=04-09, 3=04-15) — als „wann wurde die Info gegeben" ausreichend. Es fehlt aber die konsequente **Schließung**: volatile Kanten bleiben fast immer offen.

| Kantenklasse | offen / gesamt (`valid_to=null`) |
|---|---|
| `LOCATED_IN` | 21/22 |
| `OWNED_BY` | 8/9 |
| `MEMBER_OF` | 4/4 |
| `ALLIED_WITH` | 8/8 |
| `HOSTILE_TO` | 2/2 |

Konkrete Altlasten: `Lanra → Krypta` offen trotz Flucht (`[7173]`); `Schleichfurz → Goblinlager` offen seit Session 1 trotz Befreiung. **Positivbeispiel — die Pipeline kann es bereits:** `Tindrael → Friedhof` ist mit `valid_to=2` korrekt geschlossen, `Tindrael → Breschka` bleibt offen. Es passiert nur inkonsistent (1 von 22).

**Präzisierung:** `AT_LOCATION` (Event→Location) ist **stabil** (ein Event-Ort ändert sich nie) und braucht **kein** `valid_to`. Zu versionieren ist die **Entitäts-Positionskante** `LOCATED_IN` (Character/Item→Location) — sowie Besitz, Mitgliedschaft, Allianz, Feindschaft und Node-`status`.

**Bedingung — zwei Kantenklassen:**
- **Stabil** (nur `valid_from`): `AT_LOCATION`, `LOCATED_IN` (Location→Location, Geografie), `PARTICIPATED_IN`, `HAS_CLASS`, `HAS_ANCESTRY`, `PLAYS`, `APPEARS_IN`, `IN_SESSION`.
- **Volatil** (`valid_from` + Schließung via `valid_to`): `LOCATED_IN` (Character/Item→Location), `OWNED_BY`, `MEMBER_OF`, `ALLIED_WITH`, `HOSTILE_TO`, Node-`status`.

**Regeln:**
1. `valid_from` = Session/Zeitpunkt der letzten Bestätigung („zuletzt gesehen"-Stempel).
2. **Supersession beim Ingest:** existiert eine *offene* Kante derselben exklusiven Klasse für dieselbe Quell-Entität, wird sie geschlossen (`valid_to`=neue Session), bevor die neue gesetzt wird („latest observation wins"). Position/Mitgliedschaft sind pro Entität exklusiv.
3. **Query-Konvention:** „aktuell" = `valid_to IS NULL` **und** höchstes `valid_from`.
4. **Empfohlen:** Feld `last_observed_session`, um „veraltet, nicht widerlegt" von „aktiv bestätigt" zu trennen (ein explizites „X verlässt Y" kommt im Transkript selten vor).

---

## 8. Token-/Kosten-Optimierung für das Pro-Modell (konservativ)

**Ausgangslage (gemessen).** Ein Session-Transkript ≈ **27–29k Token** (voll serialisiert), ~24k reiner Inhalt; **~17% sind Timestamp-/Label-Overhead**. Alle drei Sessions ≈ **85k Token**. Wird das Transkript für **Szenen-Segmentierung *und* Extraktion** je einmal an Pro geschickt, sind es schon **~170k Input-Token** — plus der **pro Szene wiederholte Schema-/Instruktions-Block**. Genau dieser wiederholte Prefix erzeugt die vielen **Cache-Misses**: Bei z. B. 18 Szenen/Session und ~4k Token Schema+Few-Shot werden ~72k Token **pro Session nur an Wiederholung** gezahlt — oft mehr als das Transkript selbst.

**Leitprinzip (konservativ):** Nur Token kürzen, die **keine extrahierbaren Weltfakten** tragen, und **Cache-Treffer maximieren**. Der eigentliche Szeneninhalt (aus dem Pro over-summarized) bleibt unangetastet.

| # | Maßnahme | Hebel | Qualitätsrisiko | Erwartete Einsparung |
|---|---|---|---|---|
| 1 | **Prefix-Caching**: System+Schema+Few-Shot als **byte-identischen Führungsblock** an den Anfang, variabler Szenen-Chunk ans **Ende**. DeepSeek Context-Cache berechnet Cache-Hits stark reduziert. | größter | **keine** (Inhalt unverändert) | oft **40–70% des Input-Preises** |
| 2 | **Modell-Kaskade**: Szenengrenzen mit **billigem Modell/Heuristik** (Timestamp-Lücken + Sprecherwechsel + Embeddings) statt mit Pro. Pro nur für die eigentliche Extraktion. | groß | gering (Segmentierung ist grob) | entfernt **einen ganzen Transkript-Pass** aus Pro (~50% der Transkript-Token) |
| 3 | **Inline-Timestamps entfernen** (Speaker-Labels behalten!), Zeit-/Chunk-Zuordnung in Seitentabelle für `evidence_chunks`. | mittel | **~keins** | ~8–12% des Transkripts |
| 4 | **Leichte Normalisierung**: unmittelbare Wort-Wiederholungen kollabieren („Sekunde, Sekunde"→„Sekunde"), **kleine kuratierte Denylist** reiner Produktions-/Stream-Zeilen (Technik-Check, „ich push die Musik"). Nur Eindeutiges. | klein | gering (bei enger Liste) | ~3–8% |
| 5 | **Nicht-diegetische Fenster überspringen** (Session-Technikcheck, Pausen) via billigen Klassifikator; kein Pro-Call darauf. | klein–mittel | gering | 5–10% |
| 6 | **Output zügeln**: `significance`/Reasoning auf ≤2 Sätze begrenzen (Gate bleibt!). | klein (Output) | keins | Output-Token ↓ |
| 7 | **Warm-Cache-Batching**: alle Szenen einer Session (idealerweise aller Sessions) **direkt hintereinander** verarbeiten, damit der Prefix-Cache warm bleibt (TTL). | Multiplikator für #1 | keins | verstetigt #1 |
| 8 | **Off-Peak/Batch-Tarif** (falls DeepSeek aktuell anbietet): zeitunkritische Läufe dorthin verschieben. | operativ | keins | preisabhängig |

**Wichtiger Caching-Hinweis (Qualität schützen):** Der Cache greift nur auf dem **längsten gemeinsamen Prefix**. Ein pro Call **wachsendes** Element (z. B. eine Kanonik-/Entity-Registry inline) **bricht** den Cache ab seiner Position. Daher: die **Entitäts-Resolution als separaten, billigen Post-Pass** (deterministisches Fuzzy-Matching oder billiges Modell) führen, statt eine wachsende Registry in jeden Pro-Call zu stopfen. So bleiben Prefix-Cache **und** Dedup-Qualität erhalten.

**Reihenfolge & Sicherung:**
- **P0 (null Risiko):** #1 Prefix-Caching, #3 Timestamps raus, #7 Batching. Allein #1 senkt die Input-Kosten meist am stärksten.
- **P1 (geringes Risiko):** #2 Modell-Kaskade, #5 Fenster-Skipping, #6 Output-Cap.
- **P2:** #4 Normalisierung (eng halten), #8 Tarif.
- **Guardrail (Pflicht):** Vor Rollout **A/B auf einer Session** — optimiert vs. aktueller Pro-Lauf. Akzeptanz nur, wenn **kein kanonischer Entitätsverlust**, **keine neue Halluzination** und Entity-/Kanten-Zahlen ± Toleranz. Als konkrete Anker gegenprüfen: Bertie vorhanden, Lugasch=Faction, Lara-Identität, Rules-Layer kanten-rein, keine leeren Events. Erst bei bestandenem A/B produktiv schalten.

> Erwartete Gesamtwirkung konservativ: **~50–70% niedrigere Input-Kosten** (dominiert von #1 + #2), **ohne merkliche Qualitätseinbuße**, weil der über-summarisierte Szeneninhalt unangetastet bleibt und alle Schnitte nur Wiederholung/Overhead/Nicht-Diegetisches betreffen.

---

## 9. Priorisierter Maßnahmenplan

| Priorität | Maßnahme | Kategorie | Nutzen | Aufwand |
|---|---|---|---|---|
| P0 | Prefix-Caching + Timestamps entfernen + Batching (§8 #1/#3/#7) | Kosten | −40–70% Input-Kosten, kein Qualitätsverlust | S |
| P0 | Supersession für volatile Kanten (§7) | Ontologie/Schema | Aktualität, keine Zombie-Zustände | M |
| P0 | `ALLIED_WITH: Goblin-Götter→Party` entfernen/qualifizieren (P-2) | Datenbereinigung | Evidenztreue | S |
| P1 | Modell-Kaskade für Szenengrenzen (§8 #2) | Kosten | −½ Transkript-Pass auf Pro | M |
| P1 | Quest-/handlungsrelevante NPCs materialisieren (P-3); Kind als Node | Extraktionsprompt | Vollständigkeit ohne Rauschen | S |
| P1 | Bossname→Lara (+Aliases), Namenslisten-Guard (P-4) | Datenbereinigung + Human-Review | Kanonik, Over-Merge vermeiden | S |
| P2 | Provenance vereinheitlichen (`IN_SESSION`); Party-`MEMBER_OF` (P-5/P-6) | Ontologie | kompakteres Vokabular | M |
| P2 | Node-`status` (Item/Quest) temporal versionieren (§7) | Schema | Zeitlichkeitsrisiko ↓ | M |
| P2 | Quest-Arc + Sub-Quests (§6) | Human-Review | Abfragbarkeit „offene Quests je Session" | S |

### Vier Akzeptanztests für die nächste Session

1. **Signifikanz-Gate:** `MATCH (e:Entity{type:'Event'}) WHERE e.significance =~ '(?i).*(keine? permanente|no permanent|noch keine spielrelevante).*' RETURN count(e)` = **0**. *(Pro besteht bereits.)*
2. **Rules-Layer kanten-rein:** kein `:Entity{source:'SRD'}` trägt `KILLED|TARGETS|HOSTILE_TO|MEMBER_OF|OWNED_BY|LOCATED_IN`. → 0. *(Pro besteht bereits.)*
3. **Identität/Redundanz:** kein aktives Entitätspaar gleichen Typs mit Namens-/Alias-Ähnlichkeit ≥ 0.9 ohne Review-Flag; keine bidirektionalen `ALLIED_WITH`-Paare. → 0.
4. **Temporale Schließung (neu):**
   ```cypher
   // (a) keine Entität an zwei "aktuellen" Orten -> leer
   MATCH (c:Entity)-[r:LOCATED_IN]->(:Entity)
   WHERE r.valid_to IS NULL AND c.type IN ['Character','Item']
   WITH c, count(r) AS offen WHERE offen > 1 RETURN c.name, offen;
   // (b) jede volatile Kante hat valid_from -> 0
   MATCH ()-[r]->() WHERE type(r) IN ['LOCATED_IN','OWNED_BY','MEMBER_OF','ALLIED_WITH','HOSTILE_TO']
     AND r.valid_from IS NULL RETURN type(r), count(*);
   ```

---

### Fazit

v7-pro ist der **empfohlene kanonische Graph**: evidenztreu, ontologisch sauber, temporal vorbereitet. Die Auflagen sind klein und größtenteils deterministisch prüfbar. Der Token-Plan senkt die Pro-Kosten **konservativ um ~50–70%**, indem er ausschließlich Wiederholung, Overhead und Nicht-Diegetisches angreift — der über-summarisierte Szeneninhalt, aus dem die Qualität entsteht, bleibt unberührt.
