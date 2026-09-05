# pnp-knowledge

**A knowledge base for contested, multi-source narrative data.** 868 entity
concepts extracted from 64 sessions of recorded German speech, held as markdown
in git, with quality gates that are not allowed to silently regress.

```
Part of a three-repo pipeline:  pnp-crawl (private) → pnp-knowledge → pnp-export-data
                                 audio → transcript    transcript → knowledge    knowledge → wiki
```

The source material is a long-running tabletop campaign, which makes it an
unusually hard instance of an ordinary problem: many hours of unstructured
speech, dozens of speakers, entities that change name mid-story, facts that
contradict each other across sessions, and a human authority whose corrections
must outrank the model's output permanently.

---

## What makes this more than an ingestion script

**The knowledge base is markdown in git, not a database.** Git supplies the
temporal model for free: one commit per ingested session, a `s<NN>` tag per
session, "what did we know at session 25" is a read at that tag, and "what
changed since" is a diff. Corrections are made by editing a file, which the game
master can do without learning a query language — the requirement that decided
the architecture. See [ADR-001](docs/architecture/ADR-001-knowledge-layer.md) for
the decision and the three rejected alternatives, including Neo4j GraphRAG,
which was technically the strongest option and lost on exactly that point.

**Quality is ratcheted, not asserted.** 15 measured baselines — unlinked
mentions, uncited concepts, faction/NPC link coverage, dead rules — are recorded
and may not grow. They are not pass/fail correctness checks; several are
deliberately not zero, because forcing them to zero would over-link generic
language or paper over a detector's false positives. One baseline was
consciously loosened once, with the reason written down. See
[QUALITY.md](docs/QUALITY.md).

**Identity is guarded against the model.** Concept ids are derived from
extracted entity names, which couples identity to model output: a resample that
rewords a name moves the file. That has caused two production incidents. The
system now refuses to write when more than 10% of known concepts go missing in a
single run — a guard that fired for real in September 2026, on 432 of 868
concepts, and wrote nothing. See
[INCIDENT-2026-08-mass-rename.md](docs/architecture/INCIDENT-2026-08-mass-rename.md).

**Downstream cannot hallucinate.** The API serves already-synthesised, cited
markdown, so the wiki publishing stage has no LLM at all. Re-runs cost nothing,
are deterministic, and are trivially testable. Removing the model from that stage
was a deliberate decision, not an omission —
[ADR-003](docs/architecture/ADR-003-no-llm-downstream.md).

---

## The corpus

| | |
|---|---|
| Entity concepts | 868 |
| Sessions ingested | 64 |
| Entity types | 8 (Character, Deity, Domain, Event, Faction, Item, Location, NPC) |
| Largest types | 247 events, 219 NPCs, 146 items, 146 locations |
| Open conflicts | tracked as first-class artifacts in `knowledge/conflicts/` |
| Tests | 46 files in `services/kb` alone |

Reproduce the counts:

```bash
for d in knowledge/bundle/splitter_des_ewigen/*/; do
  printf "%-12s %s\n" "$(basename "$d")" \
    "$(find "$d" -maxdepth 1 -name '*.md' ! -name 'index.md' | wc -l)"
done
```

---

## Stage 1 is private by design

**`pnp-crawl` is not published.** The session recordings themselves are public,
but the pipeline derives speaker voice embeddings — biometric templates tied to
named individuals (GDPR Art. 9) — plus the local roster mapping people to
characters and sessions. Deriving that data from public audio does not make it
public, so the stage that holds it stays private. Its architecture is summarised
in [docs/PIPELINE.md](docs/PIPELINE.md).

---

## Layout

```
├── knowledge/            ★ SYSTEM OF RECORD — the OKF campaign bundle
│   ├── bundle/splitter_des_ewigen/   one markdown concept per entity
│   ├── conflicts/                    open cross-source contradictions
│   └── sources/                      campaign book + ingested custom docs
│
├── services/             ACTIVE code (each its own venv)
│   ├── kb/               OKF pipeline (transcripts → bundle) + read-only API
│   ├── summary/          pre-session recap / outlook, grounded in the KB API
│   └── dashboard/        local status view across all three repos
│
├── reports/              session reports (.md) + rolls/ CSVs — shared data
│
├── docs/architecture/    ADRs, ARCHITECTURE, incident postmortems
│
└── graph/                ❄ FROZEN GraphRAG (Neo4j) — reference + future
                            derived index only, no active development
```

`knowledge/` + `services/` are live; `graph/` is frozen and deliberately
excluded from CI. It is kept because ADR-001 names it as the fallback path and
the future derived index — see [ADR-002](docs/architecture/ADR-002-repo-layout.md)
for why it was frozen rather than deleted.

## Quick start

```bash
# KB read API (serves the bundle to the wiki + summary services)
cd services/kb && python -m pnp_okf.api      # 127.0.0.1:8070

# Pre-session recap
cd services/summary && python summary.py

# Rebuild the bundle from transcripts (DeepSeek; see services/kb/README.md)
cd services/kb && pnp run --transcripts <dir> --bundle ../../knowledge/bundle/splitter_des_ewigen
```

Tests: `services/kb` and `services/summary` each `python -m pytest`.

## Documentation

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | System, containers, API contracts, ingestion, sequence diagrams |
| [ADR-001](docs/architecture/ADR-001-knowledge-layer.md) | OKF-in-git as system of record; why not a graph database |
| [ADR-002](docs/architecture/ADR-002-repo-layout.md) | Active/frozen split and the repo rename |
| [ADR-003](docs/architecture/ADR-003-no-llm-downstream.md) | No LLM downstream of the knowledge base |
| [QUALITY.md](docs/QUALITY.md) | The 15 quality ratchets and their baselines |
| [INCIDENT-2026-08](docs/architecture/INCIDENT-2026-08-mass-rename.md) | The mass-rename incidents and the guards written in response |
| [docs/audits/](docs/audits/) | Bundle quality audits — the documents the ratchets came from |

## License

MIT, covering the code under `services/`. The campaign content under
`knowledge/` — in particular `knowledge/sources/`, which contains third-party
material — is not covered and is not the author's to relicense.

---

<sub>Formerly `pnp-graph-service`. The GraphRAG pipeline that named it is frozen
under `graph/`; see ADR-002.</sub>
