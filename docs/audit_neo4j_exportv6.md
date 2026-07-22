# Forensisches Audit — Neo4j Knowledge-Graph-Export (`neo4j_exportv6.json`)

**Kampagne:** „Dwarf Masters" (Daggerheart / TaleSpire, Sprache: DE)
**Geprüfte Sessions:** 2025-04-01, 2025-04-09, 2025-04-15
**Primärevidenz:** 3 Whisper-Transkripte (`transcripts/`), Speaker-Labels vorhanden
**Export:** 437 Nodes (246 `:Chunk`, 191 `:Entity`), 2302 Relationships
**Prüfmethode:** bidirektionaler Abgleich Graph ↔ Transkript, konservativ, quellenbasiert.

> Hinweis zur Zeit-Einordnung: Es liegen nur diese drei Sessions vor. „Kein Beleg gefunden" wird als *in dieser Session unbelegt* markiert, nicht als *falsch*. Explizite Widersprüche werden gesondert ausgewiesen.

---

## 1. Executive Assessment

- **Gesamturteil: REVIEW ERFORDERLICH**
- **Datenqualität: 5/10**
- **Evidenztreue: 6/10**
- **Ontologie-Konsistenz: 4/10**
- **Redundanzrisiko: hoch**
- **Zeitlichkeitsrisiko: hoch**

**Wichtigste drei Befunde:**

1. **Identitäts-Zerfall durch Whisper-Schreibvarianten:** Dieselbe Entität existiert mehrfach (Leandras = „Magier"; Nip = „der besoffene Nip"; Goblin-Dorf = Goblinlager = Goblendorf; Breska = Breschka = „Dorf"), und schlimmer: der **Grabwächter Tindrael** wurde mit dem **fliehenden Kind „Timrell"** in *einen* Node (`NPC_Tindrail`) zusammengemergt — zwei verschiedene Figuren.
2. **Halluzinationen aus Meta-/Regel-Talk:** `NPC_Walk`, `RULE_CLASS_Blizzard` und `RULE_ANCESTRY_Maus` sind keine diegetischen Entitäten, sondern Fehl-Extraktionen aus GM-Nebenbemerkungen bzw. der Beschreibung einer Miniatur. `EVT_SessionOpeningCharacterIntroductions` gibt selbst zu, keine Weltveränderung zu enthalten.
3. **Massive Quest- und Decision-Redundanz gegen die eigene Zielarchitektur:** Eine einzige laufende Quest („Breska gegen Goblins verteidigen") ist als **8 Nodes** mit widersprüchlichem Status modelliert, die Krypta-Quest als **4 Nodes** (u. a. gleichzeitig `open` und `completed`). Zusätzlich existieren **39 `Decision`-Nodes** — genau der Knotentyp, den euer Meta-Konzept explizit verbietet.

---

## 2. Modellinventar

| Elementtyp | Typ/Label | Anzahl | Beobachtung |
|---|---|---:|---|
| Node | `:Chunk` | 246 | RAG-Layer (Transkript-Passagen). Korrekt getrennt via Label. |
| Node | `:Entity` | 191 | Weltmodell-Skelett. |
| Entity-Typ | `RuleEntity` | 49 | Mischung aus SRD-Kanon (`session_id=SRD`, conf=high) **und** Session-Extraktionen (conf=medium) — teils dupliziert/halluziniert. |
| Entity-Typ | `Decision` | 39 | **Verstoß gegen eigene Doktrin** („Keine Decision-Knoten"). Enthält reine Mikro-Aktionen. |
| Entity-Typ | `Character` | 25 | Duplikate & Fehl-Merges (siehe §3). NPC/PC-Trennung via `role`+`is_pc`. |
| Entity-Typ | `Event` | 19 | Makro-Events — grundsätzlich sinnvoll; 1 leerer Event. |
| Entity-Typ | `Location` | 17 | Starke Duplizierung (Goblin-Camp ×3, Krypta/Dungeon/Bossraum, Breska/Dorf). |
| Entity-Typ | `Quest` | 16 | ~8 + ~4 Nodes für nur **2** reale Quests. |
| Entity-Typ | `Item` | 9 | `status` als zeitloser String; teils Duplikat (Voodoo-Puppe ×2). |
| Entity-Typ | `Faction` | 7 | Uneinheitlich (Gilde vs Gildenhalle; „Zweite Partei"). |
| Entity-Typ | `Player` | 7 | Fälschlich session-scoped; Player→Character-Mapping unvollständig. |
| Entity-Typ | `Session` | 3 | OK. |
| Relationship | `MENTIONS` | 1744 | RAG-Brücke `:Chunk`→`:Entity`. Erwartungskonform, im Chunk-Layer belassen. |
| Relationship | `IN_SESSION` | 304 | Nur für Chunk/Decision/Event. Provenance uneinheitlich. |
| Relationship | `PARTICIPATED_IN` | 74 | Character→Event. Nützlich, aber teils Provenance-Charakter. |
| Relationship | `DECIDED` | 38 | Character→Decision — verschwindet mit dem Decision-Node. |
| Relationship | `APPEARS_IN` | 30 | Character/Player→Session. **Semantisch = `IN_SESSION`.** |
| Relationship | `ALLIED_WITH` | 17 | Party-Clique (N²) + bidirektionale Dubletten. |
| Relationship | `AT_LOCATION` | 13 | Event→Location. OK. |
| Relationship | `HAS_FEATURE`/`HAS_CLASS`/`HAS_ANCESTRY`/`USES` | 11/4/8/5 | 4 überlappende Character→RuleEntity-Kanten. |
| Relationship | `LOCATED_IN`/`MEMBER_OF`/`OWNED_BY` | 10/10/9 | Grundsätzlich sinnvoll; zeitlos gespeichert. |
| Relationship | `HOSTILE_TO`/`FEARS`/`KNOWS`/`RELATES_TO` | 6/2/1/2 | Emotionale/soziale Einzelszenen-Zustände als zeitlose Fakten. |
| Relationship | `PLAYS`/`DIRECTS` | 10/3 | Player-Mapping. `DIRECTS` (GM) über alle Sessions, aber Player session-scoped. |
| Relationship | `RESULTED_IN` | 1 | Nur 1× vorhanden → inkonsistent (Events↔Quests sonst unverknüpft). |

**Vermutete Modellierungsabsicht:** GraphRAG-Hybrid (Skelett `:Entity` + Vektor-Layer `:Chunk`, Brücke `MENTIONS`). Die Absicht ist korrekt; die Umsetzung überproduziert Knoten und ignoriert Zeitlichkeit.

---

## 3. Befundliste

Referenzen = stabile `props.id` der Nodes. Transkript-Referenz = `[Sekunde] Sprecher`.

| ID | Schwere | Typ | Export-Referenz | Transkript-Evidenz | Befund | Empfehlung | Sicherheit |
|---|---|---|---|---|---|---|---|
| F1 | HOCH | WRONG_ENTITY | `NPC_Tindrail` (aliases Tenrell, Tindrael) | `[1226]` „Tindrael ist der Grabwächter"; `[4118]` Rotunas: „**Timrell**, warte da" (Kind) | Grabwächter **und** fliehendes Kind „Timrell" in einem Node gemergt; `pending_notes` enthält „das Kind, das wegläuft". Zwei verschiedene Figuren. | CONVERT_TO_NODE (Kind ausgliedern) + REQUIRE_REVIEW | hoch |
| F2 | HOCH | DUPLICATE | `NPC_Leandra` ↔ `NPC_Magier` | `[531]` „mein Name ist **Leandras**. Ich bin hier der **Magier**" | Derselbe Dorf-Magier als zwei NPCs. Auch Name „Leandra" vs „Leandras". | MERGE + RENAME→Leandras | hoch |
| F3 | HOCH | DUPLICATE | `LOC_LeandrasHaus` ↔ `LOC_HausDesMagiers` | `[531]`/`[276]` Haus des Magiers = Leandras' Haus (vergitterte Fenster / versiegelte Tür) | Ein Gebäude, zwei Location-Nodes. | MERGE | hoch |
| F4 | HOCH | DUPLICATE | `NPC_Lanra` → `CHAR_Cookie` | `[6826]` Celin (Cookie): „Name ist **Lanra**" | „Lanra" ist Cookies PC-Name, kein eigener NPC. `pending_notes` sagt es selbst. **Nicht** mit Boss „Lara" verwechseln (`[6955]`). | MERGE in `CHAR_Cookie` | hoch |
| F5 | HOCH | DUPLICATE | `LOC_GoblinDorf` ↔ `LOC_Goblinlager` ↔ `LOC_Goblendorf` | `[7162]` (04-01) „das **Goblenlager** … befreit"; `FACTION_Goblins`: „camp cleared in a previous mission" | Dasselbe Goblin-Camp über 3 Sessions als 3 Locations („Goblendorf" = Tippfehler). | MERGE (temporale Versionen) | hoch |
| F6 | HOCH | DUPLICATE | `LOC_Breska` ↔ `LOC_Dorf` („namenloses Dorf") | 04-09 Text „Brechka/Breschka"; `LOC_Dorf`: „village defended in a previous mission" | Verteidigtes Dorf = Breska = Breschka. Schreibvarianten Breska/Breschka/Brechka/Breshka. | MERGE + RENAME (kanonisch Breska) | hoch |
| F7 | HOCH | REDUNDANT_RELATIONSHIP | 8× `QUEST_*` (Goblin-Verteidigung) | `EVT_AuftaktVorbereitungAufDieGoblinInvasion`; 04-09/04-15 durchgängig | Eine laufende Quest als 8 Nodes mit widersprüchl. Status (`new`/`open`): u. a. `QUEST_BreschkaAufGoblinAngriffVorbereiten`, `QUEST_GoblinangriffAbwenden`, `QUEST_DorfGegenGoblinsVerteidigen`, `QUEST_VerteidigungBreschkaGegenGoblins`, `QUEST_DorfGegenGoblinAngriffVerteidigen`, `QUEST_VerteidigungDesDorfes`, `QUEST_VerteidigungVonBreska`. | MERGE → 1 Quest + Status-Timeline | hoch |
| F8 | HOCH | TEMPORAL_ERROR | 4× `QUEST_*` (Krypta) | `EVT_AufbruchZurKrypta`, `EVT_KonfrontationMitLara…` | `QUEST_DungeonSaeubern`=`completed` **gleichzeitig** mit `QUEST_KryptaErkunden`/`…FindenUndSaeubern`=`open` + `QUEST_KryptaCleanen`=`new`. Exklusive Zustände parallel aktiv. | MERGE → 1 Quest, Status zeitlich versionieren | hoch |
| F9 | HOCH | ONTOLOGY_ISSUE | `Decision` (39 Nodes) + `DECIDED` (38) | z. B. `DEC_2025-04-09_ValeriaIsstEineMoehreVomFeld`, `DEC_…DoubleTapAmTotenGoblin`, `DEC_2025-04-15_EsterossaNutztPreyDiceGegenSchaden` | Widerspricht eurer eigenen Meta-Architektur („Keine Decision-/Würfel-Knoten"). Enthält reine Mikro-Aktionen/Mechanik-Calls. | CONVERT_TO_PROPERTY (`decisions[]`/`rolls_by_scene` am Event) | hoch |
| F10 | HOCH | MISSING | Session `2025-04-01` | Speaker: `Celin (Cookie)`, `Basti (Esterossa)`, `Marco (Dodo)` (177–179 Turns); `[205]` „der Tank geht vor" | Drei aktive PCs, aber **0** PC-Nodes und **0** Player-Nodes für 04-01. `Esterossa` erst ab 04-15 als Node. | CONVERT_TO_NODE + PARTICIPATED_IN nachtragen | hoch |
| F11 | MITTEL | UNSUPPORTED | `NPC_Walk` | `[1314]` GM: „ihr merkt, **Walk** hat dafür gesorgt, dass es … spät geworden ist" | Meta-Bemerkung des GM (Zeit/Stream), kein diegetischer NPC. `pending_notes` erfindet „ein NPC, der die Zeit beeinflusst hat". | REMOVE | hoch |
| F12 | MITTEL | UNSUPPORTED | `RULE_CLASS_Blizzard` | `[800]` Rotunas: „Als **Blizzard** kannst du so Kleinigkeiten machen" | In-Character-Geplänkel, keine Daggerheart-Klasse. | REMOVE | hoch |
| F13 | MITTEL | UNSUPPORTED | `RULE_ANCESTRY_Maus` | `[81]` GM: „Das ist nur eine **Maus als Figur** leider" | „Maus" beschreibt die Miniatur, nicht die Ancestry (die Figur ist ein Affe/Simia). | REMOVE | hoch |
| F14 | MITTEL | DUPLICATE | `RULE_ANCESTRY_Affe` ↔ `RULE_ANCESTRY_Simia` | `[79]` „Ein Sima … **Simia** heißen die Dinger" | „Affe" (umgangssprachl.) = Simia. | MERGE → Simia | hoch |
| F15 | MITTEL | OVERINTERPRETED | `EVT_SessionOpeningCharacterIntroductions` | Node-Property selbst: „No permanent world state changes occur — no combat, no quest updates, no deaths." | Event ohne narrative Signifikanz — verletzt den `narrative_significance`-Gate. | REMOVE | hoch |
| F16 | MITTEL | DUPLICATE | `NPC_Nip` ↔ `NPC_BesoffeneNip` | `[3219]` „der **besoffene Nip** … losgeschrien"; Notes: „stellt sich als Drunken Monk heraus" | „Der besoffene Nip" ist ein Zustand desselben NPC, kein zweiter Charakter. | MERGE (Zustand → Property) | hoch |
| F17 | MITTEL | DUPLICATE | `ITEM_VoodooPuppe` ↔ `ITEM_HoelzerneVoodooPuppe` | `[…]` `DEC_…CookieHebtDieVoodooPuppeAuf`; beide 04-15 | Ein Gegenstand, zwei Item-Nodes (status „benutzt"/„aufgehoben"). | MERGE | hoch |
| F18 | MITTEL | DUPLICATE/ONTOLOGY | `LOC_Krypta` ↔ `LOC_Dungeon` ↔ `LOC_Bossraum` | `EVT_KampfGegenDieSkeletteImDungeon`, `EVT_KonfrontationMitLara…` | Zu räumende Krypta = Dungeon = Bossraum (Teilräume). `LOC_AlteBurgRuine` = Ruine darüber. | MERGE (Teilräume als Property) + REQUIRE_REVIEW | mittel |
| F19 | MITTEL | REDUNDANT_RELATIONSHIP | `ALLIED_WITH` (17) | 04-15 PC-Party (Lindo→Cookie/Dodo/Rotunas/Esterossa …), Valeria↔Rotunas beidseitig | Party-Clique als N²-Kanten + bidirektionale Dubletten; drückt nur „gehören zur Party" aus. | REMOVE → `MEMBER_OF` Party-Faction | hoch |
| F20 | MITTEL | REDUNDANT_RELATIONSHIP | `RELATES_TO` (2) | Valeria–Rotunas, Dodo–Esterossa | Vollständig durch `ALLIED_WITH` abgedeckt; generischer Catch-all. | REMOVE | hoch |
| F21 | MITTEL | NAMING_INCONSISTENCY | `NPC_Elisa` (alias Lisa), `NPC_Leandra`/„Leandras", Breska/Breschka | `[3219]` „die Lisa"; `[531]` „Leandras" | Uneinheitliche Kanonik-Namen; Aliases teils erfasst, teils nicht. | RENAME (kanonischer Name + `aliases[]`) | mittel |
| F22 | MITTEL | ONTOLOGY_ISSUE | `IN_SESSION` (304) vs `APPEARS_IN` (30) | — | Zwei Kanten für „Entität gehört zu Session X"; zusätzlich haben Location/Item/Quest/Faction **gar keine** Session-/Provenance-Kante. | MERGE Vokabular + PROVENANCE_GAP schließen | hoch |
| F23 | MITTEL | ONTOLOGY_ISSUE | `HAS_FEATURE`/`HAS_CLASS`/`HAS_ANCESTRY`/`USES` | — | 4 überlappende Character→RuleEntity-Typen. | MERGE zu kompaktem Vokabular (z. B. `HAS_RULE`+`role`) | mittel |
| F24 | MITTEL | PROVENANCE_GAP | `RuleEntity` conf=medium (session-extrahiert) | `[79]`, `[705]` etc. | Session-Regeln (`Magier`, `MageHand`, `IceSpikes`, `GreatStaff`, `HeilendeHand`, `Experience`, `Spellcast` …) parallel zu SRD-Kanon; kein Link auf SRD-Nodes. | ADD_PROVENANCE / MERGE auf SRD | mittel |
| F25 | MITTEL | ONTOLOGY_ISSUE | `RULE_CLASSFEATURE_Seraph` | Daggerheart-SRD | „Seraph" ist eine **Klasse**, kein ClassFeature (falscher `subtype`). | RENAME/Reklassifizieren | mittel |
| F26 | NIEDRIG | DUPLICATE | `RULE_CLASSFEATURE_HeilendeHand` ↔ `…MendingTouch` | 04-15 vs 04-09 | Vermutlich dieselbe Heil-Fähigkeit (DE/EN). | REQUIRE_REVIEW / MERGE | niedrig |
| F27 | MITTEL | TEMPORAL_ERROR | `HOSTILE_TO`/`FEARS` (Kerl→Valeria/Rotunas, Kerl→Tindrail, Tindrail→Valeria) | `[1181]` Wache lässt sich einschüchtern | Einmalige Einschüchterungs-Szene als zeitloser Gefühls-Fakt. | MARK_AS_CLAIM / zeitlich binden | mittel |
| F28 | MITTEL | TEMPORAL_ERROR | `Item.status`, `Quest.status`, `MEMBER_OF`, `OWNED_BY` | — | Zeitpunkt-Zustände (Besitz, Status) als zeitlose Properties/Kanten, ohne `valid_from`/`valid_to`. | Temporale Versionierung einführen | hoch |
| F29 | MITTEL | ONTOLOGY_ISSUE | `Player` session-scoped; `PLAYS` (10) | Speaker: Basti→Esterossa, Celin→Cookie, Marco→Dodo, Benjamin→Valeria, Micha→Rotunas, Tim→Lindo Laut | Spieler sind kampagnenübergreifend, aber je 1 `session_id`. Basti/Celin/Marco spielten auch 04-01. | Player entkoppeln (kein `session_id`), `PLAYS` vervollständigen | hoch |
| F30 | NIEDRIG | MISSING | Kind „Timrell" als Quest-Ziel | `[4118]` „Timrell, warte"; `QUEST_KindZurueckbringen` | Quest-Ziel-Entität existiert nur als Fehl-Merge in `NPC_Tindrail`. | CONVERT_TO_NODE (aus F1) | mittel |
| F31 | NIEDRIG | REDUNDANT_RELATIONSHIP | `RESULTED_IN` (1) | nur `EVT_KampfGegen…Kind` → `QUEST_KindZurueckbringen` | Einzelinstanz → Event↔Quest-Verknüpfung sonst durchgängig fehlend (inkonsistent). | Regel vereinheitlichen oder DEFER | mittel |
| F32 | HINWEIS | DUPLICATE | `NPC_Tindra` | `[5540]` „Tindra ein bisschen besorgt … ist alles in Ordnung?" | Evtl. Elternteil des Kindes **oder** Whisper-Variante von Tindrael. Unklar. | REQUIRE_REVIEW | niedrig |
| F33 | HINWEIS | ONTOLOGY_ISSUE | `RULE_TRAIT_*` (6), `RULE_MECHANIC_*` (5) | SRD | SRD-Kanon; grundsätzlich ok, aber laut Doktrin „Keine Trait-Knoten". Nur nützlich, wenn Charaktere darauf verweisen. | DEFER / in Rules-Layer isolieren | niedrig |

---

## 4. Nicht belegte Graph-Fakten

| Export-Referenz | Graph-Fakt | Einordnung | Empfehlung |
|---|---|---|---|
| `NPC_Walk` | NPC „Walk", „der die Zeit beeinflusst hat" | Widerspricht dem Transkript (Meta-Talk `[1314]`) | REMOVE |
| `RULE_CLASS_Blizzard` | Klasse „Blizzard" | Widerspricht dem Transkript (Banter `[800]`) | REMOVE |
| `RULE_ANCESTRY_Maus` | Ancestry „Maus" | Widerspricht dem Transkript (nur Miniatur `[81]`) | REMOVE |
| `NPC_Lanra` (role=PC, als eigener NPC) | Eigenständige Figur „Lanra" | Nicht ausreichend interpretierbar (= Cookies PC-Name) | MERGE in Cookie |
| `FACTION_ZweitePartei` | „Zweite Partei" hinter dem Angriff | In dieser Session unbelegt (nur angedeutet, `EVT_AufbruchZurKrypta`) | MARK_AS_CLAIM |
| `FACTION_Gildenhalle` vs `FACTION_Gilde` | Zwei Gilden-Factions | Nicht ausreichend interpretierbar (Halle = Ort der Gilde) | MERGE/REVIEW |
| `RULE_*` conf=medium (Magier, MageHand, IceSpikes, GreatStaff, Experience, Spellcast, HeilendeHand …) | Regel-Kanon | Wahrscheinlich Vorwissen (SRD) / RAG-Detail | ADD_PROVENANCE bzw. auf SRD mappen |
| `NPC_Berthold`, `NPC_Schmied`, `NPC_Findus`, `NPC_Elisa` Detailattribute | Rollen/Backgrounds | In dieser Session belegt (Nebenfiguren) | KEEP |

> Keiner dieser Punkte wird allein wegen fehlender Evidenz gelöscht, sofern kampagnenübergreifendes Wissen möglich ist. Gelöscht (`REMOVE`) werden nur die Fälle mit **klarem Widerspruch** zum Transkript (Walk, Blizzard, Maus).

---

## 5. Fehlende oder falsch modellierte Transkript-Fakten

| Transkript-Evidenz | Erwartete Modellierung | Tatsächlicher Zustand im Export | Empfehlung |
|---|---|---|---|
| `[205]`/`[1472]` 04-01: Esterossa (Tank), Cookie, Dodo agieren | 3 `Character(PC)`-Nodes + `PARTICIPATED_IN` für 04-01 | Keine PC-Nodes für 04-01; Esterossa erst ab 04-15 | CONVERT_TO_NODE |
| Speaker-Labels: Basti→Esterossa, Celin→Cookie, Marco→Dodo, Benjamin→Valeria, Micha→Rotunas, Tim→Lindo Laut | Stabile `PLAYS` Player→Character (kampagnenweit) | Nur 10 `PLAYS`; Player fälschlich session-scoped | ADD/COMPLETE `PLAYS` |
| `[4118]` „Timrell" = fliehendes Kind (Quest-Ziel) | Eigener `Character`-Node + `QUEST_KindZurueckbringen`-Ziel | In `NPC_Tindrail` hineingemergt | CONVERT_TO_NODE |
| `[531]` Leandras = der Magier | 1 NPC + 1 Haus | 2 NPCs + 2 Häuser | MERGE |
| `[7162]` 04-01 „Karte / Angriffsplan auf ein Dorf" gelootet | 1 `Item` (Notiz/Karte) mit Provenance 04-01 | `ITEM_Notiz` erst 04-09 („der Gilde übergeben") | ADD_PROVENANCE (Herkunft 04-01) |
| `[79]` Valeria = Simia-Ancestry, Rotunas = Giant | `HAS_ANCESTRY` Valeria→Simia, Rotunas→Giant | Ancestries als lose Rule-Nodes (Affe/Maus/Simia/Giant) unverknüpft/dupliziert | CLEANUP + korrekt verknüpfen |

---

## 6. Redundanz- und Ontologieanalyse

**Welche Relationship-Typen erzeugen unnötiges Graphwachstum?**
`ALLIED_WITH` (Party-Clique, N²), `RELATES_TO` (generisch), `DECIDED` (verschwindet mit dem Decision-Node), sowie die Aufsplittung `HAS_FEATURE`/`HAS_CLASS`/`HAS_ANCESTRY`/`USES`. `MENTIONS` (1744) ist gewollter RAG-Provenance-Layer und **kein** Problem, solange er im `:Chunk`-Layer bleibt.

**Doppelte / semantisch überlappende Kanten:** `IN_SESSION` ≙ `APPEARS_IN`; `RELATES_TO` ⊂ `ALLIED_WITH`; bidirektionale `ALLIED_WITH`-Paare (Valeria↔Rotunas, Rotunas↔Tindrail).

**Event-/Teilnahme-Kanten mit langfristigem Nutzen vs. Wegwerf-Kontext:**
- Langfristig kanonisch: `AT_LOCATION`, `OWNED_BY`, `MEMBER_OF`, `LOCATED_IN`, `HAS_ANCESTRY`, `HAS_CLASS` (temporal versioniert).
- Nur Session-/Provenance-Wert: `PARTICIPATED_IN`, `DECIDED`, `IN_SESSION` — als Event-Attribut bzw. Provenance komprimierbar.
- Als **Claim** statt Fakt: `HOSTILE_TO`/`FEARS`/`KNOWS` (Einzelszene) und `FACTION_ZweitePartei`.

**Zusammenführen / Umbenennen / Umbauen:**
Merges: Leandras+Magier (& Häuser), Goblin-Camp ×3, Breska+Dorf, Krypta+Dungeon+Bossraum, Nip+BesoffeneNip, Lanra→Cookie, Voodoo-Puppe ×2, Gilde+Gildenhalle, Affe→Simia. Umbau: `Decision`→Event-Property; `ALLIED_WITH`→Party-`MEMBER_OF`.

**Zeitlich zu versionierende Properties/Relationships:** `Quest.status`, `Item.status`, `OWNED_BY`, `MEMBER_OF`, `LOCATED_IN`, `HOSTILE_TO/FEARS`, sowie Character-`status`.

**Top-5 Ontologie-Regeln (größter Hebel):**
1. **`Decision` als Node ist verboten** → Entscheidungen/Würfe werden Array-Properties (`decisions[]`, `rolls_by_scene`) am zugehörigen `Event`.
2. **Eine Quest = ein persistenter Node** mit `status`-Historie (`valid_from`); keine Neu-Extraktion pro Session/Formulierung.
3. **Kanonische Entitäts-Auflösung vor Insert** (Alias-/Fuzzy-Matching gegen Bestand) — Pflicht wegen Whisper-Schreibvarianten.
4. **Ein einziger Provenance-Mechanismus** (`IN_SESSION` **oder** `evidence_chunks`) für **alle** Entitätstypen; `APPEARS_IN` streichen.
5. **Rules-Layer strikt trennen:** Session-Mentions verlinken auf kanonische `:RuleEntity {source:'SRD'}`; keine neuen medium-conf-Regel-Nodes.

---

## 7. Zielbild für diese Pipeline

- **Behalten im kanonischen Graphen:** Characters (PC/NPC nach Auflösung), Factions, Locations, benannte Artefakte (Voodoo-Puppe, Sigille, Schriftrollen), Makro-Events, je **eine** Quest pro Handlungsstrang, Player↔Character-Mapping.
- **Als Claim mit Provenance speichern:** „Zweite Partei"/Lara-Hintergrund, soziale Momentaufnahmen (`HOSTILE_TO`/`FEARS`), Gerüchte/Warnungen (Phipps' Spuk-Warnung).
- **Nur im RAG-/Quellenlayer:** wörtliche Dialoge, Würfelergebnisse, Mechanik-Calls (Prey Dice, Winged Sentinel, Double Tap), `:Chunk` + `MENTIONS`.
- **Nur nach Human Review übernehmen:** Tindrail↔Kind↔Tindra-Auftrennung, Krypta/Dungeon/Bossraum-Merge, HeilendeHand↔MendingTouch, Gilde↔Gildenhalle.
- **Deterministisch validieren:** verbotener Node-Typ `Decision`; widersprüchliche `Quest.status`; Node-Typen ohne Provenance; RuleEntity ohne SRD-Link; bidirektionale/Selbst-Duplikat-Kanten.

---

## 8. Priorisierter Maßnahmenplan

| Priorität | Maßnahme | Kategorie | Erwarteter Nutzen | Aufwand |
|---|---|---|---|---|
| P0 | Tindrail/Timrell/Tindra entwirren; Lanra→Cookie; Leandras/Magier & Häuser mergen | Datenbereinigung dieser Session + Human-in-the-loop | Korrekte Identitäten, saubere Retrieval-Anker | M |
| P0 | `NPC_Walk`, `RULE_CLASS_Blizzard`, `RULE_ANCESTRY_Maus`, `EVT_SessionOpening…` entfernen | Datenbereinigung | Halluzinationen raus, Evidenztreue ↑ | S |
| P0 | Quests konsolidieren (8→1 Goblin-Verteidigung, 4→1 Krypta) + Status-Timeline | Ontologie + Datenbereinigung | Kein widersprüchlicher Zustand, saubere Queries | M |
| P1 | `Decision`-Nodes → `decisions[]`/`rolls_by_scene` am Event; `DECIDED` entfernen | Extraktionsprompt + Ontologie | −39 Nodes/−38 Kanten, Doktrin-konform | M |
| P1 | 04-01 PCs (Cookie/Esterossa/Dodo) + Player→Character-Mapping nachziehen | Datenbereinigung + Extraktionsprompt | Under-Extraction behoben, konsistente Teilnahme | M |
| P1 | Entitäts-Resolver (Alias/Fuzzy) als Ingestion-Schritt | Extraktionsprompt/Pipeline | Verhindert Whisper-Duplikate künftig | L |
| P1 | Location-Merges (Goblin-Camp ×3, Breska/Dorf, Krypta-Komplex) | Datenbereinigung + Human-in-the-loop | Korrekte Topologie | M |
| P2 | Provenance vereinheitlichen (`IN_SESSION` für alle Typen, `APPEARS_IN` streichen); `ALLIED_WITH`→Party-`MEMBER_OF`; `RELATES_TO` löschen | Ontologie | Kompaktes, konsistentes Vokabular | M |
| P2 | Temporale Versionierung (`valid_from/valid_to`) für status/Besitz/Mitgliedschaft/Gefühle | Neo4j-Schema | Zeitlichkeitsrisiko ↓ | L |
| P2 | Rules-Layer trennen; Session-Mentions auf SRD-Nodes verlinken | RAG/Provenance | Kein Regel-Rauschen im Weltmodell | M |
| P3 | Neo4j-Constraints/Uniqueness + Validierungsjob (siehe Akzeptanztests) | Neo4j-Constraints/Deterministische Validierung | Regressionsschutz | S |

### Drei Akzeptanztests für die nächste Session

1. **Kein verbotener Node-Typ & keine Status-Kollision:** `MATCH (d:Entity {type:'Decision'}) RETURN count(d)` = **0**, und keine Quest-Gruppe (nach Auflösung: gleicher `canonical_id`) besitzt gleichzeitig `status ∈ {open/new}` **und** `completed`. → muss leer/0 sein.
2. **Provenance vollständig:** Jede `:Entity` (außer `source:'SRD'`) hat mindestens **eine** Session-Provenance (`IN_SESSION` **oder** `evidence_chunks ≠ []`); jede Fähigkeit/Regel-Referenz zeigt auf einen `:RuleEntity {source:'SRD'}`. → 0 Verstöße.
3. **Identitäts-/Duplikat-Gate:** Kein Paar aktiver Entitäten desselben Typs mit Namens-Ähnlichkeit ≥ 0.9 (bzw. Alias-Überschneidung) ohne Review-Flag; keine bidirektionalen oder Selbst-Duplikat-Kanten (`a-[:ALLIED_WITH]->b` **und** `b-[:ALLIED_WITH]->a`). → 0 offene Treffer.
