# T00 — Tracking model: what the KB records, and how

**Status:** design, approved scope for plans T1–T9. Not code.
**Audience:** the agent implementing T1–T9, and the human reviewing them.
**Read with:** [PIPELINE.md](../architecture/PIPELINE.md) (§4 identity,
§6 caching, §7 emit order), [ADR-004](../architecture/ADR-004-identity-primitive.md).

---

## 1. Problem, in numbers (measured 2026-10-18)

The bundle answers "who/what exists" and doesn't answer "what is going on":

| Finding | Number | Consequence |
|---|---|---|
| Event concepts | 305, **all** single-session | They restate the session recap's scene headings |
| Events with no inbound link from another entity | 286 / 305 | Nobody navigates to them |
| Events the wiki can show | 0 new (gate `MIN_SESSIONS = 2` in pnp-export-data) | 27 % of the bundle has no consumer |
| Quest / plot-thread concepts | 0 (reports S01–S26 had 19 `QUEST_` ids) | The pre-session recap has to guess "Offene Fäden" from prose |
| Alive / dead / missing status | prose only | "Is Rotunas dead?" is two contradictory Event pages |
| NPC attitude to the party | prose only | — |
| Observed vs. claimed facts | not recorded | An NPC's (likely false) retelling of Rotunas' death became `events/tod_von_rotunas` |
| Which table (Team A/B/C/W) saw a fact | not recorded | 55 Team-A, 4 Team-B, 1 willauch, 8 untagged sessions share one world |
| Source timestamps in `sources[]` | none (prose `# Belege` only) | A claim can't be checked in one click |
| Entities with positional source ids `'1'..'n'` | ~170 | 8 sessions (2026-08-12 → 2026-09-22) missing from `knowledge/episodes.yaml` |
| Rules jargon mistaken for world facts | e.g. "überlebt mit einem Hitpoint", "Heiltrank (1w4)" | The extractor misreads Daggerheart mechanics |

## 2. Principles (constraints every T-plan obeys)

1. **No identity churn.** Nothing in T1–T9 re-runs entity extraction or
   changes `EXTRACT_SYSTEM`. New information comes from a **separate,
   separately cached pass** (the *state pass*, T5) or is derived
   deterministically from data already on disk. Concept ids of existing
   entities must not move. (A re-extraction is B2's job, after opaque ids in
   B1.)
2. **Deterministic where possible, LLM only where judgement is needed.**
   Teams, timestamps, rosters and event anchoring are pure code. Only
   threads, status changes and attitudes need the model.
3. **Every structured fact carries evidence**: session, timestamp and an
   *evidence kind* (§4.4). A fact without a timestamp is not emitted.
4. **Machine fields in English, prose in German.** Frontmatter keys and enum
   values are English (`world_status: dead`), as the OKF `type` values
   already are. Body text, headings and labels stay German.
5. **Don't use OKF-reserved keys.** `status` is reserved by OKF v0.2 SPEC §5.4
   (`draft|stable|deprecated`). Use `world_status`, `thread_status`.
6. **No real player names in the bundle** (default; §6 decision D1). Player
   names are private data that lives only in pnp-crawl's gitignored
   `groups/`.
7. **Additive frontmatter.** New keys only. Existing keys keep their meaning,
   so pnp-export-data keeps working unchanged. (It reads `title`, `type`,
   `aliases`, `id`, episode fields and `body_md`; verified by grep
   2026-10-18.)
8. **Cheap to re-emit.** After the state pass is cached, `pnp run` stays a
   warm re-emit (~$0.05). The state pass itself is its own subcommand
   (`pnp state`) with `--estimate`, so its cost is always a deliberate act.

## 3. Target model at a glance

```
knowledge/bundle/splitter_des_ewigen/
  characters/ npcs/ locations/ factions/ items/ deities/ domains/   (unchanged dirs)
     + new frontmatter: teams, world_status, attitude (T2, T7, T8)
     + new body section:  "## Stand" (T7)
  events/          only ARCS: allowlisted multi-session or pivotal events (T4)
  threads/   NEW   quests, mysteries, promises, debts, deadlines   (T6)
  sessions/        + "# Ereignisse" section with scene anchors       (T4)
                   + "# Offene Fäden" section: threads touched      (T6)
knowledge/
  episodes.yaml    complete (every transcript has an episode id)    (T1, crawl C3)
  roster.yaml NEW  in-world PC roster: name, class, team, since     (T8)
  entity_rules.yaml + families: event_concepts, thread_rules        (T4, T6)
services/kb/.cache/state/<session>/<key>.json   NEW cached state pass (T5)
```

## 4. Data definitions

### 4.1 Source entries (T1)

Every `sources[]` entry gains `at` and `url_at`:

```yaml
sources:
- id: S1-02-A
  resource: https://www.youtube.com/watch?v=qRj2t3wQHfs
  at: '01:46:53'
  url_at: https://www.youtube.com/watch?v=qRj2t3wQHfs&t=6413s
  last_modified: '2026-07-16T00:00:00Z'
```

- `at` = the mention's `citation_ts`, verbatim `HH:MM:SS`. Omitted if the
  timestamp doesn't parse.
- `url_at` = `resource` + `&t=<seconds>s` (YouTube accepts this). Omitted
  when `at` is omitted.
- `resource` is **unchanged**, so nothing downstream breaks.
- Positional ids `'1'..'n'` become a validation ratchet that must reach 0
  once episodes.yaml is complete.

### 4.2 Teams (T2)

```yaml
teams: [A, B]   # sorted letters, derived from the episodes of the cited sessions
```

- Derived per entity from `mentions → session url → episodes.yaml team →
  letter` (`teams:` map in episodes.yaml: Team-A→A, Team-B→B, Team-C→C,
  willauch→W).
- A session with no team leaves no letter. An entity whose sessions all have
  no team gets no `teams` key.
- The same field goes on Session concepts as `team_letter`. (Sessions already
  carry `team: Team-A`; keep that as it is.)

### 4.3 Events → arcs and anchors (T4)

**Old:** each extracted Event mention becomes or joins an `events/<slug>`
concept.

**New:**

- An Event concept is emitted **only if** its concept id is listed in the
  new `event_concepts:` family of `entity_rules.yaml`. Examples: PC deaths,
  the Willauch tournament, sieges, "Verhandlung mit Harl" (which already has
  a live wiki page and must survive).
- Every other Event mention is rendered as a **scene anchor** in its
  session note, under a new `# Ereignisse` section:
  ```markdown
  # Ereignisse

  ### Kampf gegen die Ghule am Brunnen
  _Kampf · 01:12:40 · beobachtet_

  Die Gruppe … (the mention note, autolinked)
  ```
  Each anchor is a `###` heading, so it gets a stable markdown anchor
  (`#kampf-gegen-die-ghule-am-brunnen`).
- Several sessions' event mentions can be folded into one arc with the
  existing `merge:` rules (name → `events/<arc>`). Merged events are
  "explicit" and already bypass the span cap (`resolve.py`, the `explicit`
  variable in `resolve_entities`).
- Links that pointed at a retired event concept are dropped to plain text by
  `normalize_body` (existing behaviour). T4 measures how many.

### 4.4 Evidence kinds (T5, used by T6/T7)

| Value | German label | Meaning | Example |
|---|---|---|---|
| `observed` | beobachtet | Happened on screen, narrated by the GM as fact or played out | Rotunas implodes holding Nerash (2026-04-09 02:02:27) |
| `claimed` | behauptet | An NPC or character *says* it, the table didn't see it | The Seraph's account of Rotunas' death (2026-08-04) |
| `rumor` | Gerücht | Hearsay, legends, tavern talk | "Man sagt, im Norden …" |
| `speculation` | Vermutung | Players theorising out of or in character | "Vielleicht ist Nox der Verräter?" |

**Conflict rule (T7):** when two status facts about the same entity disagree,
`observed` beats everything else, so the disagreement is *not* a conflict;
the claim is kept as context. Two `observed` facts that disagree with no
chronological explanation go to the conflict queue as today.

### 4.5 Threads (T5 extracts, T6 emits)

A thread is anything the table is *pursuing or owes*:

| `kind` | German | Opened when … | Resolved when … |
|---|---|---|---|
| `quest` | Auftrag | someone gives the group a task, or the group sets itself a goal | it is done or explicitly dropped |
| `mystery` | Rätsel | an open question the group explicitly wonders about | it is answered |
| `promise` | Versprechen | a PC promises something to an NPC (or the reverse) | it is kept or broken |
| `debt` | Schuld | someone owes someone a favour or money | it is paid or forgiven |
| `deadline` | Frist | a time limit is named in-world ("binnen eines Jahres") | it passes or is met |

`thread_status`: `open` · `resolved` · `abandoned`.

Concept file `threads/<slug>.md` (fully deterministic, **no synthesis
call**):

```markdown
---
type: Thread
title: Evakuierung des Halblingshofs
description: Die Gruppe soll die Bewohner des Halblingshofs vor dem Angriff in Sicherheit bringen.
tags:
- threads
- quest
timestamp: '2026-08-06T00:00:00Z'
id: THREAD_EVAKUIERUNG_DES_HALBLINGSHOFS
kind: quest
thread_status: resolved
opened: S1-02-B
resolved: S1-03-B
evidence: observed
teams: [B]
involves:
- npcs/xenia_rotkam
- locations/halblingshof
sources:
- id: S1-02-B
  resource: https://www.youtube.com/watch?v=Gb-TEbCFF0M
  at: '02:10:05'
  url_at: https://www.youtube.com/watch?v=Gb-TEbCFF0M&t=7805s
---

Die Gruppe soll die Bewohner des Halblingshofs vor dem Angriff in Sicherheit bringen.

## Verlauf

- **[S1-02-B]** Session 2026-07-23 @ 02:10:05 — eröffnet: … _(beobachtet)_
- **[S1-03-B]** Session 2026-08-06 @ 01:40:12 — erledigt: … _(beobachtet)_

## Beteiligte

- [Xenia Rotkam](/npcs/xenia_rotkam.md)
- [Halblingshof](/locations/halblingshof.md)

# Belege

[S1-02-B] Session 2026-07-23 @ 02:10:05 (https://www.youtube.com/watch?v=Gb-TEbCFF0M)
[S1-03-B] Session 2026-08-06 @ 01:40:12 (https://www.youtube.com/watch?v=0HyPHao8s_k)
```

Note the `Session YYYY-MM-DD` text in every `Verlauf` and `Belege` line.
pnp-export-data's relevance gate counts sessions with the regex
`Session (\d{4}-\d{2}-\d{2})` (`02_extract.py`, `_SESSION_CITE_RE`). Keep
that exact shape or threads never reach the wiki.

**Thread identity** is minted once and then carried forward, never
re-derived from the model's wording:

1. The state pass runs **sequentially by session date**.
2. Each session's prompt lists the threads that are currently open (id,
   kind, title, last note). The model must answer with an existing
   `thread_id` or `"NEU"`.
3. Code mints `threads/<slugify(title)>` for `NEU`, adding `_2`, `_3` … on a
   collision. The fold (§5) is deterministic given the cached per-session
   outputs, so ids are stable across re-emits.
4. An unknown `thread_id` from the model is treated as `NEU` and logged.
5. Humans fix threads in `entity_rules.yaml → thread_rules:` (merge, rename,
   force status) — see T6.

### 4.6 World status (T5 extracts, T7 emits)

On persons, factions, items and locations:

```yaml
world_status:
  value: dead            # alive | dead | missing | captured | transformed | destroyed
  since: P-34            # episode id (or session date if no episode id)
  at: '02:02:27'
  evidence: observed
world_status_history:    # chronological; only when there is more than one entry
- {value: alive, since: P-01, at: '00:12:00', evidence: observed}
- {value: dead,  since: P-34, at: '02:02:27', evidence: observed}
```

- Items and locations only use `destroyed`. Validate rejects the person
  values on them.
- `current` = the last `observed` entry; if there is none, the last entry.
- Body gets a deterministic section, inserted before `# Belege`:
  `## Stand` → "Tot seit P-34 (beobachtet, 02:02:27)."

### 4.7 Attitude (T5 extracts, T7 emits)

On NPCs and factions only:

```yaml
attitude:
- toward: party          # 'party' or a characters/<slug> concept id
  value: hostile         # allied | friendly | neutral | wary | hostile
  since: S1-02-A
  at: '01:10:00'
  evidence: observed
```

The latest entry per `toward` wins. Body `## Stand` adds
"Haltung zur Gruppe: feindselig seit S1-02-A."

### 4.8 Roster (T8)

`knowledge/roster.yaml` (committed, **in-world data only**):

```yaml
# Generated by services/kb/sync_roster.py from pnp-crawl's local roster export.
# In-world facts only. No player names (see T00 D1).
characters:
- name: Lindo Laut
  concept_id: characters/lindo_laut
  team: A
  class: Fee Barde          # CharacterStint.race_class, verbatim
  since: null               # first stint date, or null
  until: null               # date the next stint of the same seat starts, or null
```

Emitted onto Character concepts as `team`, `class`, `active_since`,
`active_until`.

The player-name **blocklist** is read at runtime from pnp-crawl's gitignored
export (`PNP_ROSTER_PRIVATE` env var → JSON path). It is never committed. If
it is absent (CI), the check skips with the bundle-skip reason.

### 4.9 Rules glossary (T3)

`prompts.RULES_GLOSSARY` is a ~15-line German Daggerheart cheat sheet: HP
are *marked*, damage thresholds, Hope/Fear, Stress, Armor slots, card
"Domains" ≠ cosmological realms, Tier, Spotlight.

- Injected into the **state pass now** (T5).
- Injected into extraction only at the next budgeted re-extraction (B2), and
  into synthesis only at the next deliberate synthesis-version bump (A4 makes
  that bump independent).
- Each line must be verified against `../daggerheart-srd/` (T3 says how).

**Dice rolls are not tracked in the KB.** No consumer needs them.
`reports/rolls/*.csv` stays archival.

## 5. The state pass (T5) — mechanics

```
for session in sessions sorted by (date, session_id):
    glossary = names of live non-Event concepts (registry canonical_name + aliases, by type)
    open_threads = ledger.open_threads()          # from the fold so far
    key = sha256(STATE_PROMPT_VERSION, model, session_id, dialogue,
                 sha(glossary_text), sha(open_threads_text))[:16]
    out = cache[state/<session>/<key>.json] or call_llm(...)   # SessionState
    ledger.apply(session, out)                    # mint ids, update status
```

- **Cascade:** a change to an early session (or to the glossary) changes
  `open_threads_text` for every later session, so every later key changes.
  That is correct, because later answers depended on it, but it costs a
  re-run of the tail. `pnp state --estimate` prints how many sessions are
  uncached before you pay.
- **Glossary drift:** the glossary is built from `entity_registry.yaml`,
  which changes on every `pnp run`. To keep the cascade from firing on every
  run, **the glossary is frozen into a file**,
  `knowledge/state_glossary.yaml`, written by `pnp state --refresh-glossary`
  only. `pnp state` without that flag reads the frozen file. The file is
  committed, so its history explains every cascade.
- **Name → concept id mapping happens at emit time**, in `pnp run`, against
  the *current* resolved entities: canonical name, then aliases, then
  `slugify` match. Unmatched names are listed in
  `knowledge/conflicts/state_unmatched.md` (one line each) instead of being
  dropped silently.
- `pnp run` never calls the state model. If a session has no cached state,
  `pnp run` logs it and emits without that session's state.

**Cost estimate:**
- Per session: ~14k words of transcript ≈ 20k input tokens, plus ~6k glossary
  and threads, plus ~2k output.
- 68 sessions ≈ 1.8M input + 0.15M output on `deepseek-v4-pro`
  ≈ $1.2 + $0.3 off-peak.
- The glossary block is a stable prefix, so the provider cache cuts the
  input side further.
- Budget **$2–4** to include a retry.

## 6. Decisions (defaults — change them in review, not in code)

| # | Decision | Default | Alternative |
|---|---|---|---|
| D1 | Real player names in the bundle? | **No.** Characters get `team` and `class`; the player-name list stays local for the blocklist only | Add a `player:` pseudonym key from `people.py` keys |
| D2 | Keep the 305 Event concepts? | **No.** Allowlisted arcs only; the rest become session anchors (T4). A one-time prune of ~280 files with `--allow-prune` and an audit note | Keep all, just hide them from indexes |
| D3 | Thread bodies synthesized by an LLM? | **No.** Deterministic `Verlauf` list. Cheaper, verifiable, no cache churn | A flash-model synthesis for threads with ≥3 entries |
| D4 | Where does the state pass run? | Its own subcommand `pnp state`; `pnp run` only reads its cache | Inside `pnp run` |
| D5 | Model for the state pass | `deepseek-v4-pro` (judgement-heavy, ~$2) | flash: ~3× cheaper, untested |
| D6 | Attitude `toward` granularity | `party` plus individual PCs | `party` only |

## 7. Rollout and acceptance

| Plan | Acceptance (measured, written into the PR) |
|---|---|
| T1 | 0 positional source ids; every entity source has `at`; `url_at` opens the VOD at the right second (spot-check 3) |
| T2 | Every concept cited by ≥1 teamed session has `teams`; spot-check 5 |
| T3 | Glossary lines each cite an SRD file; GM reviewed |
| T4 | Event concepts ≤ allowlist size; 0 dangling links; session notes carry `# Ereignisse`; the wiki-mapped event survives |
| T5 | `pnp state --estimate` works offline; one paid run (HUMAN) fills the cache; ledger report shows thread count, unmatched names |
| T6 | `threads/` emitted; validate green; API `/concepts?type=Thread` lists them; 10 threads spot-checked against transcript |
| T7 | Rotunas has `world_status: dead`, evidence observed, since the 2026-04-09 episode; the 2026-08-04 retelling appears in `world_status_history` labelled *behauptet* and never overrides the observed entry |
| T8 | 0 player names in names, aliases or prose (validate, local); Characters carry team and class |
| T9 | `summary.py` prints an "Offene Fäden" list sourced from Thread concepts |

## 8. What this deliberately does not do

- No re-extraction and no change to `EXTRACT_SYSTEM` (B2).
- No opaque ids (B1). Thread ids are minted-once, which gives the same
  property for threads only.
- No dice tracking.
- No wiki pages for threads. pnp-export-data picks them up through its
  existing type list only once `Thread` is added to `EXPORT_TYPES` and
  `CATEGORY_BY_TYPE` there. That is a separate export-data plan (E7) after
  T6.
