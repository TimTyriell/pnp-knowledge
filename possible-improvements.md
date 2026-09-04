# Possible improvements

External repos/tools evaluated for this pipeline (Sep 2026). See sibling files in `pnp-crawl/` and `pnp-export-data/` for their own lists.

## Add now

### [instructor](https://github.com/567-labs/instructor)
Applies to: `services/kb` pipeline

Pydantic-typed structured outputs for LLM calls — validation and retry built in, works against DeepSeek/Ollama already in use per `PNP_PROFILE`.

- **Pros:** typed entity extraction (CHAR_/NPC_/LOC_/…) becomes a Pydantic model instead of hand-parsed JSON; automatic retry-on-validation-failure means fewer malformed OKF frontmatter blocks from a flaky LLM pass; 11k★, provider-agnostic, no vendor lock-in.
- **Cons:** another abstraction layer over calls that may already work fine unvalidated; retry loops cost extra tokens/latency on a pipeline that's presumably already tuned.

### [dedupe](https://github.com/dedupeio/dedupe)
Applies to: entity resolution (see `knowledge/conflicts/`)

Active-learning fuzzy matcher for record deduplication — relevant the moment two sessions mention "der alte Wirt" and "Wirt Hallgrim" and the pipeline has to decide if that's one `NPC_`.

- **Pros:** directly targets the entity-resolution problem already visible in `knowledge/conflicts/` — not speculative; active-learning loop generalizes from a few dozen corrections instead of hand-tuned fuzzy thresholds.
- **Cons:** needs labeled training pairs before it beats an LLM-based dedupe pass (cold-start cost); German names/diacritics need testing since matcher defaults are tuned on English-ish records.

## Worth a look, not urgent

- **[neo4j/neo4j-graphrag-python](https://github.com/neo4j/neo4j-graphrag-python)** — official first-party GraphRAG library (schema-guided extraction, retriever abstractions). `graph/` is frozen per ADR-002, but if it's ever revived as a derived index this is the maintained alternative to the current ad hoc `pnp_graph` package. *Trigger: ADR-002 freeze lifted, or graph/ picked back up as a derived index.*
- **[catancs/okf-skill](https://github.com/catancs/okf-skill)** — validate/query/lint/create toolkit for OKF bundles specifically, aimed at coding agents. Same OKF format `knowledge/` uses. *Trigger: hand-rolled OKF validation in services/kb starts drifting from spec, or you want agent-side OKF linting in CI.*
- **[worldbank/FuzzyAI](https://github.com/worldbank/FuzzyAI)** — entity dedup with an LLM-based consolidation step on top of fuzzy candidate generation, a middle ground between dedupe's active learning and a pure LLM merge pass. *Trigger: dedupe's active-learning cold start proves too slow, or German-name matching underperforms.*
- **[GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format)** — upstream OKF spec repo, sibling to the already-vendored `knowledge-catalog`. Worth diffing periodically since `knowledge-catalog` is read-only and could drift from canonical. *Trigger: quarterly spec-drift check, or a services/kb ingest bug traces to a spec edge case.*
- **[SachinMishra-ux/Open_Knowledge_Format (google-okf)](https://github.com/SachinMishra-ux/Open_Knowledge_Format)** — production-grade OKF connector library, auto-converts enterprise data sources into OKF bundles. Overlaps with what services/kb's ingest pipeline does by hand. *Trigger: adding a second knowledge source beyond session reports (rules PDFs, wiki exports) needing its own OKF connector.*
- **[AntTheLimey/gm-apprentice](https://github.com/AntTheLimey/gm-apprentice)** — Claude skill set for TTRPG GMs; `vault-ingest` turns old notes/transcripts into a structured vault by interviewing the GM, `campaign-organizer` builds YAML-frontmatter markdown + wiki-links, close to what services/kb already does with OKF. *Trigger: needing a human-in-the-loop recovery pass for pre-pnp-knowledge sessions with thin reports.*

## Evaluated, passed on

| Repo | Category | Why not |
|---|---|---|
| neo4j-labs/llm-graph-builder | GraphRAG UI | Full webapp + Neo4j-hosted product, mismatched to a frozen local pipeline |
| neo4j-product-examples/graphrag-contract-review | GraphRAG demo | Domain (legal contracts) has nothing to reuse for campaign data |
| neo4j-product-examples/neo4j-gnn-llm-example | GNN+LLM demo | Research demo, not a library — nothing to depend on |
| VectifyAI/OpenKB | Knowledge base CLI | Different "KB" — general doc wiki-builder, not the OKF format already standardized on |
| AgriciDaniel/claude-obsidian | PKM skill | Targets Obsidian vaults; this repo already has its own OKF+API stack, would be a parallel system |
| jykim/claude-obsidian-skills | PKM skill | Same reason — Obsidian-specific, redundant with OKF bundle |
| pablo-mano/Obsidian-CLI-skill | PKM skill | Same reason |
| dclasair/ttrpg-campaign-vault | Obsidian template | Vault template, not tooling — nothing to integrate |
| mcpmarket "D&D Dungeon Master" skill | Live-play skill | Runs sessions; this toolchain only processes recordings after the fact |
| mcpmarket "rpg-session-summarizer" skill | Summarization skill | Overlaps services/summary — redundant with an already-built in-house service |
| mcpmarket "ttrpg-session-prep" skill | Prep skill | Forward-looking session prep, not backward-looking archival — off-mission for this toolchain |
| skills.rest "rpg-tools" | Solo-play toolkit | Dice/oracle tools for solo play, unrelated to transcript→KB→wiki flow |
| Xeeshanmalik/Entity-Resolution | Entity resolution | Sparse/unmaintained compared to dedupe |

---
Full cross-repo report: see the artifact published 2026-09-05 (link in chat history) for context spanning all three repos.
