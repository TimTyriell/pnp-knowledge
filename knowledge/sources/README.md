# knowledge/sources/

Weltwissen, das in keinem Transkript steht: Regelwerk, In-Game-Schriften,
Kanon-Entscheidungen der Spielleitung, von Hand bearbeitete Wiki-Prosa.

Das Bundle ist generierte Ausgabe und wird bei jedem Lauf überschrieben — was
hier steht, überlebt jede Regeneration und wird bei der Synthese wieder in den
Prompt gelegt. Gelesen von `context.load_sources` (`services/kb`).

## Der Vertrag

Ein Abschnitt erreicht eine Entität nur über seinen **Namen** oder über eine
**Direktive**. Passt keins von beidem, wird er nie injiziert — die Datei sieht
korrekt aus und im Ergebnis fehlt er lautlos. Genau das war 2026-09 bei 70 von
137 Abschnitten der Fall (~60 % des Ordners), darunter die gesamte
Wiki-Prosa zu den vier Spielercharakteren.

* **Eine `##`-Überschrift pro Entität.** Unterabschnitte (`###`) erben die
  Entität der Überschrift, unter der sie stehen — Anker und Unterabschnitte
  gehören zusammen in eine Datei.
* **Direktive Pflicht** bei neuen Abschnitten:
  `<!-- okf: entity=<concept_id> -->`, `concept_id` aus
  `entity_registry.yaml`, mehrere kommagetrennt. Die Zeile wird beim Laden
  entfernt und erscheint nie in einem Prompt. Ohne sie greift nur noch die
  Namenssuche, und die bricht beim nächsten Rename.
  Optional `; mentions=off` — hält die Festlegung aus Einträgen heraus, die
  die Entität nur beiläufig erwähnen.
* **Nur zwei Marker**, alles andere ist gewöhnliche Referenz-Lore:
  * `ENTSCHEIDUNG:` — Weltfakt. Hat Vorrang vor widersprechenden
    Session-Belegen und nimmt den Punkt aus „# Offene Konflikte".
  * `DARSTELLUNG:` — Anweisung zur *Form* des Eintrags (Länge, Vorsicht bei
    Unsicherem, Kennzeichnung als Gerücht).

  Nur markierte Abschnitte reichen an Einträge weiter, die die Entität bloß
  erwähnen. Reine Lore tut das nicht: eine generische Überschrift wie
  „Fähigkeiten" landete sonst in 27 fremden Einträgen unter der Überschrift
  „Festlegungen zu ANDEREN Entitäten".
* **Keine `[n]`-Belegmarker, kein `Belege`-Abschnitt.** Im Prompt bedeutet
  `[n]` die n-te Erwähnung *dieser* Entität; eine mitkopierte Nummer wird zu
  einer falschen Episoden-Kennung umgeschrieben. Beides wird beim Laden
  entfernt, aber schreib es gar nicht erst hinein.
* **Erzähltext gehört nicht hierher.** Ausgeschriebene Prosa ohne zitierbare
  Session-Fundstelle → `../narrative/` (siehe dortige README).

## Wiki-Prosa übernehmen

Nicht von Hand kopieren — das hat die Bindung schon einmal zerstört:

```
cd services/kb && python sync_harvest.py [--dry-run]
```

Liest `pnp-export-data/harvest/*.md` (der Dateiname trägt bereits die
`concept_id`), schreibt `sources/wiki/<concept>.md` mit gesetzter Direktive,
wandelt Wikitext in Markdown und entfernt Belege und `[n]`-Marker.

## Prüfen

```
cd services/kb && python sources_doctor.py     # tot / zu breit / zu groß / ohne Direktive
cd services/kb && python -m pytest tests/test_canon_decisions.py
```

`sources_doctor.py` listet außerdem **deep-tier-Entitäten ganz ohne Quelle**,
nach Erwähnungen sortiert — die Arbeitsliste dafür, worüber sich zu schreiben
lohnt.
