# Session Report S17 — 2025-08-05

---

## 0. Meta

| Feld | Wert |
|---|---|
| **Session-ID** | S17 |
| **Datum** | 2025-08-05 |
| **Quell-Datei** | `2025-08-05_RF_cRNIWJz_ATo.txt` |
| **Datei-Größe** | 3 516 Bytes (stark gekürzt; .json: 4 853 Bytes) |
| **YouTube-URL** | https://www.youtube.com/watch?v=cRNIWJz_ATo |
| **Session-Typ** | Tavernen-Action (Side-Episode; keine offizielle Gilden-Mission) |
| **Anwesend (bestätigt)** | Deniz (GM), Marco/Dodo, Katha/Nyrella, Celin/Cookie, Micha/Rotunas, Tim/Lindo Laut, Basti/Esterossa |
| **Sitzungszahl Spieler** | 6 (größte Runde bisher) |
| **Kontinuität** | Steht nach S16 (Windung-Bogen); narrative Brücke unklar, da kein Spielinhalt im Transkript |

---

## 1. Zusammenfassung

**⚠️ Transkript stark gekürzt — kein auswertbarer Spielinhalt vorhanden.**

Das verfügbare Transkript umfasst ausschließlich die technischen Eröffnungsminuten der Sitzung (ca. 3:23 min) und bricht mitten in einem Satz ab. Kein Dialog, keine Würfelwürfe, keine Handlung, keine NPC-Interaktionen wurden aufgezeichnet.

Was aus den ersten ~3 Minuten hervorgeht:

- Deniz (GM) begrüßt die Gruppe mit Entschuldigung für Verspätung und technische Probleme.
- Die heutige Sitzung ist eine **Tavernen-Action** — kein Gildenwappen, kein offizielles Missionsschild, kein Level-Eintrag. Explizit als Erholungs- und Erzählepisode geplant.
- Erstmals **sechs Spielende** gleichzeitig: Marco (Dodo), Katha (Nyrella), Celin (Cookie), Micha (Rotunas), Tim (Lindo Laut), Basti (Esterossa).
- Deniz verliest die Charakternamen von einer Liste — mit kleinen Versprechern (nennt Rotunas zuerst „Victor Eugénie" / „Valeria", wird von Celin korrigiert).
- Technische Probleme: Talespire stürzt ab; allgemeiner Tontest wird durchgeführt.
- Geplante Aktivität: „Ihr dürft einfach Geschichten erzählen. Ihr dürft auch einfach die Taverne ein bisschen erkunden. Ihr dürft mit den Leuten quatschen."

Da das Transkript abbricht, bevor irgendetwas in der Spielwelt stattgefunden hat, können keine Szenen, Würfelwürfe, Entitäten-Updates oder Plot-Entwicklungen dokumentiert werden.

---

## 2. Szenen

*Keine dokumentierbaren Szenen — Transkript endet im technischen Setup.*

---

## 3. Anhang

### 3.1 Anwesenheit

| Spieler | Charakter | Anwesend |
|---|---|---|
| Deniz | GM | ✓ |
| Marco | Dodo | ✓ |
| Katha | Nyrella | ✓ |
| Celin | Cookie | ✓ |
| Micha | Rotunas | ✓ |
| Tim | Lindo Laut | ✓ |
| Basti | Esterossa | ✓ |

### 3.2 Neue Entitäten

*Keine (kein Spielinhalt).*

### 3.3 Entitäten-Updates

*Keine (kein Spielinhalt).*

---

## 4. Unsicherheiten

1. **Transkript-Vollständigkeit:** Die Quell-Datei ist mit 3 516 Bytes um ca. 97 % kleiner als ein typisches Sitzungs-Transkript (~100 KB). Ursache unklar — möglicherweise Fehler beim Crawl/Transcription-Prozess. Der tatsächliche Spielinhalt ist unbekannt.
2. **Narrative Einordnung:** Unklar, ob diese Tavernen-Episode zwischen S16 (Windung) und S18 relevant für die Haupthandlung ist oder rein episodisch bleibt.
3. **Charaktername-Fehler:** Deniz nennt Rotunas zunächst „Victor Eugénie" und „Valeria" — unklar ob Vertipper auf seiner Charakterliste oder Referenz auf einen anderen Charakter. Wird als Versprecher behandelt.
4. **Session-Nummerierung:** Deniz erwähnt „Folge 16" — seine interne Zählung. Unsere chronologische Zählung ist S17.

---

## 5. Taxonomie-Erweiterungen

*Keine neuen Entitäts-Typen oder Schema-Erweiterungen.*

---

## 6. Wissensgraph

```json
{
  "session": "S17",
  "date": "2025-08-05",
  "notes": "Transkript stark gekürzt — kein auswertbarer Spielinhalt. Minimaler Graph mit Anwesenheits-Bestätigung.",
  "nodes": [
    {"id": "CHAR_LindoLaut", "type": "Character", "name": "Lindo Laut", "attributes": {"is_pc": true, "player_ref": "Tim", "class_subclass": "Bard/Fae", "can_fly": true}, "evidence_scenes": ["S17-meta"]},
    {"id": "CHAR_Celin_Cookie", "type": "Character", "name": "Cookie", "attributes": {"is_pc": true, "player_ref": "Celin", "class_subclass": "Ranger/Beastbound"}, "evidence_scenes": ["S17-meta"]},
    {"id": "CHAR_Basti_Esterossa", "type": "Character", "name": "Esterossa", "attributes": {"is_pc": true, "player_ref": "Basti", "class_subclass": "Seraph", "can_fly": true}, "evidence_scenes": ["S17-meta"]},
    {"id": "CHAR_Micha_Rotunas", "type": "Character", "name": "Rotunas", "attributes": {"is_pc": true, "player_ref": "Micha", "class_subclass": "Wizard/Battlemage"}, "evidence_scenes": ["S17-meta"]},
    {"id": "CHAR_Deniz_GM", "type": "Character", "name": "Deniz", "attributes": {"is_pc": false, "subtype": "GM"}, "evidence_scenes": ["S17-meta"]},
    {"id": "CHAR_Marco_Dodo", "type": "Character", "name": "Dodo", "attributes": {"is_pc": true, "player_ref": "Marco", "class_subclass": "unbekannt"}, "evidence_scenes": ["S17-meta"]},
    {"id": "CHAR_Katha_Nyrella", "type": "Character", "name": "Nyrella", "attributes": {"is_pc": true, "player_ref": "Katha", "class_subclass": "Ranger/Beastbound", "species": "Freeborn Fairy", "companion_name": "Nyruk"}, "evidence_scenes": ["S17-meta"]}
  ],
  "edges": [
    {"source": "CHAR_LindoLaut", "target": "CHAR_Deniz_GM", "relation": "NIMMT_TEIL_AN_SESSION", "confidence": "hoch", "attributes": {"session": "S17", "session_typ": "Tavernen-Action"}},
    {"source": "CHAR_Celin_Cookie", "target": "CHAR_Deniz_GM", "relation": "NIMMT_TEIL_AN_SESSION", "confidence": "hoch", "attributes": {"session": "S17"}},
    {"source": "CHAR_Basti_Esterossa", "target": "CHAR_Deniz_GM", "relation": "NIMMT_TEIL_AN_SESSION", "confidence": "hoch", "attributes": {"session": "S17"}},
    {"source": "CHAR_Micha_Rotunas", "target": "CHAR_Deniz_GM", "relation": "NIMMT_TEIL_AN_SESSION", "confidence": "hoch", "attributes": {"session": "S17"}},
    {"source": "CHAR_Marco_Dodo", "target": "CHAR_Deniz_GM", "relation": "NIMMT_TEIL_AN_SESSION", "confidence": "hoch", "attributes": {"session": "S17"}},
    {"source": "CHAR_Katha_Nyrella", "target": "CHAR_Deniz_GM", "relation": "NIMMT_TEIL_AN_SESSION", "confidence": "hoch", "attributes": {"session": "S17"}}
  ]
}
```

---

## 7. Würfelprotokoll

```csv
Szene,Zeitstempel,Spieler,Charakter,Wurf-Typ,Modifikator,Ergebnis_Gesamt,DC_oder_Kontext,Erfolg,Notiz
S17-meta,00:00:00,—,—,—,—,—,—,—,Kein Spielinhalt im Transkript dokumentiert
```
