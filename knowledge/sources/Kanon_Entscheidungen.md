# Kanon-Entscheidungen der Spielleitung

Verbindliche Festlegungen zu widersprüchlichen Belegen aus den Sessions.

**Wie das funktioniert**

* Eine Überschrift `### <Name der Entität>` verbindet den Abschnitt mit dem
  Eintrag im Bundle. Der Name muss zum `canonical_name` oder einem Alias in
  `entity_registry.yaml` passen (Zeichensetzung ist egal — "Vhar'Zul" trifft
  auch "Vhar Zul").
* Jede Festlegung beginnt mit `ENTSCHEIDUNG:`. Nur dann hat sie Vorrang vor
  widersprechenden Session-Belegen und der Punkt verschwindet aus
  "# Offene Konflikte".
* Danach `pnp run` ausführen. Es wird **nur** die betroffene Entität neu
  geschrieben — der Cache-Schlüssel enthält die zugehörigen Quellen, alle
  anderen Einträge bleiben Cache-Treffer.
* Zum Schluss die erledigte Datei aus `knowledge/conflicts/` löschen.

Diese Datei liegt bewusst in `sources/` und nicht im Bundle: das Bundle ist
generierte Ausgabe und wird bei jedem Lauf überschrieben. Was hier steht,
überlebt jede Regeneration.

---

### Dodo

ENTSCHEIDUNG: Dodos Waffenwechsel ist **kein Widerspruch, sondern Chronologie**.
Er führte zunächst ein Breitschwert, kaufte auf Tier 2 einen Streitkolben und
nutzt seither Streitkolben. In der Seelenwacht-Session erhielt die Gruppe einen
neuen Kolben, **"Zebros Zorn"**, eine heilige Waffe — seine aktuelle Hauptwaffe.
Stelle diese Abfolge als Entwicklung dar, nicht als offenen Konflikt.

ENTSCHEIDUNG: Dass Dodo "seine blaue Haut vermisst", ist **kein Hinweis auf
seine Spezies oder eine Verwandlung**. Ursache war ein Domänen-Effekt der
Götter, durch den kurzzeitig alles schwarz-weiß erschien und nur Rot als Farbe
wahrnehmbar blieb. Er vermisste also die Farbe, nicht die Haut. Führe diesen
Punkt nicht als Spezies-Widerspruch auf.

### Esterossa

ENTSCHEIDUNG: Esterossa ist ein **Seraph der Unterklasse "Winged Sentinel"** und
**männlich**. Verwende durchgängig männliche Pronomen ("er/ihn/sein").

ENTSCHEIDUNG: Esterossa betet seit jeher und ausschließlich den **neuen Gott
Korn** an, der auch als **Blutgott** bezeichnet wird — beide Namen meinen
dieselbe Gottheit. Korn zählt zu den *neuen* Göttern, nicht zu den alten.

### Korn

ENTSCHEIDUNG: Korn ist ein **neuer Gott** und identisch mit dem "Blutgott".
Sein einziger namentlich bekannter Anhänger in der Gruppe ist Esterossa
(männlich), der ihm im Kampf Opfer darbringt.

### Nyrella

ENTSCHEIDUNG: Nyrella ist nach dem Daggerheart-Regelwerk eine **Faery**, also
eher eine Pixie als eine Elfe — allerdings nicht so klein wie eine gewöhnliche
Pixie. Bezeichne sie nicht als Elfe.

### Silberkerne

ENTSCHEIDUNG: Die Silberkerne werden von **zwei** Personen gemeinsam angeführt:
**Harl** und **Sarina**. Beide stehen an der Spitze.

HINWEIS ZUR DARSTELLUNG: Über die Silberkerne ist bewusst noch nicht alles
bekannt. Beschreibe nur den aktuellen Kenntnisstand und **kennzeichne alles
Unsichere ausdrücklich als Vermutung** (z. B. "vermutlich", "den Belegen
zufolge", "bislang unbestätigt"). Ein lückenhafter Eintrag ist hier korrekt;
fülle Lücken nicht mit Spekulation, die wie Tatsache klingt.

### Ring der Teleportation

ENTSCHEIDUNG: Der Ring der Teleportation ist ein Gegenstand **von Lindo Laut**
und wird einmal pro Session aktiviert. Der Ring, den Dodo zerstört hat, ist ein
**anderer, nicht verwandter Ring** — er gehört nicht in diesen Eintrag. Führe
hier ausschließlich Lindos Ring.

### Ringe

ENTSCHEIDUNG: Sammeleintrag. Hier werden die verschiedenen kleineren Ringe der
Kampagne **nur stichwortartig** aufgelistet — jeweils ein bis zwei Sätze, was
der Ring ist und wo er auftauchte. Keine ausführlichen Einzelabschnitte, keine
Chronologie. Diese Ringe waren jeweils nur kurz relevant (etwa der von Dodo
zerstörte Ring) und verdienen keinen eigenen Eintrag. Lindos **Ring der
Teleportation** gehört ausdrücklich NICHT hierher, er hat einen eigenen Eintrag.

### Schriftrollen

ENTSCHEIDUNG: Sammeleintrag. Liste die verschiedenen unbedeutenden
Schriftrollen **nur stichwortartig** auf (je ein bis zwei Sätze). Dazu zählt
unter anderem die Schriftrolle vom Anfang aus Session 1. Die **Schriftrolle von
Nerash** (Ritual gegen Vasul) und die **Schriftrolle von Belorus** sind
handlungsrelevant und haben eigene Einträge — sie gehören nicht hierher.

### Casa del Cookie

ENTSCHEIDUNG: Die Casa del Cookie liegt **nordwestlich von Willauch**.

ENTSCHEIDUNG: Die widersprüchlich wirkenden Beschreibungen des Ortes sind
**alle korrekt**. Sessionzeit entspricht Echtzeit, und das Dorf hat sich in
dieser Zeit stark verwandelt — vermutlich durch die dunkle Magie der Hag.
Stelle die Veränderung als Entwicklung über die Zeit dar, nicht als
Widerspruch.

### Ehrenfels

ENTSCHEIDUNG: **Nox lebt.** Sein Tod ist lediglich ein Gerücht. Im Eintrag darf
er als „Gerüchten zufolge tot oder verschwunden" geführt werden — aber nicht
als Tatsache.

HINWEIS ZUR DARSTELLUNG: Das Wiki soll nur so viel wissen wie die Zuschauer.
Kennzeichne Unbestätigtes ausdrücklich als Gerücht und nimm Wissen, das nur am
Spieltisch bekannt ist, nicht vorweg.

### Die Prinzessin

ENTSCHEIDUNG: Die Prinzessin **lebt**. Gerüchten zufolge ist sie tot, ihr
Aufenthaltsort ist unbekannt. Führe den Tod ausdrücklich als Gerücht, nicht als
Tatsache.

### Lenra

ENTSCHEIDUNG: Lenra **wirkte tatsächlich durch die Statue**. Die Helden
erinnern sich nicht falsch.

HINWEIS ZUR DARSTELLUNG: Das ist allerdings sehr spezifisches Wissen vom
Spieltisch. Halte es im Eintrag knapp und beiläufig; das Wiki soll nicht mehr
wissen, als den Zuschauern zugänglich ist.

### Nyruk

ENTSCHEIDUNG: Der korrekte Name lautet **Nyruk**, nicht „Nairuk" — die übrigen
Schreibweisen sind Transkriptionsfehler.

ENTSCHEIDUNG: Nyruk ist ein **großer Eisbär ohne Flugfähigkeit**. Er konnte
**nie** fliegen. Belege, die ihm Fliegen zuschreiben, sind falsch; übernimm sie
nicht.

### Nox

ENTSCHEIDUNG: Nox ist **männlich**. Weibliche Formen in den Belegen sind
Transkriptionsfehler. Verwende durchgängig männliche Pronomen.

### Perry das Schnabeltier

ENTSCHEIDUNG: Dass Perry „nicht kampftauglich" sei, beschreibt einen
**vorübergehenden Zustand**, keine dauerhafte Eigenschaft. Stelle es als
zeitweiligen Effekt dar, nicht als Wesensmerkmal.

### Akastrale

ENTSCHEIDUNG: Akastrale ist eine **weibliche alte Gottheit**. Verwende
durchgängig weibliche Formen („sie/ihr").

HINWEIS ZUR DARSTELLUNG: Zu Akastrale muss vorerst **kein umfangreicher
Eintrag** entstehen. Ein knapper Entwurf des aktuellen Kenntnisstandes genügt;
kennzeichne ihn als vorläufig und fülle Lücken nicht mit Spekulation.

### Rotunas

ENTSCHEIDUNG: Rotunas hat im Daggerheart-Regelwerk die Klasse **Giant** und ist
damit ein **Riese** — **kein Elf**. Belege, die ihn als Elf bezeichnen, sind
falsch.

### Cornivum

ENTSCHEIDUNG: Die widersprüchlich wirkenden Beschreibungen Cornivums sind
**alle korrekt** und beschreiben verschiedene Zeitpunkte. Zwischen der ersten
und der letzten Session des Prologs ist **über ein Jahr** vergangen; das
abgeschiedene Dorf ist in dieser Zeit stetig gewachsen. Stelle die Entwicklung
als Chronologie dar, nicht als Widerspruch.

ENTSCHEIDUNG: Ursache des Wachstums ist die **dunkle Magie der Hag
[Lenra](../bundle/splitter_des_ewigen/npcs/lenra.md)** (auch „Landra"). Sie
nutzte das abgelegene Dorf, um dort eine **Armee aus Gnollen, Waldschraten und
Untoten zu züchten**.

### Harald (Freibeuter)

ENTSCHEIDUNG: Es gibt **zwei verschiedene Haralds**. Dieser Eintrag betrifft
ausschließlich den **Freibeuter-Kapitän Harald**, der eine heruntergekommene
Taverne betreibt und sich mit einem Rapier verteidigt — die **wichtigere** der
beiden Figuren. Der Dämon Harald aus Abyssalis hat einen eigenen Eintrag und
gehört nicht hierher.

### Harald (Dämon)

ENTSCHEIDUNG: Ein **Magier-Dämon in Abyssalis**, der mit einem Seelenstein
auftritt. Er ist **nicht** identisch mit dem Freibeuter-Kapitän Harald und
trägt den Namen nur zufällig gleich. Eine Nebenfigur.

### Stiller Gott

HINWEIS ZUR DARSTELLUNG: Wie bei Akastrale — vorerst nur ein knapper Entwurf
des aktuellen Wissensstandes, ausdrücklich als vorläufig gekennzeichnet.

### Vhar'Zul

ENTSCHEIDUNG: Vhar'Zul wurde nicht getötet, sondern **in fünf Seelen
zerspalten**. Das *Buch der vier Seelen* kennt nur vier — **Sythraal** (der
Schleier), **Ezhura** (die Glut), **Koll'Mereth** (die Krone) und **Thyrex**
(der Sänger). Das Buch ist an dieser Stelle **unvollständig**: es gibt einen
**versteckten fünften Teil, Slix**. Vier der fünf sind bösartig; **Thyrex ist
der einzige besonnene**.

ENTSCHEIDUNG: Behandle die Angabe „vier Seelen" im Buch nicht als Widerspruch
zu Belegen, die von fünf Teilen sprechen — das Buch weiß von Slix schlicht
nichts.

ENTSCHEIDUNG: Lindo Laut freundete sich mit Thyrex an, der als Stimme in seinem
Amulett saß. Gemeinsam löschten die beiden die übrigen Seelen aus. Vhar'Zul
kehrte dadurch **als vollwertige Gottheit** zurück — **nicht** als Ansammlung
zerschlagener Einzelteile — und trägt seither die **dominierende
Persönlichkeit von Thyrex**. Belege, die von drei oder vier verbliebenen
Stimmen sprechen, beschreiben Zwischenstände dieses Vorgangs und sind kein
Widerspruch.

### Thyrex

ENTSCHEIDUNG: Thyrex, „der Sänger", ist **eine der vier Seelen Vhar'Zuls**,
kein eigenständiges Wesen. In den Transkripten erscheint er als „Tyrex" oder
„T-Rex" — maßgeblich ist die Schreibweise **Thyrex**. Er sprach aus Lindo Lauts
Amulett, verbündete sich mit ihm gegen die drei bösartigen Seelen und ist
seither die vorherrschende Persönlichkeit des wiedererstarkten Vhar'Zul.

HINWEIS: Der Widerspruch „einmal absorbiert, einmal eigenständig in Abyssalis
handelnd" ist damit **aufgelöst** — beides trifft zu, nur zu verschiedenen
Zeitpunkten. Stelle es als Abfolge dar.

### Sythraal

ENTSCHEIDUNG: Sythraal, „der Schleier", ist eine der vier Seelen Vhar'Zuls.
In Sessions als „Sintra" gehört.

### Ezhura

ENTSCHEIDUNG: Ezhura, „die Glut", ist eine der vier Seelen Vhar'Zuls.
In Sessions als „Esua", „Esoa" oder „Ezreal" gehört.

### Koll'Mereth

ENTSCHEIDUNG: Koll'Mereth, „die Krone", ist eine der Seelen Vhar'Zuls und
**keine eigenständige Gottheit**. In Sessions als „Kol Meref" gehört.

### Slix

ENTSCHEIDUNG: Slix ist der **versteckte fünfte Teil Vhar'Zuls** — im *Buch der
vier Seelen* nicht verzeichnet, weshalb dort nur von vier Seelen die Rede ist.
Er gehört zu den vier bösartigen Anteilen. Beschreibe ihn in diesem Verhältnis
und verweise auf den Eintrag zu Vhar'Zul.

### Voras der Heilige

ENTSCHEIDUNG: Mit **„der Graf"** ist stets **Voras der Heilige** gemeint. Belege
über den Grafen gehören in diesen Eintrag.

### Die Prinzessin

### Dormak

ENTSCHEIDUNG: Dormak ist ein **Komplize der Hag** ([Lenra](../bundle/splitter_des_ewigen/npcs/lenra.md)).
Beide wollten Vhar'Zul zurückholen — allerdings dessen **ursprünglichen Teil**,
nicht die besonnene Persönlichkeit. Da der wiedererstarkte Vhar'Zul die Gestalt
von Tyrex angenommen hat und diese Persönlichkeit ein **Feind Dormaks** ist,
wurde Dormak am Ende von Vhar'Zul selbst ausgelöscht.

---

<!-- Vorlage - kopieren und ausfüllen:

### <Entitätsname>

ENTSCHEIDUNG: <Was gilt.> Frühere Belege, die <X> behaupten, beruhen auf
<Transkriptionsfehler / Missverständnis am Tisch / Retcon> und sind ungültig.

-->
