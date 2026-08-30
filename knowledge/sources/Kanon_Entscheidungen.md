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
und wird einmal pro Session aktiviert. Er ist derselbe Gegenstand, der an
anderer Stelle als "Lindo Lauts Ring" beschrieben wird — kein zweiter Ring,
nur ein zweiter Titel dafür. Der Ring, den Dodo zerstört hat, ist ein
**anderer, nicht verwandter Ring** — er gehört nicht in diesen Eintrag. Führe
hier ausschließlich Lindos Ring.

### Ringe

ENTSCHEIDUNG: Sammeleintrag. Hier werden die verschiedenen kleineren Ringe der
Kampagne **nur stichwortartig** aufgelistet — jeweils ein bis zwei Sätze, was
der Ring ist und wo er auftauchte. Keine ausführlichen Einzelabschnitte, keine
Chronologie. Diese Ringe waren jeweils nur kurz relevant (etwa der von Dodo
zerstörte Ring, assoziiert mit Abisalis und lila Magie) und verdienen keinen
eigenen Eintrag. Lindos **Ring der Teleportation** gehört ausdrücklich NICHT
hierher, er hat einen eigenen Eintrag.

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

### Liam Velora

ENTSCHEIDUNG: Der korrekte Name lautet **Liam Velora** — Lunaras Bruder. Er
tritt auch als **Ulvanara**, junger Wächter Vorgul'tars, auf; das ist dieselbe
Person unter fremder Kontrolle, kein zweites Wesen.

ENTSCHEIDUNG: Vhar'Zuls Aussage, Liam existiere **nur noch als Seele**, ist
**falsch**. Ob aus Unwissenheit oder Absicht, ist unklar — stelle beides als
offene Möglichkeit dar, aber nicht die Behauptung selbst als Tatsache.

### Hendrik (Nomadenführer)

ENTSCHEIDUNG: **Zwei verschiedene Personen.** Dieser Eintrag betrifft
ausschließlich **Hendrik, den älteren Anführer der Bergnomaden** (Session
2025-08-12). Er hat nichts mit dem Bauern Hendrik Heinrich zu tun.

### Hendrik Heinrich (Bauer)

ENTSCHEIDUNG: Der **Bauer und Besitzer der Heinrich-Farm**, die den Silberkernen
als Unterschlupf dient (Session 2026-03-23). Er ist **nicht** identisch mit
Hendrik, dem Anführer der Bergnomaden — die Namensähnlichkeit ist Zufall.

### Jen (Schreiberin)

ENTSCHEIDUNG: **Zwei verschiedene Personen** tragen diesen Namen. Hier geht es
um die **menschliche Schreiberin**, die die Gruppe nahe der Kapelle antrifft
(Session 2026-06-10).

### Der Jen (Diener Vorgul'tars)

ENTSCHEIDUNG: Ein **mysteriöser Diener Vorgul'tars**, der aus eigenen Interessen
handelt (Session 2026-06-16). **Nicht** identisch mit der Schreiberin Jen.

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

### Thar'Vok, der Erdrichter

ENTSCHEIDUNG: **„Seras" / „Seraph" ist keine Gottheit.** Die Bergnomaden in
Session 2025-08-12 verehren **Thar'Vok, den Erdrichter**. Der Name im
Transkript („also wir sind hier für Seraph", „Da ist es Seras, Herr der
Flammen") ist ein Verhörer am Tisch bzw. ein Transkriptionsfehler und darf in
keinem Eintrag als Eigenname erscheinen. Belege über den Kult der Nomaden,
das Heiligtum am Berg und den Gruß „ein flammendes Herz" gehören in diesen
Eintrag.

ENTSCHEIDUNG: **„Parfon" ist ebenfalls keine Gottheit.** Der „ursprüngliche
Steingott", dem die Bergkapelle geweiht war, bevor Vhar'Zuls Kult sie
übernahm (Session 2025-09-02), ist **Thar'Vok**. Auch dieser Name ist ein
Transkriptionsfehler.

ENTSCHEIDUNG: Warum der Name nicht genannt werden darf: Thar'Vok ist ein
**alter Gott**, und die Verehrung alter Götter ist in der Zeit **nach dem
Götterkrieg verboten bzw. verpönt**. Die Panik der Dorfbewohner ist kulturell
und politisch begründet — keine übernatürliche Gefahr durch das Aussprechen
des Namens.

ENTSCHEIDUNG: Thar'Vok war ein **Kampfgefährte Vhar'Zuls** („keine Freunde,
aber Kampfgefährten in den letzten Tagen"). Diesen Hinweis gibt **Vhar'Zul
selbst** — als Stimme (Thyrex) in Lindo Lauts Amulett. Belege, die den
Kampfgefährten [Ezhura](../bundle/splitter_des_ewigen/deities/ezhura.md) („Ezua")
zuschreiben, verwechseln die sprechende Stimme mit dem Inhalt der Aussage und
sind ungültig.

### Vhar'Zul

ENTSCHEIDUNG: Vhar'Zul wurde nicht getötet, sondern **in fünf Seelen
zerspalten**. Das *Buch der vier Seelen* kennt nur vier — **Sythraal** (der
Schleier), **Ezhura** (die Glut), **Koll'Mereth** (die Krone) und **Thyrex**
(der Sänger). Das Buch ist an dieser Stelle **unvollständig**: es gibt einen
**versteckten fünften Teil, Slix**. Vier der fünf sind bösartig; **Thyrex ist
der einzige besonnene**.

ENTSCHEIDUNG: **Thar'Vok, der Erdrichter war ein Kampfgefährte Vhar'Zuls** —
siehe den Abschnitt zu Thar'Vok. Die Auskunft darüber gibt Vhar'Zul als Stimme
im Amulett Lindo Lauts (Session 2025-08-12).

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
**keine eigenständige Gottheit**. In Sessions als „Kol Meref" und als „Koll"
gehört — beide Schreibweisen meinen ihn. Die Belege vom oberen Schrein in der
Kapelle und die Gravur auf der linken Statue gehören zu diesem Eintrag; er ist
eine der Stimmen in Lindo Lauts Amulett.

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

### Huludan

ENTSCHEIDUNG: **Huludan ist ein Titan** — das uralte Wesen, das im *Splitter
des Ewigen* gefangen ist und das Vhar'Zul befreien wollte, um einen
Schöpferwunsch zu erwirken.

ENTSCHEIDUNG: Der Name **„Holodarn" existiert nicht**. Er ist durchgehend ein
Transkriptionsfehler und darf in keinem Eintrag als Eigenname auftauchen.

ENTSCHEIDUNG: Das Wesen, das in Session 2026-05-13 auftritt und „in Huludans
Namen den Segen ausspricht", ist **real, aber namenlos** — es wird als *Diener
Huludans* geführt. Es ist weder celestisch noch dämonisch und ist **nicht**
mit Huludan identisch. Belege, die es „Holodarn" nennen, meinen diesen Diener;
Belege aus Session 2026-06-16, die „Holodarn" den Urgott im Splitter nennen,
meinen Huludan selbst.

### Willauch

ENTSCHEIDUNG: Willauch liegt auf der aktuellen Karte im **Südwesten**. Belege,
die die Stadt als „Hauptstadt im Norden" oder „größte Stadt der nördlichen
Schneise" bezeichnen, sind falsch.

ENTSCHEIDUNG: Die kanonische Schreibweise ist **Willauch**. „Willau",
„Willoch" und „Vilauch" sind Transkriptionsvarianten.

### Belorus

ENTSCHEIDUNG: Belorus ist ein **schwarzer Paladin** — ausdrücklich **kein
Lich**. Belege, die ihn als Lich bezeichnen, sind falsch.

ENTSCHEIDUNG: Belorus ist **keine Gottheit**. Die Beschreibung als „Gottheit,
die mit Stille assoziiert ist" beruht auf seinem Beinamen *der Stille* und ist
ein Missverständnis; er ist ein mächtiger NPC, kein göttliches Wesen.

ENTSCHEIDUNG (GM/Noah 2026-08-30): Belorus' Untotenarmee wurde einmal separat
als „Untote Horde von Zebras" erfasst und dabei falsch verstanden: „Zebras"
ist hier wieder die Verhörung von **Zebros**, dem gefallenen Königreich — die
Horde besteht nicht aus untoten *Zebra-Tieren*, sondern zieht aus dem Gebiet
des früheren Königreichs Zebros ins Tal. Es ist **dieselbe** Armee wie oben,
kein zweites, eigenständiges Konzept.

### Hans

ENTSCHEIDUNG: Es gibt **zwei verschiedene Personen namens Hans**. Der Soldat
aus Breska, der Belorus' versiegelte Botschaft überbringt (Session 2026-01-13),
und der Tiefling-Wirt der Taverne *Zum grünen Sichelmond* (Session 2026-03-18)
haben nichts miteinander zu tun. Sie werden getrennt geführt.

### Adeliga

ENTSCHEIDUNG: Es gibt **zwei verschiedene Frauen namens Adeliga**. Die eine ist
die Besitzerin des *Haus des Löwen* in **Willauch** — eine menschliche
Geschäftsfrau, elegant und kühl, ohne übernatürliche Merkmale (Session
2026-03-03). Die andere ist ein **Eulen-Seraph** und Paladin des neuen Gottes
*Joran der Münzenzähler*, der der Gruppe im **Ringtal** begegnet (Session
2026-06-04). Sie haben nichts miteinander zu tun; der scheinbare Widerspruch
zwischen „Geschäftsfrau" und „himmlisches Wesen" ist keiner.

### Breska

ENTSCHEIDUNG: Die kanonische Schreibweise des Dorfes ist **Breska**.
„Brechka", „Bresca", „Breschka" und „Reska" sind Transkriptionsvarianten.

### Silberkerne

ENTSCHEIDUNG: Die Silberkerne sind **eine Organisation mit mehreren Lagern**,
nicht mehrere gleichnamige Banden. **Harl und Sarina führen das Ganze**;
**Floran** führt lediglich die Zelle auf der **Heinrich-Farm**. Belege, die
Floran als Anführer der Silberkerne bezeichnen, meinen diese eine Zelle.

ENTSCHEIDUNG: Anlass der Verfolgung ist der **Mord an einem Diplomaten**. Der
Beleg, der stattdessen vom Tod einer Prinzessin spricht, ist eine Verwechslung.

ENTSCHEIDUNG: Es gibt **kein drittes Führungsmitglied und kein „Monster"**. Die
Stelle geht auf eine einzige Aussage einer Figur zurück, die ausdrücklich sagt,
sie habe die Anführer *nie gesehen*: „Soll wohl irgendein Monster sein, ein
krasser Mann und eine sehr, sehr starke Frau." Das ist **Hörensagen über
dieselben zwei Personen** — der „krasse Mann" ist Harl, die „sehr starke Frau"
ist Sarina. „Monster" ist eine Beschreibung, kein Name und keine dritte Figur.

### Hal / Harl

ENTSCHEIDUNG: **Hal (auch Harl) hat beide Rollen** — der Widerspruch
„Stellvertreter" gegen „Anführer" ist keiner. Die **Banditenfestung ist ein
Lager der Silberkerne**; er ist dort stellvertretender Anführer und zugleich
Anführer der Silberkerne. Beide Belege gelten.

### Goblin-Götter

ENTSCHEIDUNG: Die Goblin-Götter sind **chaotisch und wechselhaft**, nicht
bösartig. Der Beleg aus Session 2025-04-15, der sie als „bösartige
Göttergruppe" bezeichnet, ist eine Fehleinschätzung.

### Schwarzer Palantir

ENTSCHEIDUNG: Beide Fundortangaben stimmen und widersprechen sich nicht: Der
Palantir lag im **Labor der Hag**, und dieses Labor liegt **im Sumpf-Dungeon**.

### Verhandlung mit Harl

ENTSCHEIDUNG: Es gab **eine einzige Verhandlung**, keine Vorverhandlung. Der
Preis ist derselbe: **eine Truhe Gold = 10 Säcke Gold**. Es war eine
**Gruppenverhandlung** der Rotunas-Freunde, bei der **Lindo Laut die Gruppe
vertrat** — deshalb erscheint er in einem Beleg als alleiniger Verhandler.

### Der Schinder

ENTSCHEIDUNG: Das Geschlecht des Schinders ist für den Kanon **unerheblich**;
im Zweifel männlich. Kein offener Konflikt.

### Tyrael

ENTSCHEIDUNG: Das Wesen, über das Tyrael konkretes Wissen besitzt, ist
**Vhar'Zul**. „Basul" und „Vasul" sind zwei Transkriptionen desselben Namens;
es besteht kein Widerspruch. Tyrael kennt Vhar'Zul als bekannten Gott und gibt
einige Informationen über ihn preis.

### Nyrella

ENTSCHEIDUNG: Nyrellas Eisbär heißt **Nyruk**. „Nairuk", „Nairook", „Nayruk"
und „Naeruk" sind Transkriptionsvarianten desselben Namens — kein Widerspruch.

ENTSCHEIDUNG: Wer in Session 5 im Moment vor dem Knall gesprochen hat, ist
**bewusst nicht festgelegt** und für den Kanon nicht relevant. Dieser Punkt ist
**nicht** als offener Konflikt zu führen.

### Dodos heiliger Streitkolben

ENTSCHEIDUNG: Dodo führt **eine** heilige Waffe. „Streitkolben", „Dodos
leuchtender Streitkolben", „Heiliger Streitkolben Dodos", „Der heilige
Streitkolben aus Zebras" und „Streitkolben von Zebras" bezeichnen alle
dieselbe. Nicht zu verwechseln mit dem *Morgenstern des Heiligen Duran*, der
Ritter Brandon gehört.

ENTSCHEIDUNG (überholt, siehe Korrektur 2026-08-29 direkt darunter): Die drei
Herkunftsangaben widersprechen sich nicht: Dodo zog die Waffe in der Festung
Zebras aus einem Spiegel, und sie stammt ursprünglich von Cepros. Das sind
drei Teile einer Geschichte.

KORREKTUR (GM/Noah 2026-08-29): **„Cepros" ist keine dritte, eigenständige
Herkunft** — es ist dieselbe Verhörung wie „Zebras" für **Zebros**, das
gefallene Königreich. Die Waffe heißt **Zebros Zorn**, wurde **in der Festung
Zebros aus einem Spiegel gezogen** und stammt **ursprünglich aus dem
Königreich Zebros** — eine einzige Herkunft, nicht drei. Jede weitere
Erwähnung von „Cepros" im Bundle bezeichnet ebenfalls Zebros.

### Die Hags

ENTSCHEIDUNG: **Lenra** ist *die Hag* der Kampagne. „Die Hack", „Heck",
„Lanra", „Leandra", „Moorhexe" und **„die Sumpfhexe"** bezeichnen alle sie.

ENTSCHEIDUNG: **Ausnahme** — im **Abisalis** (= der *Splitterwelt*) existiert
eine **zweite Hag**, die **nicht** Lenra ist: die **Kräuterhexe der Anhänger
Uhoriaks'**, persönliche Alchemistin von **Lady Kalen**, der Sprecherin
Uhoriaks' und Herrin von Boragdil. Sie darf nie mit Lenra vermengt werden.

### Abisalis

ENTSCHEIDUNG: **Abisalis ist die Splitterwelt** — dieselbe Domäne, zwei Namen.
„Abyssalis" und „Abyssares" sind Transkriptionsvarianten.

### Benennung von Orten

ENTSCHEIDUNG: Ein Gebäude oder Gelände innerhalb einer Stadt bekommt einen
**eigenen Eintrag** — der Graph soll die Beziehung zwischen Ort und Stadt als
Kante zeigen, nicht durch Verschmelzen verlieren.

ENTSCHEIDUNG: Die **Stadt steht im Namen immer am Schluss**: *Arena von
Willauch*, *Kapelle von Ehrenfels*, *Gruft von Breska*. Nicht „Kapelle in
Ehrenfels" und nicht mit der Stadt am Anfang.

ENTSCHEIDUNG: **Räume innerhalb eines Dungeons bekommen keinen eigenen
Eintrag** — anders als Gebäude in einer Stadt. Ein Dungeon wird an einem Abend
durchquert, seine Räume haben außerhalb davon kein Eigenleben; sie werden im
Eintrag des Dungeons beschrieben.

ENTSCHEIDUNG: **Lager, die die Gruppe für eine Nacht aufschlägt, werden nicht
geführt.** Ein Lager bekommt nur dann einen Eintrag, wenn es dauerhaft und
identifizierbar ist — das *Banditenlager der Silberkerne*, das *Berglager der
Hendriks-Sippe*, die Flüchtlingslager.

### Was ein Gegenstand ist

ENTSCHEIDUNG: Nur **besondere** Gegenstände werden als eigener Eintrag geführt
— magische, heilige oder handlungstragende Artefakte. **Gewöhnliche
Ausrüstung** wird nicht getrackt: normale Schwerter und Rüstungen,
Verbrauchsgüter wie Heiltränke und Gegengifte, Geld und Goldfunde. Ein Eintrag,
dem ein Leser nicht folgen würde, gehört nicht in die Wissensbasis.

### Was eine Fraktion ist

ENTSCHEIDUNG: Eine **Fraktion** ist eine Macht, die **über eine Stadt und über
eine Session hinaus** wirkt — die Gilden, die Silberkerne, Belorus'
Untotenarmee, die Kulte der Götter, die Zwerge der Festung, die Goblins. Eine
Handvoll Magier, die Bewohner eines Dorfes oder ein Gnoll-Rudel aus einer
Session sind **keine** Fraktion, sondern ein **kollektiver Charakter** und
werden als NPC geführt.

ENTSCHEIDUNG: Zwei Ausnahmen gelten wegen **narrativer Bedeutung**, nicht wegen
Macht: die **Flüchtlinge aus Breska** und die **Gefährten von Rotunas** (die
Heldengruppe selbst) bleiben Fraktionen.

ENTSCHEIDUNG: Eine Person und die nach ihr benannte Gruppe sind **zwei
Einträge**, nicht einer. **Voras** bleibt ein NPC, und seine **Sippe** ist eine
eigene Fraktion, weil sie einflussreich genug war. Nur **unbenannte** oder
**einmalig erwähnte** Kollektive werden in die Fraktion hineingezogen, zu der
sie gehören — sie bekommen keinen eigenen Knoten.

ENTSCHEIDUNG: „Dwarfmasters" ist der **Twitch-Account**, nicht der Name der
Gilde. Die Gilde der Gruppe ist die **Gilde von Ehrenfels**.

### Ezhura

ENTSCHEIDUNG: „Glut" und „Ezua" bezeichnen **dieselbe Entität**: **Ezhura**, im
*Buch der vier Seelen* „die Glut" genannt — eine der Seelen Vhar'Zuls und eine
der Stimmen in Lindo Lauts Amulett. Ihre Statue steht ganz rechts im Schrein.

ENTSCHEIDUNG: **Ezhuras Seelenstück wurde nicht ausgelöscht.** Belege, die das
behaupten, verwechseln sie mit **Koll'Mereth**. Ezhura spricht später weiterhin
aus dem Amulett; der Widerspruch beruht auf dieser Verwechslung.

### Koll'Mereth: Auslöschung

ENTSCHEIDUNG: Das Seelenstück, das **Nerash ausgelöscht** hat, ist das von
**Koll'Mereth**, nicht das von Ezhura. Seitdem sind von den vier im Amulett
bekannten Seelen nur noch drei übrig.

### Blutschalen-Statuen

HINWEIS ZUR DARSTELLUNG: Die namenlose „böse Gottheit" der Statue mit der
Blutschale ist **nicht sicher zuzuordnen** — wahrscheinlich Vhar'Zul, aber
**jede Blutschalen-Statue kann einem anderen Gott gehören**. Eine Statue mit
Blutschale ist also *kein* Erkennungsmerkmal für eine bestimmte Gottheit.
Entsprechend vorsichtig formulieren und keine Zuordnung als gesichert
darstellen.

### Zebros

ENTSCHEIDUNG: **Zebros ist keine Gottheit.** Der Name bezeichnet ein **altes
Königreich**, das im **Götterkrieg zerstört** wurde. Die **Hauptstadt** des
Königreichs trug ebenfalls den Namen Zebros, ebenso ein **Berg** (der **Berg
Zebros**). Vom Königreich sind heute nur noch **Ruinen und Relikte** erhalten;
der Berg Zebros dagegen **steht weiterhin**. Der Beleg, der Zebros anhand der
Inschrift in der Silbergruft als „ehemaligen Eigentümer" und Erdgott führt,
verwechselt eine Nennung des Reichsnamens mit einer Gottheit — dort ist
vermutlich ein Relikt oder eine Ruine aus der Zeit des Königreichs gemeint,
nicht ein Gott. Führe den Eintrag als **Ort/ehemaliges Königreich**, nicht als
Deity.

HINWEIS ZUR DARSTELLUNG: Hauptstadt und Berg sind bislang nur durch diese eine
Nennung belegt und bekommen deshalb vorerst **keine eigenen Einträge** —
beschreibe beide knapp innerhalb dieses Eintrags. Ein eigener Eintrag ist erst
gerechtfertigt, sobald weitere Sessions sie unabhängig voneinander behandeln
(vgl. „Benennung von Orten").

### Gott und Erscheinung

ENTSCHEIDUNG: Tritt ein Gott körperlich auf, bleibt das **ein Knoten vom Typ
Deity**. Die Erscheinung ist ein Ereignis, das auf den Gott verweist, kein
zweiter Eintrag. Betrifft [Nerash](../bundle/splitter_des_ewigen/deities/nerash.md),
Kol Meref und die Kultisten des Varsurs.

Nicht betroffen: eine Organisation und ihr Sitz bleiben **getrennt**, auch bei
gleichem Namen. Die *Seelenwacht* ist sowohl ein Orden als auch eine Stadt —
das sind zwei Dinge mit einer echten Beziehung zwischen ihnen, keine Dublette.

### Hartwacht

ENTSCHEIDUNG: Hartwacht ist eine **Stadt**, keine uneinnehmbare Orkfestung.
Der Beleg aus Session 2026-03-18 (00:45:15), der sie als "uneinnehmbare
Orkfestung" bezeichnet, ist ungültig — er beruht auf einer Fehldarstellung am
Tisch. Gültig bleibt die Beschreibung aus Session 2025-10-07 (00:09:39): eine
Stadt, die die Magier vor dem Golem schützen wollten. Die Lage hinter einem von
Vargen bewohnten Pass und das Reiseziel der Gruppe bleiben davon unberührt —
nur die Einordnung als Festung entfällt. Führe diesen Punkt nicht als offenen
Konflikt auf.

---

<!-- Vorlage - kopieren und ausfüllen:

### <Entitätsname>

ENTSCHEIDUNG: <Was gilt.> Frühere Belege, die <X> behaupten, beruhen auf
<Transkriptionsfehler / Missverständnis am Tisch / Retcon> und sind ungültig.

-->
