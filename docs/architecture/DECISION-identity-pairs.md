# Identity pairs awaiting a GM ruling

Nine pairs of concept ids surfaced during the 2026-09-22 bundle regeneration
(`docs/audits/2026-09-22-rename-guard-override.md`, rows 20-28) that the
resolver could not safely decide on its own. Each pair is two spellings of
what may be the same entity, or may genuinely be two things — a matcher
folding them automatically is exactly how
[INCIDENT-2026-08-mass-rename.md](INCIDENT-2026-08-mass-rename.md) started:
guessing identity from spelling silently discarded half the campaign's
accumulated identity work, twice. This document exists so nobody has to
guess. It is not a ruling; it is the evidence a ruling needs.

**Sources used below:** the raw LLM extraction cache
(`services/kb/.cache/extract/`, one JSON per session — the `note` field is
what the model understood at that moment, quoted verbatim in German) and the
`retired:` ledger in `knowledge/entity_registry.yaml` (concepts a prune
already deleted from disk, kept there with their canonical name and
aliases). Where one half of a pair still has a file in
`knowledge/bundle/splitter_des_ewigen/`, its current body is summarized.

> **Ruled 2026-09-23, not at the table.** The campaign owner delegated these
> calls, so they were made from the extraction-cache evidence below and
> encoded in `knowledge/entity_rules.yaml` (commit `b9a7d71`). That evidence
> can show which spellings were *spoken*; it cannot show what they referred
> to. Every ruling is one line to reverse, with its reasoning beside it in
> the rules file. Pair 3 is only half-ruled and pair 7 was left alone
> because a standing GM ruling already covers it -- those two are the ones
> worth a second look.

**How to fill this in:** for each pair, replace `<same entity | distinct
entities | fold both into X>` with your ruling and write the reason — a
sentence is enough, but it's the part that gets kept. If you know something
that isn't in the evidence (something said at the table, off the recording),
say so; that's exactly the kind of thing this process can't see on its own.

**What happens to your answers:** "same entity" becomes a `merge:` line in
`knowledge/entity_rules.yaml` (both spellings folded into one concept id,
your reason as the comment above it); "distinct entities" becomes a
`never_merge:` group (the two ids pinned apart, same comment convention);
"fold both into X" merges both into a third, already-existing concept. Six
of these nine pairs (2, 3, 4, 5, 6, 8) are currently blocking a registry
backfill, so ruling on those six unblocks other work even if the rest wait.

---

## 1. Amulett mit Rabenschädel / Krähenschädel

- `items/amulett_mit_rabenschaedel` — **survives** in the bundle.
- `items/amulett_mit_kraehenschaedel` — retired (no file on disk).
- Background: Rabe (raven) vs Krähe (crow) — different birds.

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "Rabenschädel" | 0 |
| "Krähenschädel" | 1 |

Only "Krähenschädel" appears anywhere in the 69-session cache — no mention
under the raven spelling was found at all.

- Session `2025-04-30_RF_fsCOiSkKKTE` (2025-04-30), item "Amulett mit
  Krähenschädel", `citation_ts` 01:30:26:
  > „Gulrak behauptet, dieses magische Familienerbstück sei im Besitz von
  > Baran und er habe versucht, es zurückzustehlen. Das Amulett soll einen
  > Krähenschädel darstellen und von Gulraks Urgroßvater stammen. Es wird in
  > dieser Session nicht gesehen.“

**What the surviving concept currently claims:** its title and entire body
are about the *Krähenschädel* — despite living under the `rabenschaedel` id,
the file contains no mention of a raven at all; it is word-for-word the
Krähenschädel note above.

**Ruling:** same entity
**Reason:** "Rabenschaedel" has no attestation in any of the 69 cached sessions; the one real source (2025-04-30) is a Kraehenschaedel note and items/amulett_mit_rabenschaedel.md is that note word for word. One amulet whose id drifted from its own content.
**Rule added:** `amulett mit krähenschädel: items/amulett_mit_rabenschaedel`
**Reason:**

---

## 2. Notiz von Tyrex / Notiz von Tyrael

- `items/notiz_von_tyrex` — **survives** in the bundle.
- `items/notiz_von_tyrael` — retired (no file on disk).
- Background: `deities/thyrex` and `npcs/tyrael` both exist as separate
  surviving concepts — likely two different beings, so this may be two
  different notes, not one mis-transcribed one.

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "Notiz von Tyrex" (item) | 0 |
| "Notiz von Tyrael" (item) | 1 |

No item named "Notiz von Tyrex" was found anywhere in the cache — the
`items/notiz_von_tyrex` id's only cache-traceable source is the "Notiz von
Tyrael" mention below.

- Session `2026-03-24_RF_Yj5BWJfg3Ag` (2026-03-24), item "Notiz von
  Tyrael", `citation_ts` 01:33:57:
  > „Lunara liest eine Notiz ihres Kontakts Tyrael vor, die vor den
  > erstarkenden Vasul-Teilen im Abyssalis warnt und zum Handeln auffordert.
  > Die Notiz wurde beim Nekromanten gefunden und zunächst für unwichtig
  > gehalten.“

**Context — the two candidate namesakes, all mentions:**

- `deities/thyrex` (a soul-aspect of the dead god Vhar'Zul, voice in Lindo
  Lauts amulet):
  - Session `2025-09-02_RF_TLZOH7TlGhk` (2025-09-02), Deity "Tyrex",
    `citation_ts` 02:12:11:
    > „Tyrex ist eine der Seelen in Lindo Lauts Amulett, die sich als
    > väterliche, warnende Stimme zeigt. Nach Lindo Lauts erster
    > Verwandlung sagt er, dass dies alles ändert. Er warnt Lindo Laut vor
    > den anderen Stimmen und drängt zur Vorsicht. Am Ende gibt er Lindo
    > Laut die Kraft, Esua und Sintra über den Thron zu zerstören. Danach
    > fühlt sich das Amulett leer an. Tyrex scheint ein Aspekt des Gottes
    > Varsu zu sein oder zumindest mit ihm verbunden.“
  - Session `2025-09-06_RF_vo1xnyLQDJk` (2025-09-06), NPC "Tyrex",
    `citation_ts` 00:01:05:
    > „Tyrex wird nur als vorherige Identität erwähnt. Vasul hat seine
    > Persönlichkeit übernommen, aber Lindo Laut nimmt noch Charakterzüge
    > von Tyrex in Vasul wahr. Tyrex selbst ist nicht mehr aktiv.“
- `npcs/tyrael` (undead lich/mage in the Abyssalis, Lunara's contact,
  `important: true` in the registry):
  - Session `2025-10-14_RF_cUtz87UCHu4` (2025-10-14), NPC "Tyrael",
    `citation_ts` 01:25:02:
    > „Tyrael ist ein untoter Lich und mächtiger Magier. Er erkennt sofort
    > zwei Wesen in Lindo Laut und hält ihn mit einem Zauber fest. Er gibt
    > Lindo Laut ein Stück vergorenes Fleisch, das den Dämon stillen soll,
    > und warnt, dass dieser bald erwachen wird. Lindo Laut liest in
    > Tyraels Gedanken und erfährt, dass die Entität mit Valsor/Basul
    > verbunden ist, einem Herrn der Seelen, dessen Ursprung 'Abyssalis'
    > ist. Tyrael gesteht, einst auf einer Seite im Götterkrieg gekämpft zu
    > haben und bestraft worden zu sein. Er rät, nicht am Magierkampf
    > teilzunehmen, und verschwindet per Teleport.“
  - Session `2026-03-24_RF_Yj5BWJfg3Ag` (2026-03-24), NPC "Tyrael",
    `citation_ts` 01:33:57 — **note this line names both spellings in the
    same breath:**
    > „Tyrael (auch als Tyrex bezeichnet) ist Lunaras Kontakt im Abyssalis,
    > quasi ihre Augen und Ohren dort. Er hat ihr eine Notiz zukommen
    > lassen, in der er vor den erstarkenden Teilen von Vasul warnt und
    > dringendes Handeln anmahnt. Lunara plant, ihn in seinem Versteck
    > aufzusuchen und ihm den Stab zu übergeben, um gegen die
    > Vasul-Teile vorzugehen. Er wird von Lindo als Anhänger Tarvoks und
    > Vorgutars beschrieben, der jedoch taktisch und nicht blind loyal
    > handelt.“

**What the surviving concept currently claims:** the `notiz_von_tyrex` file's
title and body are entirely the Tyrael note (links to `/npcs/tyrael.md`) —
nothing about the amulet-voice Tyrex survives on it.

**Ruling:** same entity, for this item only
**Reason:** "Notiz von Tyrex" is unattested. The sole item mention (2026-03-24) names the sender "Tyrael (auch als Tyrex bezeichnet)", so the fiction itself bridges the two spellings for this note. Deliberately narrow: deities/thyrex and npcs/tyrael remain distinct beings and the existing `tyrex:` merge is untouched. This rules on the note, not on who wrote it.
**Rule added:** `notiz von tyrael: items/notiz_von_tyrex`
**Reason:**

---

## 3. Orlanius Schwarzhorn / Orlanius Schwarzohr

- `npcs/orlanius_schwarzhorn` — **survives** in the bundle.
- `npcs/orlanius_schwarzohr` — retired (no file on disk).
- Background: Horn vs Ohr (ear).

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "Schwarzhorn" | 0 |
| "Schwarzohr" | 2 |

No mention under "Schwarzhorn" was found anywhere in the cache.

- Session `2026-07-29_Team-A_umGyKLkefJI` (2026-07-29), NPC "Olanio
  Schwarzohr" — note the first name is spelled differently here too,
  `citation_ts` 01:13:00:
  > „Olanio Schwarzohr ist ein Weggefährte von Meister Pyrandas. Er hat
  > anscheinend bereits ein paar Schlucke getrunken, kichert, nickt den
  > Helden lächelnd zu und folgt dann etwas schwankend Meister Pyrandas.“
- Session `2026-08-04_Team-A_qRj2t3wQHfs` (2026-08-04), NPC "Orlanius
  Schwarzohr", `citation_ts` 02:02:21:
  > „Orlanius Schwarzohr ist ein weiterer Vertreter der alten Garde in
  > Ehrenfels. Er tritt zusammen mit Meister Pyrandras auf und wird von
  > einem Seraphen bedroht, der ihm eine Waffe ins Gesicht hält. Er
  > erschrickt, fällt von einem Stein, rappelt sich aber wieder auf und
  > zeigt eine besänftigende Geste, um die Situation zu deeskalieren. Er
  > scheint eher vorsichtig zu sein.“

Both mentions describe a companion of "Meister Pyrandras"/"Pyrandas", six
days apart — plausibly one NPC introduced twice, but that is exactly the
kind of read this document is not supposed to make on its own.

**What the surviving concept currently claims:** the `orlanius_schwarzhorn`
file's title and body are entirely the "Orlanius Schwarzohr" note from
2026-08-04 (the "Ohr" spelling) — no "Schwarzhorn" content survives on it.

**Ruling:** same entity (one form only)
**Reason:** "Schwarzhorn" is unattested; both real mentions say "Schwarzohr" and both describe a companion of Meister Pyrandras. **But only "Orlanius Schwarzohr" is routed.** The second attested form, "Olanio Schwarzohr", is left split: Olanio vs Orlanius is a different first name, not a spelling slip, and folding npcs/olanio_schwarzohr in would be an identity claim this evidence does not carry. That merge was made, measured, and then withdrawn -- it cleared the rename guard one id sooner but created a new abandonment as a side effect of the guess.
**Rule added:** `orlanius schwarzohr: npcs/orlanius_schwarzhorn` -- and deliberately NOT `olanio schwarzohr`
**Reason:**

---

## 4. Begegnung mit Landra / Begegnung mit Lanra

- `events/begegnung_mit_landra` — **survives** in the bundle.
- `events/begegnung_mit_lanra` — retired (no file on disk).

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "Landra" | 0 |
| "Lanra" | 2 |

Both from session `2025-04-15_RF_YCpAz_syjaY` (2025-04-15):

- NPC "Lanra", `citation_ts` 01:53:46:
  > „Lanra ist eine Hexe (Hack), die im hinteren Teil der Krypta erscheint.
  > Sie ist offenbar diejenige, die das Feuerwesen beschwören darf, und
  > steht vermutlich hinter den Bugbären und dem Angriff auf Breschka. Sie
  > schrumpft Dodo auf Froschgröße, stellt sich den anderen vor und bittet
  > Lindo Laut um ein Lied. Sie ist selbstsicher, spöttisch und nennt die
  > Gruppe „niedriges Pack“. Nachdem sie den Altar berührt, verschwindet
  > sie und hinterlässt Schriftrollen mit Hinweisen auf einen gesuchten
  > Magier in Breschka.“
- Event "Begegnung mit Lanra", `citation_ts` 01:52:34:
  > „Im letzten Raum öffnen sich die Tore und Lanra, eine Hexe, erscheint.
  > Sie schrumpft Dodo auf Froschgröße, stellt sich vor und genießt Lindos
  > Lied. Cookie versucht, die Voodoo-Puppe gegen Lanra einzusetzen,
  > verletzt sich aber selbst. Lanra berührt den Altar und verschwindet,
  > hinterlässt Schriftrollen mit Hinweisen auf Breschka.“

**Important context:** the witch herself is not actually split in the
registry — a third id, `npcs/lenra` (canonical name "Landra, die Hag"),
already carries **both** "Landra" and "Lanra" as registered aliases
(alongside "Lenra", "Leandra", "Hack", "Die Hack", "Sumpfhexe", etc.), and
the surviving event file already links its "Landra" mention to
`/npcs/lenra.md`. The 2026-08-30 spelling sweep
(`docs/audits/2026-08-30-spelling-sweep.md`) independently canonicalized
"Lanra" → "Landra" (42 hits), "Leandra" → "Landra" (21 hits) and "Lenra" →
"Landra" (9 hits) in prose. So the **NPC** identity question is effectively
already settled; what remains open here is only whether the two **event**
concepts (`begegnung_mit_landra` / `begegnung_mit_lanra`) — both describing
the same scene, same session, same near-identical timestamp — are one event
or two.

**What the surviving concept currently claims:** the `begegnung_mit_landra`
file's title is "Begegnung mit Lanra" and its body is the Event note quoted
above (using "Landra" in running prose, linked to `npcs/lenra`).

**Ruling:** same entity
**Reason:** The event spelling "Landra" is unattested; the sole Event-type mention is "Begegnung mit Lanra" and the surviving file's own title reads that way under the `landra` id. The NPC half was already settled by the existing `lanra: npcs/lenra` merge, so only the event id needed to catch up.
**Rule added:** `begegnung mit lanra: events/begegnung_mit_landra`
**Reason:**

---

## 5. Tatrick / Tattrick

- `npcs/tatrick` — **survives** in the bundle.
- `npcs/tattrick` — retired (no file on disk).

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "Tatrick" | 0 |
| "Tattrick" | 1 |

- Session `2026-06-16_RF_qe0ck8hvYpk` (2026-06-16), NPC "Tattrick",
  `citation_ts` 00:16:31:
  > „Der uralte Demilich Tattrick lebt im Keller eines Turms in der Narbe.
  > Er hat einen Teil seines Verstands verloren, erinnert sich aber an ein
  > Kind, das vor etwa zwölf Jahren zum Tempel des Herrn der Schleier
  > gebracht wurde und von der Umgebung geschützt war. Er kennt den
  > versteckten Altar und das Geheimwort "Splitter des Ewigen", mit dem man
  > hineinkommt. Im Verlauf wird offenbart, dass er einst von Vorgul'tar
  > getötet wurde, als dieser den Splitter nicht nutzen konnte, aber der
  > Ort ließ ihn nicht sterben. Er trägt ein Kontrollsymbol am Hinterkopf,
  > das von Jen aktiviert wird und ihn kurzzeitig zur Marionette macht.
  > Esterossa brennt dieses Symbol mit heiliger Magie aus und befreit ihn;
  > danach verrät er das Passwort und hält die herannahenden Feinde auf.“

No mention under the single-t spelling was found anywhere in the cache.

**What the surviving concept currently claims:** the `tatrick` file's title
and full body are this same Tattrick (double-t) note verbatim.

**Ruling:** same entity
**Reason:** "Tatrick" unattested, "Tattrick" attested once (2026-06-16), surviving file is that note verbatim. Clean id drift.
**Rule added:** `tattrick: npcs/tatrick`
**Reason:**

---

## 6. Trillo / Trilo

- `npcs/trillo` — **survives** in the bundle.
- `npcs/trilo` — retired (no file on disk).

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "Trillo" | 0 |
| "Trilo" | 2 |

Both from session `2026-05-27_RF_IYYmgpqsp7E` (2026-05-27):

- NPC "Trilo", `citation_ts` 00:34:29:
  > „Trilo ist ein Jäger und Ordensbruder mit einem leuchtenden Stab,
  > Narben im Gesicht und fehlendem Finger. Er verfügt über Schutzmagie,
  > Heilung und Teleportation. Zunächst wirkt er loyal zu Vilaux und führt
  > die Gruppe auf eine Expedition, warnt aber vor hoher Sterblichkeit. Im
  > Verlauf wird deutlich, dass er die Gruppe belügt: Er lässt den
  > Schutzzauber im Turm fallen und stellt sie Kalos als 'gutes Material'
  > vor. Er bietet ihnen an, sich der Organisation anzuschließen, und
  > teleportiert sich davon, als sie ablehnen. Seine wahren Motive bleiben
  > teilweise unklar, aber er ist ein Verräter, der die Gruppe in eine
  > Falle lockt.“
- Event "Verrat durch Trilo und Rekrutierungsversuch", `citation_ts`
  01:28:42:
  > „Im alten Turm offenbart Trilo, dass er nicht mehr Vilaux dient, und
  > stellt die Gruppe Kalos vor. Kalos bietet ihnen Gold und Land, wenn sie
  > sich seiner Organisation anschließen; andernfalls droht er mit
  > Opferung. Die Gruppe lehnt ab, Trilo teleportiert sich weg, und Kalos
  > beschwört Kampfverstärkung. Dieses Ereignis markiert den Wendepunkt der
  > Session und deckt die Illoyalität des Jägers auf.“

No mention under the double-l spelling was found anywhere in the cache.

**What the surviving concept currently claims:** the `trillo` file's title
and body are this same "Trilo" NPC note verbatim.

**Ruling:** same entity
**Reason:** "Trillo" unattested, "Trilo" attested twice in one session, surviving file is that note verbatim. Clean id drift.
**Rule added:** `trilo: npcs/trillo`
**Reason:**

---

## 7. Armringe von Lindo Laut / Ring von Lindo Laut

- `items/armringe_von_lindo_laut` — **survives** in the bundle.
- `items/ring_von_lindo_laut` — retired (no file on disk). Oddly, even its
  retired registry entry's `canonical_name` already reads "Armringe von
  Lindo Laut", not "Ring" — a system-side lean towards the same identity
  that was never turned into a rule.
- Background: plural vs singular — may be two different objects.

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "Armringe von Lindo Laut" | 1 |
| "Ring von Lindo Laut" | 1 |

- Session `2026-03-03_RF_BRUNuNKTeOg` (2026-03-03), item "Armringe von
  Lindo Laut", `citation_ts` 01:47:16:
  > „Lindos Armringe glühen kurz auf, als er die rote Magie-Seite sieht –
  > wie ein leichtes Zucken. Er hat ein Déjà-vu, kann aber die Bedeutung
  > nicht entschlüsseln.“
- Session `2025-09-02_RF_TLZOH7TlGhk` (2025-09-02), item "Ring von Lindo
  Laut", `citation_ts` 02:11:18:
  > „Der Ring, den Lindo Laut an seinem Mittelfinger trägt, wurde bisher
  > nicht aktiviert. In der finalen Konfrontation nutzt er ihn, um sich auf
  > den Thron zu teleportieren. Der Ring scheint durch die neue Form
  > zusätzlich verstärkt zu sein.“

**Not to be confused with:** session `2025-04-23_RF_z3C-bewKqUs`
(2025-04-23) also has a "Magische Armringe" item, but that one belongs to
**Rotunas**, not Lindo Laut — a different item entirely, unrelated to this
pair.

The two candidate mentions describe different behavior at different points
in the story: the ring is worn on a finger and used to teleport during the
climactic 2025-09-02 confrontation with the throne; the armringe glow in
reaction to red magic seven months later (2026-03-03), with no mention of a
teleport or throne connection. This supports the "may be two different
objects" reading, but is not conclusive on its own.

**What the surviving concept currently claims:** the `armringe_von_lindo_laut`
file's title and body are the "Armringe" (plural) note from 2026-03-03,
matching its id.

**Ruling:** distinct entities -- and already ruled
**Reason:** Both spellings are attested once each and describe materially different objects: glowing bracelets versus a ring that teleports. Decisively, `entity_rules.yaml` already carries a 2026-08-29 GM-Klarstellung routing `ring von lindo laut` to items/ring_der_teleportation, with the ring Dodo destroyed noted as a third unrelated item. Merging this pair would collapse three items into fewer and contradict a standing ruling.
**Rule added:** none -- no new rule. The existing GM ruling stands.
**Reason:**

---

## 8. Heiliger Streitkolben aus Zebros / aus Zebras

- `items/heiliger_streitkolben_aus_zebros` — **survives** in the bundle.
- `items/heiliger_streitkolben_aus_zebras` — retired (no file on disk).
- Background: may actually be `items/streitkolben_von_dodo`.

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "...aus Zebros" | 0 |
| "...aus Zebras" | 1 |

- Session `2026-01-13_RF_w4LB1s9_3rs` (2026-01-13), item "Heiliger
  Streitkolben (aus Zebras)", `citation_ts` 01:37:13:
  > „Dodos heiliger Streitkolben aus Zebras. Er leuchtet und ist in der
  > Lage, den magischen Schild der Gegner zu durchdringen. Er verursacht
  > hohen Schaden und tötet den Schreckensritter.“

No mention under "aus Zebros" was found anywhere in the cache. The surviving
file itself is internally inconsistent: its title/registry `canonical_name`
read "Heiliger Streitkolben (aus Zebras)" while its own body prose says "aus
Zebros" — i.e. even the file that carries the `zebros` id currently asserts
the `zebras` spelling in its title.

**Existing precedent — quote from `knowledge/entity_rules.yaml`:**

```yaml
# line 128
cepros' heiliger streitkolben: items/streitkolben_von_dodo
# 2026-08-30 spelling sweep: "Cepros" bare (origin references outside the
# weapon phrase above) is the same mishearing of "Zebros" -- GM ruling
# 2026-08-29 overturns the prior Kanon_Entscheidungen.md entry that treated
# it as a separate origin. See sources/Kanon_Entscheidungen.md.
cepros: factions/koenigreich_zebros
# items/zebras_zorn duplicates items/streitkolben_von_dodo ("Zebros Zorn")
# under a one-letter-off title that dodged validate.py's exact-match
# duplicate_titles check. Same weapon, fold it in.
zebras zorn: items/streitkolben_von_dodo
```

And from `docs/audits/2026-09-22-rename-guard-override.md`:

> Rows 27-28 deserve a specific look: `entity_rules.yaml` already maps
> `cepros' heiliger streitkolben` and `zebras zorn` to
> `items/streitkolben_von_dodo`, so both of these may be that same mace
> under a third and fourth mishearing.

The surviving `items/streitkolben_von_dodo` concept (canonical name "Zebros
Zorn") already carries both "Streitkolben von Zebras" and "Der heilige
Streitkolben aus Zebras" as registered aliases — i.e. this exact wording has
already been folded into that concept once, independently of this pair.

**What the surviving concept currently claims:** the `heiliger_streitkolben_
aus_zebros` file's body describes Dodo's glowing holy mace piercing a magic
shield and killing the Schreckensritter, and already links the word
"Streitkolben" to `/items/streitkolben_von_dodo.md`.

**Ruling:** fold both into `items/streitkolben_von_dodo`
**Reason:** "aus Zebros" is unattested; "aus Zebras" is attested once (2026-01-13, Dodo's glowing mace). entity_rules already folds `zebros zorn`, `zebras zorn`, `zebrus zorn` and `cepros' heiliger streitkolben` into items/streitkolben_von_dodo, and QUALITY.md records items/zebras_zorn as the same weapon. This is a further mishearing of that one mace, so it folds there rather than into its pair.
**Rule added:** `heiliger streitkolben (aus zebras): items/streitkolben_von_dodo`
**Reason:**

---

## 9. Streitkolben von Zebros / Streitkolben von Cepros

- `items/streitkolben_von_zebros` — **survives** in the bundle.
- `items/streitkolben_von_cepros` — retired (no file on disk).
- Background: same situation as pair 8.

**Mentions found in the extraction cache:**

| Spelling | Count |
|---|---|
| "Streitkolben von Zebros" | 0 |
| "Streitkolben von Cepros" | 1 |

- Session `2026-03-10_RF_Kr9_AC2XtOw` (2026-03-10), item "Streitkolben von
  Cepros", `citation_ts` 00:25:24:
  > „Dodo benutzt einen Streitkolben, der nach Cepros benannt ist. Im Kampf
  > gegen die Ghule und die Schattenkreatur setzt er ihn effektiv ein. Der
  > Kolben scheint mächtig zu sein.“

No mention under "Streitkolben von Zebros" was found anywhere in the cache —
this is the **same** session/timestamp cited by the surviving
`streitkolben_von_zebros` file, i.e. the `zebros`-id concept's only
cache-traceable source is this Cepros mention. Its title/registry
`canonical_name` already reads "Streitkolben von Cepros" while its body
prose says the weapon "ist nach Zebros benannt" — the same
title/body-text mismatch as pair 8.

**Existing precedent:** same `entity_rules.yaml` lines quoted under pair 8
apply here — `cepros` alone is already mapped to
`factions/koenigreich_zebros` (line 133), and the 2026-08-30 spelling sweep
(`docs/audits/2026-08-30-spelling-sweep.md`) explicitly recorded: *"'Cepros'
never made it into the registry as an alias at all — extraction never
proposed it as a mention; needs a direct `merge:`/`spelling:` addition, not
just a registry fix."* Two more rule lines already fold other Zebros
spelling drift into the same weapon (`entity_rules.yaml` around line 439):

```yaml
zebrus zorn: items/streitkolben_von_dodo
zebros zorn: items/streitkolben_von_dodo
```

So `items/streitkolben_von_dodo` already absorbs "Zebrus", "Zebras" and
"Zebros Zorn" spellings of the same mace; this pair would be a third and
fourth ("Zebros"/"Cepros", in the "von X" phrasing rather than "X Zorn").

**What the surviving concept currently claims:** the `streitkolben_von_
zebros` file's body is the Cepros-battle note quoted above, and already
links "Streitkolben" to `/items/streitkolben_von_dodo.md`.

**Ruling:** fold both into `items/streitkolben_von_dodo`
**Reason:** Same weapon family as pair 8. "von Zebros" is unattested, "von Cepros" attested once (2026-03-10). The 2026-08-30 spelling sweep flagged this exact gap -- Cepros never reached the registry as an alias of the mace. The existing bare `cepros:` key covers Cepros-as-kingdom, not this weapon phrase.
**Rule added:** `streitkolben von cepros: items/streitkolben_von_dodo`
**Reason:**
