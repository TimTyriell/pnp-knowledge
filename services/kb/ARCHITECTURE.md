# Der Splitter des Ewigen — Architecture

## Overview

`pnp-okf` distills ~42 diarized German Daggerheart actual-play transcripts
(session `.json` files) into an **Open Knowledge Format (OKF)** campaign wiki:
a git-versioned, cross-linked bundle of markdown concepts (characters, NPCs,
locations, factions, items, per-session recaps) plus an interactive `viz.html`
graph.

**Core principle:** raw transcripts are *sources*, not knowledge. They are never
stored as concepts; every fact in a concept is **cited** back to the session
YouTube URL and a `[HH:MM:SS]` timestamp.

The pipeline is a batch **map → reduce → synthesize** ETL job that calls
the **DeepSeek API** with structured (schema-constrained) outputs. OKF emission and
visualization reuse the `okf` reference package from the `knowledge-catalog` repo.

---

## Pipeline diagram

```plantuml
@startuml
!theme plain
title Der Splitter des Ewigen — Transcript → OKF Pipeline

skinparam componentStyle rectangle
skinparam defaultTextAlignment center
skinparam ArrowColor #555555

actor "Campaign Curator" as User

package "Inputs" {
  database "Transcripts\n(*.json — diarized\nsegments + video meta)" as TX
  file "entity_registry.yaml\n(alias -> canonical)\n[human-editable]" as REG
}

cloud "DeepSeek" {
  [DeepSeek API\nchat completions\n(structured outputs / JSON schema)] as AOAI
}

package "pnp-okf pipeline (src/pnp_okf/)" {
  [ingest.py\nload segments + meta\n→ SessionTranscript] as INGEST
  [extract.py\nper-session recap +\nentity mentions w/ [ts]] as EXTRACT
  database ".cache/extract/\n(keyed by session + prompt ver.)" as CACHE_E
  database ".cache/synth/\n(keyed by entity + inputs)" as CACHE_S
  [resolve.py\nalias clustering\n→ CanonicalEntity list] as RESOLVE
  [synthesize.py\nOKF body per entity\n(German, structural MD)] as SYNTH
  [emit.py\nwrite .md concepts\ncross-links, indexes, log] as EMIT
}

package "okf reference package (reused)" {
  [okf.py (internal)\nOKFDocument writer\nindex.md generator] as OKFW
  [reference_agent visualize CLI\n→ viz.html] as VIZGEN
}

folder "OKF Bundle (output)" {
  file "sessions/        characters/\nnpcs/          locations/\nfactions/      items/\nindex.md       log.md" as BUNDLE
  file "viz.html" as HTML
}

User --> REG : curate alias merges
TX --> INGEST
INGEST --> EXTRACT : SessionTranscript
EXTRACT <--> CACHE_E : read / write
EXTRACT <--> AOAI : transcript chunks\n→ SessionExtraction (JSON schema)
EXTRACT --> RESOLVE : dict[session → extraction]
REG --> RESOLVE : alias overrides
RESOLVE --> SYNTH : CanonicalEntity list
SYNTH <--> CACHE_S : read / write
SYNTH <--> AOAI : entity mentions\n→ German wiki body
SYNTH --> EMIT : (entity, body) pairs
EMIT ..> OKFW : write frontmatter + body\nregenerate indexes
EMIT --> BUNDLE
BUNDLE --> VIZGEN
VIZGEN ..> OKFW
VIZGEN --> HTML

@enduml
```

---

## Stage detail

| Stage | Module | Input | DeepSeek? | Output | Idempotent? |
|-------|--------|-------|:------:|--------|:-----------:|
| 1 · Ingest | `ingest.py` | `*.json` | no | `SessionTranscript` objects | pure |
| 2 · Extract | `extract.py` | one session | **yes** (JSON schema) | recap + entity mentions w/ `[ts]` | cache by `(session, chunk, prompt_ver)` |
| 3 · Resolve | `resolve.py` | all extractions + registry | no | `CanonicalEntity` list | deterministic + registry editable |
| 4 · Synthesize | `synthesize.py` | canonical entity + mentions | **yes** (free text) | German markdown body | cache by `(entity, inputs_hash)` |
| 5 · Emit | `emit.py` | entities + bodies | no | `.md` concepts, `index.md`, `log.md` | deterministic |
| 6 · Visualize | `okf` CLI | bundle dir | no | `viz.html` | deterministic |

---

## Concept model (OKF v0.1)

```
splitter_des_ewigen/          (bundle root)
├── index.md                  # directory overview  (no frontmatter)
├── log.md                    # newest-first per-session changelog
├── sessions/                 # type: Session  resource: youtube-url
│   ├── index.md
│   ├── 2025-03-26.md
│   └── …
├── characters/               # type: Character  (PCs)
├── npcs/                     # type: NPC
├── locations/                # type: Location
├── factions/                 # type: Faction
├── items/                    # type: Item
└── events/                   # type: Event  (major in-world events)
```

Every concept:
- YAML frontmatter: required `type`; recommended `title`, `description`,
  `resource`, `tags`, `timestamp` (ISO 8601).
- Cross-links use bundle-relative paths (`/characters/lindo_laut.md`).
- Externally sourced claims listed under `# Belege` (Citations), citing
  `[Session YYYY-MM-DD @ HH:MM:SS](<youtube-url>)`.

---

## DeepSeek configuration

All settings are environment-driven. Copy `.env.example` → `.env`:

| Variable | Purpose |
|----------|---------|
| `DEEPSEEK_API_KEY` | Required; API-key auth (DeepSeek has no keyless auth option) |
| `DEEPSEEK_BASE_URL` | Defaults to `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | Defaults to `deepseek-chat` |

Same pattern as `pnp-graph-service`'s `flagship` profile (see its
`CLAUDE.md`): `extract.py` first tries strict `json_schema` structured
output (`beta.chat.completions.parse`) and falls back to a JSON-object
prompt if DeepSeek's endpoint rejects it — DeepSeek's structured-output
support is less reliable than OpenAI's/Azure's.

---

## Entity registry (`entity_registry.yaml`)

Generated by `pnp run` / `pnp extract`, then human-editable:

```yaml
# Add entries here to fold a variant / Whisper-garbled name into an
# existing canonical concept:
merge:
  "bade":          characters/lindo_laut     # "Bade" → Blade (Whisper error)
  "lindo":         characters/lindo_laut
  "sifaf":         characters/seraph_name    # Seraph class name misheard

entities:                                    # regenerated — do not edit below
  - concept_id: characters/lindo_laut
    canonical_name: Lindo Laut
    aliases: [Lindo, Barde]
    mention_count: 12
```

---

## Non-goals

- No publishing to Knowledge Catalog / Dataplex (out of scope for this project).
- No English output (German only, matching the transcripts).
- No real-time / per-episode automation (batch ETL only).
