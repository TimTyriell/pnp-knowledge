# Erzähltexte (kein KB-Input)

Ausgeschriebene Kampagnen-Prosa. Liegt bewusst **nicht** in `../sources/` und
wird von der Pipeline nicht gelesen.

Warum nicht: es ist abgeleiteter Text, keine Quelle. Die Kapitel schmücken das
Spielgeschehen aus (erfundene Sinnesdetails, Dialog, innere Monologe), zu denen
es keine zitierbare Session-Fundstelle gibt — die Synthese hätte sie aber als
kanonisches Hintergrundwissen behandelt und als Tatsache in die Einträge
geschrieben, ohne Beleg. Dazu kommt: `Der_Splitter_des_Ewigen.md` und
`Der_Splitter_des_Ewigen_Buch1.md` erzählen die Kapitel 1–4 doppelt und
abweichend. Beide Fassungen landeten gemeinsam im selben Prompt — `locations/breska`
zog 13 028 Zeichen, also 65 % des gesamten Quellen-Budgets, für zwei
widersprüchliche Versionen derselben Szene.

Wenn ein Detail von hier in die Wissensbasis soll: als `ENTSCHEIDUNG:` in
`../sources/Kanon_Entscheidungen.md` festlegen, mit `<!-- okf: entity=... -->`.
Dann ist es eine Festlegung der Spielleitung statt unbelegter Erzähltext.

Das PDF war nie eingelesen — `load_sources` liest nur `*.md`.
