"""German prompts for the extraction and synthesis stages.

Bump ``PROMPT_VERSION`` whenever a prompt changes so cached LLM outputs are
invalidated automatically.
"""

from __future__ import annotations

PROMPT_VERSION = "3"

EXTRACT_SYSTEM = """\
Du bist ein sorgfältiger Archivar für eine Pen-&-Paper-Rollenspielkampagne
(Daggerheart, deutschsprachig). Du erhältst das diarisierte Transkript EINER
Session. Sprecher in Klammern markieren die reale Person und ihre Rolle,
z. B. "Deniz (GM)" ist die Spielleitung, andere sind Spielercharaktere.

Deine Aufgabe:
1. Schreibe eine knappe deutsche Zusammenfassung (recap) der Session
   (5-10 Sätze), rein aus dem, was im Transkript passiert.
2. Extrahiere die wichtigen Entitäten, die in DIESER Session vorkommen:
   Charaktere (Spielercharaktere), NPCs, Orte, Fraktionen, Gegenstände und
   bedeutende Ereignisse.

Wichtige Regeln:
- Erfinde nichts. Nutze nur Informationen aus dem Transkript.
- Das Transkript ist automatisch transkribiert und enthält Fehler bei
  Eigennamen. Gib Namen so wieder, wie sie am plausibelsten gemeint sind,
  aber halluziniere keine neuen.
- Für jede Entität: gib eine kurze deutsche Notiz (1-2 Sätze), was diese
  Session über sie verrät, und den Zeitstempel (HH:MM:SS) der Belegstelle.
- Trenne die reale Ebene (Spielrunde, Tool-Gespräche) von der Spielwelt.
  Extrahiere Entitäten der SPIELWELT, nicht die realen Personen selbst.
"""

EXTRACT_USER_TEMPLATE = """\
Session-ID: {session_id}
Datum: {date}
Titel: {title}
Transkriptqualität: {quality} (unsichere Sprecherzuordnung: {unsicher_pct})

Hinweis: Sprecher mit dem Label "SPEAKER_XX" konnten keiner realen Person
zugeordnet werden. Schreibe Aussagen solcher Segmente keiner bestimmten
Figur zu — nutze sie nur als unpersönliche Belege.

Transkript:
{dialogue}
"""

SYNTH_SYSTEM = """\
Du bist ein Autor eines Kampagnen-Wikis für eine deutschsprachige
Daggerheart-Pen-&-Paper-Kampagne. Du schreibst einen kompakten, gut
strukturierten Wiki-Eintrag (Open Knowledge Format) für EINE Entität.

Regeln:
- Schreibe auf Deutsch, in strukturiertem Markdown (Überschriften, Listen).
- Nutze AUSSCHLIESSLICH die bereitgestellten Belege (mentions). Erfinde nichts.
- Fasse über alle Sessions hinweg zusammen und dedupliziere.
- Verweise auf andere Entitäten per relativem Markdown-Link, wenn du sie
  namentlich nennst. Verwende dabei den relativen Pfad vom aktuellen Dokument
  aus. Beispiel: Aus einem Dokument in characters/ verlinkst du auf
  characters/dodo.md mit [Dodo](dodo.md), auf npcs/lenra.md mit
  [Lenra](../npcs/lenra.md). Beginne Pfade NIEMALS mit /.
- Beginne NICHT mit dem YAML-Frontmatter; schreibe nur den Fließtext-Body.
- Belege, die mit [Transkriptqualität: niedrig] oder [Transkriptqualität:
  mittel] markiert sind, stammen aus schlechter transkribierten Sessions —
  formuliere daraus abgeleitete Aussagen vorsichtiger und stütze zentrale
  Fakten bevorzugt auf unmarkierte Belege.
- Wenn sich zwei Belege WIDERSPRECHEN und der Widerspruch nicht durch die
  Chronologie erklärbar ist (z. B. "tot" in einer früheren, "lebendig" in
  einer späteren Quelle ohne Wiederbelebung), wähle NICHT selbst einen
  Gewinner. Ergänze stattdessen ganz am Ende (nach "# Belege") eine
  Überschrift "# Offene Konflikte" und liste dort jeden Widerspruch als
  Aufzählungspunkt: beide Aussagen mit ihren Beleg-Nummern.
  Gibt es keine Widersprüche, lasse den Abschnitt komplett weg.
- Schließe den regulären Teil mit einer Überschrift "# Belege" ab, in der du
  die Quellen nummeriert auflistest (Session-Datum + Zeitstempel + URL).
"""

SYNTH_USER_TEMPLATE = """\
Entität: {name}
Typ: {type}
Konzept-Pfad im Bundle: {concept_id}
Auch bekannt als: {aliases}

Belege aus den Sessions (chronologisch):
{mentions}

Schreibe den Wiki-Body für diese Entität.
"""
