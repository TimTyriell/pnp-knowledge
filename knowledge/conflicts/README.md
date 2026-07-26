# Konflikt-Queue

Jede Datei hier ist ein Widerspruch, den die Synthese **nicht** selbst
auflösen durfte: zwei Belege sagen Unvereinbares, und die Chronologie erklärt
es nicht. Das Modell wählt in so einem Fall bewusst keinen Gewinner.

## Der Grundsatz

> Konflikte werden **niemals im Bundle** gelöst.

`knowledge/bundle/` ist generierte Ausgabe. Jeder `pnp run` überschreibt sie —
ein Kommentar oder eine Korrektur direkt in `characters/dodo.md` ist beim
nächsten Lauf verschwunden. Gelöst wird immer an einem **Eingang**.

## Welcher Eingang? Zwei Fragen

**1. „Sind hier zwei Dinge zu einem geworden — oder eines fälschlich zu zweien?"**
→ Identitätsproblem → `entity_registry.yaml`

| Fall | Eintrag |
|---|---|
| Zwei Schreibweisen derselben Figur | `merge:` — `"warzul": deities/vharzul` |
| Zwei *verschiedene* Figuren wurden zusammengelegt | Merge-Key entfernen **und** Paar in `never_merge:` eintragen |
| Nebenname fehlt | `aliases:` beim Konzept |

`never_merge:` ist wichtig: ohne den Eintrag schlägt der nächste
`pnp dedup`-Lauf dieselbe Zusammenlegung wieder vor, und dieselbe Ablehnung
muss erneut entschieden werden. Beispiel: Myko (Willauch-Gruppe) und Miqo
(Kinder aus Abisalis) sind zwei Spieler, deren Namen sich fast gleichen.

**2. „Was stimmt eigentlich?"**
→ Kanon-Frage, die nur die Spielleitung beantworten kann
→ `knowledge/sources/Kanon_Entscheidungen.md`

Abschnitt `### <Entitätsname>`, Text beginnt mit `ENTSCHEIDUNG:`. Nur dieses
Schlüsselwort gibt der Festlegung Vorrang vor widersprechenden Session-Belegen
und nimmt den Punkt aus `# Offene Konflikte` heraus.

Häufig ist ein „Konflikt" auch gar keiner, sondern **Chronologie** — eine
Figur wechselt die Waffe, eine Stadt wird zerstört, jemand ändert die Seite.
Dann sagt die Entscheidung genau das: *„kein Widerspruch, sondern Abfolge"*.

## Ablauf

```
1. pnp run                     → Konflikte landen hier
2. Datei lesen, Frage 1 / 2 anwenden
3. Eingang bearbeiten          → registry.yaml  oder  sources/Kanon_Entscheidungen.md
4. pnp run                     → betroffene Einträge werden neu geschrieben,
                                 gelöste Konfliktdateien verschwinden von selbst
```

Schritt 4 ist billig: der Cache-Schlüssel der Synthese enthält den Hash der
zugehörigen Quellen. Eine neue `ENTSCHEIDUNG:` zu Dodo schreibt **nur** Dodo
neu — die übrigen ~730 Einträge bleiben Cache-Treffer, es fallen keine
weiteren Modellkosten an.

Gelöste Konfliktdateien müssen **nicht** von Hand gelöscht werden; `pnp run`
räumt sie ab, sobald der Widerspruch nicht mehr auftritt. Bleibt eine Datei
bestehen, wurde der Widerspruch also noch nicht wirklich ausgeräumt.

## Unsicherheit ist erlaubt

Nicht jeder Konflikt braucht eine harte Antwort. Wenn im Spiel schlicht noch
nicht bekannt ist, was gilt, gehört genau das in die Entscheidung — mit der
Auflage, es als Vermutung zu kennzeichnen. Siehe den Eintrag zu den
Silberkernen: zwei Anführer sind bekannt, der Rest bleibt ausdrücklich offen
und wird im Eintrag als unbestätigt markiert, statt mit Spekulation gefüllt zu
werden, die wie eine Tatsache klingt.
