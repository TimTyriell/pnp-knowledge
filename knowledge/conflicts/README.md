# Konflikt-Queue

Jede Datei hier ist ein Widerspruch, den die Synthese **nicht** selbst
auflösen durfte: zwei Belege sagen Unvereinbares, und die Chronologie erklärt
es nicht. Das Modell wählt in so einem Fall bewusst keinen Gewinner.

## Der Grundsatz

> Konflikte werden **niemals im Bundle** gelöst — und diese Datei hier
> gehört selbst dazu.

`knowledge/bundle/` ist generierte Ausgabe. Jeder `pnp run` überschreibt sie —
ein Kommentar oder eine Korrektur direkt in `characters/dodo.md` ist beim
nächsten Lauf verschwunden. Gelöst wird immer an einem **Eingang**.

Das gilt auch für die Datei, die gerade den Konflikt beschreibt: sie liegt
zwar nicht unter `bundle/`, wird aber genauso bei jedem `pnp run` neu
geschrieben (`emit_conflict()`, unbedingt, ohne die alte Datei zu lesen).
Ein Status-Feld hier auf `resolved` setzen, den Text ändern oder die Datei
von Hand löschen sieht wie eine Lösung aus, ist aber ein No-Op — beim nächsten
Lauf kommt exakt dieselbe Datei zurück, solange sich am **Eingang** nichts
geändert hat, denn der Synthese-Cache kennt diese Queue gar nicht. Editieren
lohnt sich nur an den beiden Eingängen unten.

## Welcher Eingang? Zwei Fragen

**1. „Sind hier zwei Dinge zu einem geworden — oder eines fälschlich zu zweien?"**
→ Identitätsproblem → `entity_rules.yaml`

**Nicht** `entity_registry.yaml`: die Registry ist generierte Ausgabe wie das
Bundle, jeder Lauf schreibt sie komplett neu. Ein `merge:`-Eintrag, der dort
statt in `entity_rules.yaml` landet, wird beim nächsten `pnp run`
stillschweigend verworfen (`resolve.write_registry` behält eine `merge:`-Zeile
in der Registry nur, solange sie *nicht* bereits nach `entity_rules.yaml`
migriert ist) — die "Lösung" wirkt getroffen und ist es nicht.

| Fall | Eintrag |
|---|---|
| Zwei Schreibweisen derselben Figur | `merge:` — `"warzul": deities/vharzul` |
| Zwei *verschiedene* Figuren wurden zusammengelegt | Merge-Key entfernen **und** Paar in `never_merge:` eintragen |
| Nebenname fehlt | `aliases:` beim Konzept in `entity_registry.yaml` (dort *wird* eine bestehende Alias-Liste beim Schreiben erhalten, siehe oben — nur `merge:`/`never_merge:`/`ignore:`/`split:`/`canonical_name:`/`important:`/`alias_block:` gehören nach `entity_rules.yaml`) |

`never_merge:` ist wichtig: ohne den Eintrag schlägt der nächste
`pnp dedup`-Lauf dieselbe Zusammenlegung wieder vor, und dieselbe Ablehnung
muss erneut entschieden werden. Beispiel: Myko (Willauch-Gruppe) und Miqo
(Kinder aus Abisalis) sind zwei Spieler, deren Namen sich fast gleichen.

**2. „Was stimmt eigentlich?"**
→ Kanon-Frage, die nur die Spielleitung beantworten kann
→ `knowledge/sources/Kanon_Entscheidungen.md`

Abschnitt `### <Entitätsname>`, direkt darunter eine Zeile
`<!-- okf: entity=<concept_id> -->` — das bindet die Festlegung an einen
konkreten Bundle-Eintrag (mehrere `concept_id`s, kommagetrennt, wenn sie
mehrere Einträge betrifft). Diese Zeile wird beim Laden entfernt und
erscheint nie in einem Prompt.

Der Text darunter beginnt mit einem von zwei Schlüsselwörtern:
- `ENTSCHEIDUNG:` — ein Weltfakt, hat Vorrang vor widersprechenden
  Session-Belegen und nimmt den Punkt aus `# Offene Konflikte` heraus.
- `DARSTELLUNG:` — keine Tatsachenfestlegung, sondern eine Anweisung zur
  Form des Eintrags (Länge, Vorsicht bei Unsicherem, Kennzeichnung als
  Gerücht).

Eine Festlegung reicht automatisch auch an Einträge weiter, die die
betroffene Entität nur namentlich erwähnen, nicht nur an ihren eigenen
Eintrag — dort zählt sie für Schreibweise, Identität und Fakten, aber nicht
als eigener Abschnitt und nicht als offener Konflikt. Mit
`<!-- okf: entity=…; mentions=off -->` lässt sich das für eine einzelne
Festlegung abschalten.

Häufig ist ein „Konflikt" auch gar keiner, sondern **Chronologie** — eine
Figur wechselt die Waffe, eine Stadt wird zerstört, jemand ändert die Seite.
Dann sagt die Entscheidung genau das: *„kein Widerspruch, sondern Abfolge"*.

## Ablauf

```
1. pnp run                     → Konflikte landen hier
2. Datei lesen, Frage 1 / 2 anwenden
3. Eingang bearbeiten          → entity_rules.yaml  oder  sources/Kanon_Entscheidungen.md
                                 (nicht die Konfliktdatei selbst, nicht entity_registry.yaml)
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

## Wenn die Entscheidung trotzdem nicht wirkt

Mit einer `<!-- okf: entity=<concept_id> -->`-Zeile erreicht die Festlegung
genau die genannte(n) `concept_id`(s) — keine Namens-Rätselei mehr. Fehlt die
Zeile, greift zur Rückwärtskompatibilität die alte Suche: der
Überschriftentext (`### <Name>`) muss auf `canonical_name` oder einen Alias
matchen (`context.sources_for`). Drei Fallen, alle schon einmal echt
aufgetreten:

- Die `concept_id` in der Direktive existiert nicht (mehr) in
  `entity_registry.yaml` — meist eine Umbenennung, deren Direktive nicht
  mitgezogen wurde. Die Tests unter `services/kb/tests/test_canon_decisions.py`
  finden das; `pnp validate` nicht.
- Ohne Direktive: die Entität wurde umbenannt (`canonical_name:`-Pin in
  `entity_rules.yaml`), aber die Überschrift hier nennt noch den alten
  Namen — die Entscheidung greift dann für niemanden mehr.
- Zwei Überschriften mit demselben Namen: die zweite ergänzt die erste, statt
  sie zu ersetzen — beide werden injiziert, wo der Name matcht.

## Unsicherheit ist erlaubt

Nicht jeder Konflikt braucht eine harte Antwort. Wenn im Spiel schlicht noch
nicht bekannt ist, was gilt, gehört genau das in die Entscheidung — mit der
Auflage, es als Vermutung zu kennzeichnen. Siehe den Eintrag zu den
Silberkernen: zwei Anführer sind bekannt, der Rest bleibt ausdrücklich offen
und wird im Eintrag als unbestätigt markiert, statt mit Spekulation gefüllt zu
werden, die wie eine Tatsache klingt.
