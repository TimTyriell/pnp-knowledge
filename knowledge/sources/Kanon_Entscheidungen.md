# Kanon-Entscheidungen der Spielleitung

Verbindliche Festlegungen zu widersprüchlichen Belegen aus den Sessions.

**Wie das funktioniert**

* Eine Überschrift `### <Name der Entität>` beschriftet den Abschnitt für
  Menschen. Die eigentliche Bindung an einen Bundle-Eintrag macht die Zeile
  direkt darunter: `<!-- okf: entity=<concept_id> -->`, mit dem `concept_id`
  aus `entity_registry.yaml` (mehrere, kommagetrennt, wenn eine Festlegung
  mehrere Einträge betrifft). Diese Zeile wird beim Laden entfernt und
  erscheint nie in einem Prompt. Fehlt sie, greift zur Rückwärtskompatibilität
  die alte Namens-Suche (Überschrift passt auf `canonical_name` oder einen
  Alias) — für neue Abschnitte immer die Direktive setzen.
* Optional `<!-- okf: entity=…; mentions=off -->` — verhindert, dass die
  Festlegung zusätzlich in Einträge einsickert, die die Entität nur beiläufig
  erwähnen (siehe nächster Punkt). Nur nötig, wenn das für diese eine
  Festlegung ausdrücklich falsch wäre.
* Jede Festlegung beginnt mit einem von zwei Schlüsselwörtern:
  - `ENTSCHEIDUNG:` — ein Weltfakt, der Vorrang vor widersprechenden
    Session-Belegen hat und den Punkt aus "# Offene Konflikte" nimmt.
  - `DARSTELLUNG:` — keine Tatsachenfestlegung, sondern eine Anweisung zur
    Form des Eintrags (Länge, Vorsicht bei Unsicherem, Kennzeichnung als
    Gerücht). Beide werden von der Synthese als Anweisung an sie selbst
    behandelt, nie als zu zitierender Text.
  Jede Festlegung reicht automatisch auch an Einträge weiter, die die
  betroffene Entität nur namentlich erwähnen (nicht nur an ihren eigenen) —
  dort zählt sie für Schreibweise, Identität und Fakten, aber nicht als
  eigener Abschnitt und nicht als offener Konflikt.
* Danach `pnp run` ausführen. Der Cache-Schlüssel der Synthese enthält den
  Hash der zugehörigen Quellen (Haupt- **und** Nebenanhang), daher werden nur
  die betroffenen Einträge neu geschrieben.
* Gelöste Konfliktdateien unter `knowledge/conflicts/` müssen nicht von Hand
  gelöscht werden — `pnp run` räumt sie ab, sobald der Widerspruch nicht mehr
  auftritt.

Kampagnenweite Regeln, die für jeden Eintrag gelten (Ortsbenennung, was einen
eigenen Gegenstands-Eintrag rechtfertigt, was eine Fraktion ist, Gott vs.
Erscheinung), stehen nicht mehr hier — sie trafen nie eine Überschrift und
erreichten so nie eine Entität. Sie stehen jetzt in `SYNTH_SYSTEM`
(`prompts.py`), wo sie jeden Eintrag zu null Zusatzkosten pro Entität
erreichen.

Diese Datei liegt bewusst in `sources/` und nicht im Bundle: das Bundle ist
generierte Ausgabe und wird bei jedem Lauf überschrieben. Was hier steht,
überlebt jede Regeneration.

---

### Dodo
<!-- okf: entity=characters/dodo -->

ENTSCHEIDUNG: Dodos Waffenwechsel ist **kein Widerspruch, sondern Chronologie**.
Er führte zunächst ein Breitschwert, kaufte auf Tier 2 einen Streitkolben und
nutzt seither Streitkolben. In der Seelenwacht-Session erhielt die Gruppe einen
neuen Kolben, **"Zebros Zorn"**, eine heilige Waffe — seine aktuelle Hauptwaffe.
Stelle diese Abfolge als Entwicklung dar, nicht als offenen Konflikt.

ENTSCHEIDUNG: Dodo vermisste die *Farbe* Blau, nicht blaue Haut — Ursache war
ein Domänen-Effekt der Götter (alles schwarz-weiß außer Rot). Seine Spezies
ist davon unberührt.

### Esterossa
<!-- okf: entity=characters/esterossa -->

ENTSCHEIDUNG: Esterossa ist ein **Seraph der Unterklasse "Winged Sentinel"** und
**männlich**. Verwende durchgängig männliche Pronomen ("er/ihn/sein").

ENTSCHEIDUNG: Esterossa betet seit jeher und ausschließlich den **neuen Gott
Korn** an, der auch als **Blutgott** bezeichnet wird — beide Namen meinen
dieselbe Gottheit. Korn zählt zu den *neuen* Göttern, nicht zu den alten.

### Korn
<!-- okf: entity=deities/korn -->

ENTSCHEIDUNG: Korn ist ein **neuer Gott** und identisch mit dem "Blutgott".
Sein einziger namentlich bekannter Anhänger in der Gruppe ist Esterossa
(männlich), der ihm im Kampf Opfer darbringt.

### Nyrella
<!-- okf: entity=characters/nyrella -->

ENTSCHEIDUNG: Nyrella ist nach dem Daggerheart-Regelwerk eine **Faery**, also
eher eine Pixie als eine Elfe — allerdings nicht so klein wie eine gewöhnliche
Pixie. Bezeichne sie nicht als Elfe.

ENTSCHEIDUNG: Nyrellas Eisbär heißt **Nyruk**. „Nairuk", „Nairook", „Nayruk"
und „Naeruk" sind Transkriptionsvarianten desselben Namens — kein Widerspruch.

ENTSCHEIDUNG: Wer in Session 5 im Moment vor dem Knall gesprochen hat, ist
**bewusst nicht festgelegt** und für den Kanon nicht relevant. Dieser Punkt ist
**nicht** als offener Konflikt zu führen.

### Silberkerne
<!-- okf: entity=factions/silberkerne -->

ENTSCHEIDUNG: Die Silberkerne sind **eine Organisation mit mehreren Lagern**,
nicht mehrere gleichnamige Banden, angeführt von **Harl und Sarina** gemeinsam.
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

DARSTELLUNG: Über die Silberkerne ist bewusst noch nicht alles bekannt.
Beschreibe nur den aktuellen Kenntnisstand und **kennzeichne alles Unsichere
ausdrücklich als Vermutung** (z. B. "vermutlich", "den Belegen zufolge",
"bislang unbestätigt"). Ein lückenhafter Eintrag ist hier korrekt; fülle
Lücken nicht mit Spekulation, die wie Tatsache klingt.

### Ring der Teleportation
<!-- okf: entity=items/ring_der_teleportation -->

ENTSCHEIDUNG: Der Ring der Teleportation ist ein Gegenstand **von Lindo Laut**
und wird einmal pro Session aktiviert. Er ist derselbe Gegenstand, der an
anderer Stelle als "Lindo Lauts Ring" beschrieben wird — kein zweiter Ring,
nur ein zweiter Titel dafür. Der Ring, den Dodo zerstört hat, ist ein
**anderer, nicht verwandter Ring** — er gehört nicht in diesen Eintrag. Führe
hier ausschließlich Lindos Ring.

### Ringe
<!-- okf: entity=items/ring_der_pocket_dimension,items/magischer_ring -->

ENTSCHEIDUNG: Sammeleintrag. Hier werden die verschiedenen kleineren Ringe der
Kampagne **nur stichwortartig** aufgelistet — jeweils ein bis zwei Sätze, was
der Ring ist und wo er auftauchte. Keine ausführlichen Einzelabschnitte, keine
Chronologie. Diese Ringe waren jeweils nur kurz relevant (etwa der von Dodo
zerstörte Ring, assoziiert mit Abisalis und lila Magie) und verdienen keinen
eigenen Eintrag. Lindos **Ring der Teleportation** gehört ausdrücklich NICHT
hierher, er hat einen eigenen Eintrag.

### Schriftrollen
<!-- okf: entity=items/schriftrollen -->

ENTSCHEIDUNG: Sammeleintrag. Liste die verschiedenen unbedeutenden
Schriftrollen **nur stichwortartig** auf (je ein bis zwei Sätze). Dazu zählt
unter anderem die Schriftrolle vom Anfang aus Session 1. Die **Schriftrolle von
Nerash** (Ritual gegen Vasul) und die **Schriftrolle von Belorus** sind
handlungsrelevant und haben eigene Einträge — sie gehören nicht hierher.

### Casa del Cookie
<!-- okf: entity=locations/casa_del_cookie -->

ENTSCHEIDUNG: Die Casa del Cookie liegt **nordwestlich von Willauch**.

ENTSCHEIDUNG: Die widersprüchlich wirkenden Beschreibungen des Ortes sind
**alle korrekt**. Sessionzeit entspricht Echtzeit, und das Dorf hat sich in
dieser Zeit stark verwandelt — vermutlich durch die dunkle Magie der Hag.
Stelle die Veränderung als Entwicklung über die Zeit dar, nicht als
Widerspruch.

### Ehrenfels
<!-- okf: entity=locations/ehrenfels -->

ENTSCHEIDUNG: **Nox lebt.** Sein Tod ist lediglich ein Gerücht. Im Eintrag darf
er als „Gerüchten zufolge tot oder verschwunden" geführt werden — aber nicht
als Tatsache.

DARSTELLUNG: Das Wiki soll nur so viel wissen wie die Zuschauer. Kennzeichne
Unbestätigtes ausdrücklich als Gerücht und nimm Wissen, das nur am Spieltisch
bekannt ist, nicht vorweg.

### Die Prinzessin
<!-- okf: entity=npcs/die_prinzessin -->

ENTSCHEIDUNG: Die Prinzessin **lebt**. Gerüchten zufolge ist sie tot, ihr
Aufenthaltsort ist unbekannt. Führe den Tod ausdrücklich als Gerücht, nicht als
Tatsache.

### Lenra
<!-- okf: entity=npcs/lenra -->

ENTSCHEIDUNG: Lenra **wirkte tatsächlich durch die Statue**. Die Helden
erinnern sich nicht falsch.

DARSTELLUNG: Das ist allerdings sehr spezifisches Wissen vom Spieltisch. Halte
es im Eintrag knapp und beiläufig; das Wiki soll nicht mehr wissen, als den
Zuschauern zugänglich ist.

### Liam Velora
<!-- okf: entity=npcs/liam_velora -->

ENTSCHEIDUNG: Der korrekte Name lautet **Liam Velora** — Lunaras Bruder. Er
tritt auch als **Ulvanara**, junger Wächter Vorgul'tars, auf; das ist dieselbe
Person unter fremder Kontrolle, kein zweites Wesen.

ENTSCHEIDUNG: Vhar'Zuls Aussage, Liam existiere **nur noch als Seele**, ist
**falsch**. Ob aus Unwissenheit oder Absicht, ist unklar — stelle beides als
offene Möglichkeit dar, aber nicht die Behauptung selbst als Tatsache.

### Hendrik (Nomadenführer)
<!-- okf: entity=npcs/hendrik -->

ENTSCHEIDUNG: **Zwei verschiedene Personen.** Dieser Eintrag betrifft
ausschließlich **Hendrik, den älteren Anführer der Bergnomaden** (Session
2025-08-12). Er hat nichts mit dem Bauern Hendrik Heinrich zu tun.

### Hendrik Heinrich (Bauer)
<!-- okf: entity=npcs/hendrik_heinrich -->

ENTSCHEIDUNG: Der **Bauer und Besitzer der Heinrich-Farm**, die den Silberkernen
als Unterschlupf dient (Session 2026-03-23). Er ist **nicht** identisch mit
Hendrik, dem Anführer der Bergnomaden — die Namensähnlichkeit ist Zufall.

### Jen (Schreiberin)
<!-- okf: entity=npcs/jen -->

ENTSCHEIDUNG: **Zwei verschiedene Personen** tragen diesen Namen. Hier geht es
um die **menschliche Schreiberin**, die die Gruppe nahe der Kapelle antrifft
(Session 2026-06-10).

### Der Jen (Diener Vorgul'tars)
<!-- okf: entity=npcs/der_jen -->

ENTSCHEIDUNG: Ein **mysteriöser Diener Vorgul'tars**, der aus eigenen Interessen
handelt (Session 2026-06-16). **Nicht** identisch mit der Schreiberin Jen.

### Nyruk
<!-- okf: entity=npcs/nyruk -->

ENTSCHEIDUNG: Der korrekte Name lautet **Nyruk**, nicht „Nairuk" — die übrigen
Schreibweisen sind Transkriptionsfehler.

ENTSCHEIDUNG: Nyruk ist ein **großer Eisbär ohne Flugfähigkeit**. Er konnte
**nie** fliegen. Belege, die ihm Fliegen zuschreiben, sind falsch; übernimm sie
nicht.

### Nox
<!-- okf: entity=npcs/nox -->

ENTSCHEIDUNG: Nox ist **männlich**. Weibliche Formen in den Belegen sind
Transkriptionsfehler. Verwende durchgängig männliche Pronomen.

### Perry das Schnabeltier
<!-- okf: entity=npcs/perry_das_schnabeltier -->

ENTSCHEIDUNG: Dass Perry „nicht kampftauglich" sei, beschreibt einen
**vorübergehenden Zustand**, keine dauerhafte Eigenschaft. Stelle es als
zeitweiligen Effekt dar, nicht als Wesensmerkmal.

### Akastrale
<!-- okf: entity=deities/akastrale -->

ENTSCHEIDUNG: Akastrale ist eine **weibliche alte Gottheit**. Verwende
durchgängig weibliche Formen („sie/ihr").

DARSTELLUNG: Zu Akastrale muss vorerst **kein umfangreicher Eintrag**
entstehen. Ein knapper Entwurf des aktuellen Kenntnisstandes genügt;
kennzeichne ihn als vorläufig und fülle Lücken nicht mit Spekulation.

### Rotunas
<!-- okf: entity=characters/rotunas -->

ENTSCHEIDUNG: Rotunas hat im Daggerheart-Regelwerk die Klasse **Giant** und ist
damit ein **Riese** — **kein Elf**. Belege, die ihn als Elf bezeichnen, sind
falsch.

### Cornivum
<!-- okf: entity=locations/cornivum -->

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
<!-- okf: entity=npcs/freibeuter_harald -->

ENTSCHEIDUNG: Es gibt **zwei verschiedene Haralds**. Dieser Eintrag betrifft
ausschließlich den **Freibeuter-Kapitän Harald**, der eine heruntergekommene
Taverne betreibt und sich mit einem Rapier verteidigt — die **wichtigere** der
beiden Figuren. Der Dämon Harald aus Abyssalis hat einen eigenen Eintrag und
gehört nicht hierher.

### Harald (Dämon)
<!-- okf: entity=npcs/abisalis_harald -->

ENTSCHEIDUNG: Ein **Magier-Dämon in Abyssalis**, der mit einem Seelenstein
auftritt. Er ist **nicht** identisch mit dem Freibeuter-Kapitän Harald und
trägt den Namen nur zufällig gleich. Eine Nebenfigur.

### Stiller Gott
<!-- okf: entity=deities/bodrak_gott_der_stille -->

DARSTELLUNG: Wie bei Akastrale — vorerst nur ein knapper Entwurf des aktuellen
Wissensstandes, ausdrücklich als vorläufig gekennzeichnet.

### Thar'Vok, der Erdrichter
<!-- okf: entity=deities/tarvok_der_erdrichter -->

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
<!-- okf: entity=deities/vharzul -->

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
<!-- okf: entity=deities/thyrex -->

ENTSCHEIDUNG: Thyrex, „der Sänger", ist **eine der vier Seelen Vhar'Zuls**,
kein eigenständiges Wesen. In den Transkripten erscheint er als „Tyrex" oder
„T-Rex" — maßgeblich ist die Schreibweise **Thyrex**. Er sprach aus Lindo Lauts
Amulett, verbündete sich mit ihm gegen die drei bösartigen Seelen und ist
seither die vorherrschende Persönlichkeit des wiedererstarkten Vhar'Zul. Der
Widerspruch „einmal absorbiert, einmal eigenständig in Abyssalis handelnd" ist
damit **aufgelöst** — beides trifft zu, nur zu verschiedenen Zeitpunkten;
stelle es als Abfolge dar, nicht als Widerspruch.

### Sythraal
<!-- okf: entity=deities/sythraal -->

ENTSCHEIDUNG: Sythraal, „der Schleier", ist eine der vier Seelen Vhar'Zuls.
In Sessions als „Sintra" gehört.

### Ezhura
<!-- okf: entity=deities/ezhura -->

ENTSCHEIDUNG: Ezhura, „die Glut", ist eine der vier Seelen Vhar'Zuls und eine
der Stimmen in Lindo Lauts Amulett — ihre Statue steht ganz rechts im Schrein.
In Sessions als „Esua", „Esoa" oder „Ezreal" gehört; „Glut" und „Ezua"
bezeichnen dieselbe Entität.

ENTSCHEIDUNG: **Ezhuras Seelenstück wurde nicht ausgelöscht.** Belege, die das
behaupten, verwechseln sie mit **Koll'Mereth**. Ezhura spricht später weiterhin
aus dem Amulett; der Widerspruch beruht auf dieser Verwechslung.

### Koll'Mereth
<!-- okf: entity=deities/kollmereth -->

ENTSCHEIDUNG: Koll'Mereth, „die Krone", ist eine der Seelen Vhar'Zuls und
**keine eigenständige Gottheit**. In Sessions als „Kol Meref" und als „Koll"
gehört — beide Schreibweisen meinen ihn. Die Belege vom oberen Schrein in der
Kapelle und die Gravur auf der linken Statue gehören zu diesem Eintrag; er ist
eine der Stimmen in Lindo Lauts Amulett.

### Slix
<!-- okf: entity=npcs/slix_vasul -->

ENTSCHEIDUNG: Slix ist der **versteckte fünfte Teil Vhar'Zuls** — im *Buch der
vier Seelen* nicht verzeichnet, weshalb dort nur von vier Seelen die Rede ist.
Er gehört zu den vier bösartigen Anteilen. Beschreibe ihn in diesem Verhältnis
und verweise auf den Eintrag zu Vhar'Zul.

### Voras der Heilige
<!-- okf: entity=npcs/voras -->

ENTSCHEIDUNG: Mit **„der Graf"** ist stets **Voras der Heilige** gemeint. Belege
über den Grafen gehören in diesen Eintrag.

### Dormak
<!-- okf: entity=npcs/dormak -->

ENTSCHEIDUNG: Dormak ist ein **Komplize der Hag** ([Lenra](../bundle/splitter_des_ewigen/npcs/lenra.md)).
Beide wollten Vhar'Zul zurückholen — allerdings dessen **ursprünglichen Teil**,
nicht die besonnene Persönlichkeit. Da der wiedererstarkte Vhar'Zul die Gestalt
von Tyrex angenommen hat und diese Persönlichkeit ein **Feind Dormaks** ist,
wurde Dormak am Ende von Vhar'Zul selbst ausgelöscht.

### Huludan
<!-- okf: entity=deities/huludan -->

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
<!-- okf: entity=locations/willauch -->

ENTSCHEIDUNG: Willauch liegt auf der aktuellen Karte im **Südwesten**. Belege,
die die Stadt als „Hauptstadt im Norden" oder „größte Stadt der nördlichen
Schneise" bezeichnen, sind falsch.

ENTSCHEIDUNG: Die kanonische Schreibweise ist **Willauch**. „Willau",
„Willoch" und „Vilauch" sind Transkriptionsvarianten.

### Belorus
<!-- okf: entity=npcs/belorus -->

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
<!-- okf: entity=npcs/hans_soldat_aus_breska,npcs/hans_wirt_zum_gruenen_sichelmond -->

ENTSCHEIDUNG: Es gibt **zwei verschiedene Personen namens Hans**. Der Soldat
aus Breska, der Belorus' versiegelte Botschaft überbringt (Session 2026-01-13),
und der Tiefling-Wirt der Taverne *Zum grünen Sichelmond* (Session 2026-03-18)
haben nichts miteinander zu tun. Sie werden getrennt geführt.

### Adeliga
<!-- okf: entity=npcs/adeliga_der_eulenseraph,npcs/adeliga_vom_haus_des_loewen -->

ENTSCHEIDUNG: Es gibt **zwei verschiedene Frauen namens Adeliga**. Die eine ist
die Besitzerin des *Haus des Löwen* in **Willauch** — eine menschliche
Geschäftsfrau, elegant und kühl, ohne übernatürliche Merkmale (Session
2026-03-03). Die andere ist ein **Eulen-Seraph** und Paladin des neuen Gottes
*Joran der Münzenzähler*, der der Gruppe im **Ringtal** begegnet (Session
2026-06-04). Sie haben nichts miteinander zu tun; der scheinbare Widerspruch
zwischen „Geschäftsfrau" und „himmlisches Wesen" ist keiner.

### Breska
<!-- okf: entity=locations/breska -->

ENTSCHEIDUNG: Die kanonische Schreibweise des Dorfes ist **Breska**.
„Brechka", „Bresca", „Breschka" und „Reska" sind Transkriptionsvarianten.

### Hal / Harl
<!-- okf: entity=npcs/hal_harl -->

ENTSCHEIDUNG: **Hal (auch Harl) hat beide Rollen** — der Widerspruch
„Stellvertreter" gegen „Anführer" ist keiner. Die **Banditenfestung ist ein
Lager der Silberkerne**; er ist dort stellvertretender Anführer und zugleich
Anführer der Silberkerne. Beide Belege gelten.

### Goblin-Götter
<!-- okf: entity=deities/goblingoetter -->

ENTSCHEIDUNG: Die Goblin-Götter sind **chaotisch und wechselhaft**, nicht
bösartig. Der Beleg aus Session 2025-04-15, der sie als „bösartige
Göttergruppe" bezeichnet, ist eine Fehleinschätzung.

### Schwarzer Palantir
<!-- okf: entity=items/schwarzer_palantir -->

ENTSCHEIDUNG: Beide Fundortangaben stimmen und widersprechen sich nicht: Der
Palantir lag im **Labor der Hag**, und dieses Labor liegt **im Sumpf-Dungeon**.

### Verhandlung mit Harl
<!-- okf: entity=events/verhandlung_mit_harl -->

ENTSCHEIDUNG: Es gab **eine einzige Verhandlung**, keine Vorverhandlung. Der
Preis ist derselbe: **eine Truhe Gold = 10 Säcke Gold**. Es war eine
**Gruppenverhandlung** der Rotunas-Freunde, bei der **Lindo Laut die Gruppe
vertrat** — deshalb erscheint er in einem Beleg als alleiniger Verhandler.

### Der Schinder
<!-- okf: entity=npcs/der_schinder -->

ENTSCHEIDUNG: Das Geschlecht des Schinders ist für den Kanon **unerheblich**;
im Zweifel männlich. Kein offener Konflikt.

### Tyrael
<!-- okf: entity=npcs/tyrael -->

ENTSCHEIDUNG: Das Wesen, über das Tyrael konkretes Wissen besitzt, ist
**Vhar'Zul**. „Basul" und „Vasul" sind zwei Transkriptionen desselben Namens;
es besteht kein Widerspruch. Tyrael kennt Vhar'Zul als bekannten Gott und gibt
einige Informationen über ihn preis.

### Dodos heiliger Streitkolben
<!-- okf: entity=items/streitkolben_von_dodo -->

ENTSCHEIDUNG: Dodo führt **eine** heilige Waffe. „Streitkolben", „Dodos
leuchtender Streitkolben", „Heiliger Streitkolben Dodos", „Der heilige
Streitkolben aus Zebras" und „Streitkolben von Zebras" bezeichnen alle
dieselbe. Nicht zu verwechseln mit dem *Morgenstern des Heiligen Duran*, der
Ritter Brandon gehört.

ENTSCHEIDUNG (GM/Noah 2026-08-29): **„Cepros" ist keine dritte, eigenständige
Herkunft** — es ist dieselbe Verhörung wie „Zebras" für **Zebros**, das
gefallene Königreich. Die Waffe heißt **Zebros Zorn**, wurde **in der Festung
Zebros aus einem Spiegel gezogen** und stammt **ursprünglich aus dem
Königreich Zebros** — eine einzige Herkunft, nicht drei. Jede weitere
Erwähnung von „Cepros" im Bundle bezeichnet ebenfalls Zebros.

### Die Hags
<!-- okf: entity=npcs/lenra,npcs/kraeuterhexe_von_lady_kalen -->

ENTSCHEIDUNG: **Lenra** ist *die Hag* der Kampagne. „Die Hack", „Heck",
„Lanra", „Leandra", „Moorhexe" und **„die Sumpfhexe"** bezeichnen alle sie.

ENTSCHEIDUNG: **Ausnahme** — im **Abisalis** (= der *Splitterwelt*) existiert
eine **zweite Hag**, die **nicht** Lenra ist: die **Kräuterhexe der Anhänger
Uhoriaks'**, persönliche Alchemistin von **Lady Kalen**, der Sprecherin
Uhoriaks' und Herrin von Boragdil. Sie darf nie mit Lenra vermengt werden.

### Abisalis
<!-- okf: entity=domains/splitterwelt -->

ENTSCHEIDUNG: **Abisalis ist die Splitterwelt** — dieselbe Domäne, zwei Namen.
„Abyssalis" und „Abyssares" sind Transkriptionsvarianten.

### Koll'Mereth: Auslöschung
<!-- okf: entity=deities/kollmereth -->

ENTSCHEIDUNG: Das Seelenstück, das **Nerash ausgelöscht** hat, ist das von
**Koll'Mereth**, nicht das von Ezhura. Seitdem sind von den vier im Amulett
bekannten Seelen nur noch drei übrig.

### Blutschalen-Statuen

DARSTELLUNG: Die namenlose „böse Gottheit" der Statue mit der Blutschale ist
**nicht sicher zuzuordnen** — wahrscheinlich Vhar'Zul, aber **jede
Blutschalen-Statue kann einem anderen Gott gehören**. Eine Statue mit
Blutschale ist also *kein* Erkennungsmerkmal für eine bestimmte Gottheit.
Entsprechend vorsichtig formulieren und keine Zuordnung als gesichert
darstellen.

### Zebros
<!-- okf: entity=factions/koenigreich_zebros -->

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

DARSTELLUNG: Hauptstadt und Berg sind bislang nur durch diese eine Nennung
belegt und bekommen deshalb vorerst **keine eigenen Einträge** — beschreibe
beide knapp innerhalb dieses Eintrags. Ein eigener Eintrag ist erst
gerechtfertigt, sobald weitere Sessions sie unabhängig voneinander behandeln.

### Hartwacht
<!-- okf: entity=locations/hartwacht -->

ENTSCHEIDUNG: Hartwacht ist eine **Stadt**, keine uneinnehmbare Orkfestung.
Der Beleg aus Session 2026-03-18 (00:45:15), der sie als "uneinnehmbare
Orkfestung" bezeichnet, ist ungültig — er beruht auf einer Fehldarstellung am
Tisch. Gültig bleibt die Beschreibung aus Session 2025-10-07 (00:09:39): eine
Stadt, die die Magier vor dem Golem schützen wollten. Die Lage hinter einem von
Vargen bewohnten Pass und das Reiseziel der Gruppe bleiben davon unberührt —
nur die Einordnung als Festung entfällt. Führe diesen Punkt nicht als offenen
Konflikt auf.

---

Kopiervorlage für einen neuen Abschnitt — absichtlich eingerückt, damit die
`###`-Zeile hier selbst keine Überschrift ist und nicht als eigener (dann
funktionsloser) Abschnitt geladen wird:

    ### <Entitätsname>
    <!-- okf: entity=<typ>/<concept_id> -->

    ENTSCHEIDUNG: <Was gilt.> Frühere Belege, die <X> behaupten, beruhen auf
    <Transkriptionsfehler / Missverständnis am Tisch / Retcon> und sind
    ungültig.
