# Bloat-Analyse Knowledge-Graph — 2 volle Sessions (2025-04-01 + 2025-04-09)

Analysiert: `docs/neo4j_export-data-2025-04-01-and-2025-04-09.json`
(Live-Export `:7687`, **1063 Knoten, 1498 Kanten**, zwei vollständige Sessions).
Follow-up zur Ein-Drittel-Analyse in `KG_Qualitaetsanalyse_S01_20250326.md` —
diesmal voller Input, zwei Sessions, damit die Skalierung des Problems sichtbar
wird. Vermessen am 2026-07-12.

---

## Executive Summary

Der Graph ist zu ~2/3 Müll, und die zwei größten Quellen sind **Trait-Spam**
und **konsequenzlose Events**. Beide entstehen an der Quelle (Extraction), nicht
downstream. Der WP6b-Aggregationsmechanismus (wiederkehrendes Verhalten
hochzählen) ist durch die Daten **widerlegt**: alle 374 Trait-Kanten haben
`count = 1`. Events sind strukturell von ihren Konsequenzen entkoppelt: **0 %**
der 346 Events tragen eine Consequence-Edge (`ROLLED`/`TARGETS`/`RESULTED_IN`) —
diese Kantentypen zeigen per Ontologie auf `RollEvent`/`Character`, nie auf ein
`Event`.

Architektur-Entscheidung des Auftraggebers dazu: **Downstream-Pruning (Müll
erzeugen und per Skript löschen) ist ein Anti-Pattern.** Fix gehört in die
Extraktions-Schicht. Plan: `evolution/12_extraction_quality_overhaul.md`.

## Kennzahlen

| Metrik | Wert | Einordnung |
|---|---|---|
| Knoten (unique) | 1063 | |
| Kanten (unique) | 1498 | |
| **Trait-Knoten** | **374 (35 %)** | mehr als Character+Location+Item+Quest+Faction zusammen |
| `KNOWN_FOR count`-Histogramm | **`{1: 374}`** | Aggregation zu 100 % tot — jeder Trait ein Singleton |
| **Event-Knoten** | **346** | ~173/Session (Gate im Prompt sagt „nur State-Changes") |
| Events ohne jede Nicht-Anchor-Kante (Orphan) | **115 (33 %)** | hängen nur per `IN_SESSION` an der Session |
| **Events mit strikter Consequence-Edge** | **0 (0 %)** | `ROLLED`/`TARGETS`/`RESULTED_IN` treffen nie ein Event |
| Events mit `PARTICIPATED_IN` | 199 (57 %) | Teilnehmer ≠ Konsequenz („Dodo considers healing" hat Dodo) |
| Vollständig kantenlose Knoten | 116 | Quest 40/45, Item 32, Location 28, RuleEntity 11, Faction 5 |
| `RELATES_TO`-Kanten (off-vocab Sammelbecken) | 75 | |
| Inverse-Paar `OWNS`/`OWNED_BY` | 22 / 39 | eine Richtung sollte gefaltet sein (resolve.py:560) — Altdaten oder Lücke |

## Root Cause (belegt im Code, nicht vermutet)

### 1. Trait-Flut — der Prompt IST das Auffangbecken
`_EVENT_PROMPT` (`extract.py:40-41`) instruiert wörtlich: *„If it's ambient/
flavor color … do NOT create an event; **instead extract it as a trait.**"*
Trait ist als Dump für jede Flavor-Zeile designt → 374 Stück.

Zwei strukturelle Fehler verstärken es:
- **„Recurring" ist per-Chunk unentscheidbar.** `Trait` (`schema.py:71`) verlangt
  wiederkehrende Charakterisierung; ein Chunk sieht ein einzelnes Verhalten,
  formuliert es jedes Mal anders → jeder Slug neu → `count=1`.
- **Kein Consolidation-Pass für Traits.** Events haben N3
  (`propose_event_groups`); Traits haben nichts. Near-Dups kollabieren nie.

### 2. Konsequenzlose Events — Gate ignoriert + Title-only erlaubt
Der Event-Gate im Prompt (`extract.py:36-40`) ist gut formuliert, aber:
- Kriterien (c) „caused/resulted" und (d) „referenced later" sind **per-Chunk
  unprüfbar** → das Modell rät großzügig, über-extrahiert.
- `Event.participants: list[str] = []` (`schema.py:34`) default leer → nichts
  zwingt einen Teilnehmer → Title-only Events = die 115 Orphans.
- Kein Feld verlinkt ein Event mit einem Roll/Result → **0 %** strikte
  Consequence-Edges. `ROLLED` läuft Character→RollEvent, nicht Event→irgendwas.

### 3. Kantenlose Backbone-Nodes
40 von 45 Quests, 32 Items, 28 Locations werden gemintet und nie verlinkt.
`register()` (`resolve.py`) gibt Location/Item-ohne-Owner/Faction/Quest keine
Anchor-Kante — sie landen kantenlos, außer eine `relationships`-Zeile
referenziert sie zufällig.

## Warum kein Downstream-Prune

Ein deterministischer Orphan-Sweep würde alle drei Symptome erschlagen — aber
er erzeugt erst Müll und wirft ihn dann weg. Entscheidung: an der Wurzel fixen
(Schema erzwingt Signifikanz, Trait-Topologie entfällt an der Quelle,
Scene-level Chunks geben dem Modell den narrativen Bogen). Ein optionaler,
**manuell getriggerter** Cleanup bleibt für Alt-/Restdaten erlaubt, aber nie im
`ingest`-Hot-Path.

## Verweise
- Plan: `../evolution/12_extraction_quality_overhaul.md`
- Vorläufer (1/3 Input, 1 Session): `KG_Qualitaetsanalyse_S01_20250326.md`
- Reverted Scene-Noise (verwandtes Bloat-Muster): `MIGRATION_NOTES.md` §M2
