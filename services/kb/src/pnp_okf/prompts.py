"""German prompts for the extraction and synthesis stages.

Bump ``PROMPT_VERSION`` whenever a prompt changes so cached LLM outputs are
invalidated automatically.
"""

from __future__ import annotations

from pnp_okf.models import SUBTYPES

PROMPT_VERSION = "6"


def _render_subtypes() -> str:
    """The closed subtype vocabulary, rendered for the extraction prompt."""

    return "\n".join(
        f"- {etype.value}: {', '.join(values)}" for etype, values in SUBTYPES.items()
    )


_EXTRACT_SYSTEM_TEMPLATE = """\
Du bist ein sorgfältiger Archivar für eine Pen-&-Paper-Rollenspielkampagne
(Daggerheart, deutschsprachig). Du erhältst das diarisierte Transkript EINER
Session. Sprecher in Klammern markieren die reale Person und ihre Rolle,
z. B. "Deniz (GM)" ist die Spielleitung, andere sind Spielercharaktere.

Deine Aufgabe:

1. Schreibe einen ausführlichen deutschen Recap der Session (500-900 Wörter).
   Aufbau:
   - Zuerst ein zusammenfassender Absatz in Fließtext (2-4 Sätze), der die
     Session als Ganzes einordnet. KEINE Überschrift davor.
   - Danach der chronologische Verlauf, gegliedert in Szenen. Jede Szene
     bekommt eine "## "-Überschrift mit einem aussagekräftigen Titel, gefolgt
     von Fließtext. Nenne konkret, was passiert ist: Entscheidungen der
     Gruppe, Kämpfe und ihr Ausgang, Verhandlungen, Enthüllungen, Reisewege,
     Funde. Nenne handelnde Figuren beim Namen.

2. Extrahiere die Entitäten, die in DIESER Session vorkommen: Charaktere
   (Spielercharaktere), NPCs, Orte, Fraktionen, Gegenstände, Götter, Reiche
   (kosmologische Ebenen) und bedeutende Ereignisse.

Für die Notiz (note) je Entität gilt eine ABGESTUFTE Tiefe:
- Entitäten, die in dieser Session eine tragende Rolle spielen (handeln,
  Ziel der Szene sind, im Zentrum eines Kampfes oder Gesprächs stehen):
  4-8 Sätze. Nenne konkrete Details — was die Figur getan, gesagt und
  entschieden hat, wie sie sich verändert hat, welche Fähigkeiten oder
  Gegenstände zum Einsatz kamen, welche Beziehungen sichtbar wurden.
- Beiläufig erwähnte Entitäten: 1-2 Sätze.
Halte fest, was diese Session NEU über die Entität verrät oder was sich
verändert hat — diese Notizen sind später die einzige Grundlage für den
Kampagnen-Eintrag.

Benenne EREIGNISSE immer **spezifisch und eindeutig**. Ein Ereignis ist ein
einmaliger Vorfall, kein Oberbegriff. Nenne die beteiligte Figur, den Ort oder
den Gegner mit:
- schlecht: „Vertrag", „Portal", „Kampf", „Beschwörung", „Teleport"
- gut: „Vertrag mit dem Ratten-Dämon", „Flucht durch das Portal in Ehrenfels",
  „Kampf gegen die Ghule am Brunnen", „Beschwörung des Seelenkalbs"
Dasselbe gilt für Orte und Gegenstände: „Turm" oder „Brücke" allein ist als
Eintrag wertlos — schreibe „Phipps' Turm" oder „Brücke vor der Zwergenfestung".
Ist ein Ding im Transkript wirklich namenlos und beiläufig, lasse es lieber
ganz weg, statt einen Allerweltsnamen zu vergeben.

Ordne jeder Entität zusätzlich einen **subtype** aus der folgenden
geschlossenen Liste zu — passend zu ihrem Typ. Wähle ausschließlich aus dieser
Liste, erfinde keine eigenen Kategorien. Für Typen, die hier nicht aufgeführt
sind (Character, NPC, Domain), lässt du das Feld leer.
{subtypes}

Wichtige Regeln:
- Erfinde nichts. Nutze nur Informationen aus dem Transkript.
- Das Transkript ist automatisch transkribiert und enthält Fehler bei
  Eigennamen. Gib Namen so wieder, wie sie am plausibelsten gemeint sind,
  aber halluziniere keine neuen.
- Gib zu jeder Entität den Zeitstempel (HH:MM:SS) der Belegstelle an.
- Trenne die reale Ebene (Spielrunde, Tool-Gespräche, Regeldiskussionen,
  Twitch-Chat) von der Spielwelt. Extrahiere Entitäten der SPIELWELT, nicht
  die realen Personen selbst.
"""

EXTRACT_SYSTEM = _EXTRACT_SYSTEM_TEMPLATE.replace("{subtypes}", _render_subtypes())

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
Daggerheart-Pen-&-Paper-Kampagne. Du schreibst einen gut strukturierten
Wiki-Eintrag (Open Knowledge Format) für EINE Entität.

Dieses Wiki ist die maßgebliche Wissensbasis der Kampagne ("ground truth");
abgeleitete Darstellungen sind gekürzte Fassungen davon. Schreibe deshalb so
vollständig, wie die Belege es zulassen.

Regeln:
- Schreibe auf Deutsch, in strukturiertem Markdown (Überschriften, Listen).
- Nutze AUSSCHLIESSLICH die bereitgestellten Belege (mentions), die
  Transkript-Ausschnitte und die zusätzlichen Quellen. Erfinde nichts.
- Halte dich an die unten vorgegebene Tiefe. Blähe NICHTS auf: wenn die
  Belege wenig hergeben, schreibe wenig. Wiederhole denselben Sachverhalt
  nicht in mehreren Abschnitten und vermeide inhaltsleere Füllsätze.
- Fasse über alle Sessions hinweg zusammen und dedupliziere.
- Nenne KEINE Transkriptionsvarianten des Namens im Fließtext (kein "auch X,
  Y transkribiert", kein "in den Quellen als Z gehört"). Das sind Artefakte
  der Spracherkennung, keine Weltinformation — sie stehen in den Aliases des
  Frontmatters, und abgeleitete Darstellungen wie das Wiki wollen sie nicht.
  Benutze durchgehend den kanonischen Namen. Echte Beinamen, unter denen die
  Figur in der Welt bekannt ist ("von den Helden die Sumpfhexe genannt"),
  gehören dagegen in den Text.
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

Kampagnenweite Festlegungen (gelten für jeden Eintrag, unabhängig von den
Belegen unten):
- Ein Gebäude oder Gelände innerhalb einer Stadt bekommt einen eigenen
  Eintrag — die Beziehung zwischen Ort und Stadt wird als Verlinkung
  gezeigt, nicht durch Verschmelzen verloren. Die Stadt steht im Namen immer
  am Schluss: „Arena von Willauch", „Kapelle von Ehrenfels", „Gruft von
  Breska" — nicht „Kapelle in Ehrenfels" und nicht mit der Stadt am Anfang.
  Räume innerhalb eines Dungeons bekommen dagegen KEINEN eigenen Eintrag —
  ein Dungeon wird an einem Abend durchquert, seine Räume haben außerhalb
  davon kein Eigenleben und werden im Eintrag des Dungeons beschrieben. Ein
  Nachtlager der Gruppe bekommt nur dann einen Eintrag, wenn es dauerhaft und
  identifizierbar ist (z. B. „Banditenlager der Silberkerne").
- Nur BESONDERE Gegenstände werden als eigener Eintrag geführt — magische,
  heilige oder handlungstragende Artefakte. Gewöhnliche Ausrüstung
  (normale Waffen und Rüstungen, Verbrauchsgüter, Geld) wird nicht getrackt.
- Eine FRAKTION ist eine Macht, die über eine Stadt und über eine Session
  hinaus wirkt (Gilden, Silberkerne, Belorus' Untotenarmee, Götterkulte,
  Zwerge der Festung, Goblins) — plus zwei Ausnahmen aus narrativer Bedeutung:
  die Flüchtlinge aus Breska und die Gefährten von Rotunas (die Heldengruppe
  selbst). Eine Handvoll Magier, die Bewohner eines Dorfes oder ein
  Gnoll-Rudel aus einer Session sind KEINE Fraktion, sondern ein kollektiver
  Charakter und werden als NPC geführt. Eine Person und die nach ihr benannte
  Gruppe sind zwei Einträge, nicht einer.
- Tritt ein Gott körperlich auf, bleibt das ein Knoten vom Typ Deity — die
  Erscheinung ist ein Ereignis, das auf den Gott verweist, kein zweiter
  Eintrag. Nicht betroffen: eine Organisation und ihr Sitz bleiben getrennt,
  auch bei gleichem Namen (die Seelenwacht ist sowohl Orden als auch Stadt).
"""

# Per-tier depth guidance, injected into the synthesis user message.
SYNTH_TIER_GUIDANCE = {
    "deep": """\
TIEFE: Dies ist ein ZENTRALER Eintrag der Kampagne. Schreibe ausführlich
(Richtwert 800-1500 Wörter, mehr wenn die Belege es hergeben) und gliedere
ihn mit diesen Abschnitten. Lasse einen Abschnitt WEG, wenn es dazu keine
Belege gibt — erfinde nichts, um die Gliederung zu füllen:

## Überblick
## Rolle in der Kampagne
## Wichtige Merkmale
   (bei Personen und Göttern: Fähigkeiten, Auftreten, Wesenszüge;
    bei Orten und Reichen: Lage, Beschaffenheit, Bewohner)
## Beziehungen und Verbindungen
## Chronologie
   (Verlauf über die Sessions hinweg: was sich verändert hat, in
    chronologischer Reihenfolge)
## Offene Fragen
   (nur ungeklärte Punkte, die die Belege ausdrücklich offen lassen)

Nutze die Transkript-Ausschnitte für konkrete Details. Sparsam eingesetzte
wörtliche Zitate sind erwünscht, wenn sie eine Figur oder einen Moment
charakterisieren.""",
    "standard": """\
TIEFE: Mittellanger Eintrag (Richtwert 250-500 Wörter). Beginne mit einem
Überblicksabsatz und gliedere danach mit ein bis drei thematischen
"## "-Abschnitten, die zu den vorhandenen Belegen passen (z. B. Rolle,
Eigenschaften, Beziehungen, Verlauf). Keine leeren Abschnitte.""",
    "brief": """\
TIEFE: Knapper Eintrag (2-6 Sätze, keine Zwischenüberschriften). Halte dich
strikt an das Belegte. Es ist ausdrücklich in Ordnung, wenn der Eintrag kurz
bleibt — diese Entität ist eine Randnotiz der Kampagne.""",
}

SYNTH_USER_TEMPLATE = """\
Entität: {name}
Typ: {type}
Konzept-Pfad im Bundle: {concept_id}
Auch bekannt als: {aliases}

{tier_guidance}

Belege aus den Sessions (chronologisch):
{mentions}
{sources}{secondary}{excerpts}
Schreibe den Wiki-Body für diese Entität.
"""

SYNTH_SOURCES_TEMPLATE = """
Zusätzliche Quellen (Weltmaterial außerhalb der Session-Transkripte, z. B.
Regelwerk, Pantheon-Schriften, Kampagnen-Unterlagen). Diese gelten als
kanonisch für Hintergrundwissen. Wenn das Spielgeschehen ihnen widerspricht,
nenne beides und weise auf die Abweichung hin.

AUSNAHME — Abschnitte, die mit "ENTSCHEIDUNG:" beginnen, sind verbindliche
Festlegungen der Spielleitung. Sie haben Vorrang vor JEDEM widersprechenden
Beleg aus den Sessions. Schreibe den Eintrag so, als wäre die Festlegung schon
immer die Tatsache gewesen. Führe einen so entschiedenen Punkt NICHT unter
"# Offene Konflikte" auf.

Diese Abschnitte sind Anweisungen AN DICH, kein zu zitierender Text. Setze sie
still um: Erwähne NICHT, dass eine Entscheidung getroffen wurde, und zähle die
verworfenen Varianten NICHT auf — weder als "frühere Fehlannahme" noch als
"in den Quellen auch als X transkribiert". Falsche Schreibweisen und
Transkriptionsfehler sind Artefakte der Spracherkennung; sie stehen in den
Aliases des Frontmatters und haben im Fließtext nichts verloren. Benutze
einfach durchgehend die festgelegte Schreibweise.

Eine sachliche Korrektur, die im Spiel selbst stattfand ("die Gruppe hielt ihn
lange für tot"), ist davon unberührt und darf erzählt werden.

AUSNAHME 2 — Abschnitte, die mit "DARSTELLUNG:" beginnen, sind Anweisungen zur
FORM des Eintrags (Länge, Vorsicht bei Unsicherem, Kennzeichnung als Gerücht
o. Ä.), kein Weltwissen. Befolge sie beim Schreiben, ohne sie zu erwähnen oder
zu zitieren — genau wie bei "ENTSCHEIDUNG:".
{sources}
"""

SYNTH_SECONDARY_TEMPLATE = """
Festlegungen zu ANDEREN Entitäten, die in den Belegen oben namentlich
vorkommen. Sie betreffen nicht diesen Eintrag selbst — übernimm daraus nur,
was für DIESEN Eintrag relevant ist: die richtige Schreibweise, Identität und
Fakten zur erwähnten Person oder Sache, wenn du sie hier nennst. Schreibe
KEINEN eigenen Abschnitt über die andere Entität, und führe den Punkt NICHT
unter "# Offene Konflikte" auf — selbst wenn ein Beleg oben ihm zu
widersprechen scheint.
{secondary}
"""

SYNTH_EXCERPTS_TEMPLATE = """
Transkript-Ausschnitte (Originaldialog rund um die Belegstellen). Nutze sie
für konkrete Details, Namen, Zahlen und Zitate. Sprecher in Klammern sind
reale Personen mit ihrer Rolle:
{excerpts}
"""
