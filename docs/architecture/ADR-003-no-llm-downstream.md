# ADR-003: No LLM downstream of the knowledge base — publishing is deterministic

**Status:** Accepted
**Date:** 2026-09-05
**Deciders:** Noah + Claude (architecture session)
**Relates to:** [ADR-001](ADR-001-knowledge-layer.md) (the bundle is the system
of record), [ADR-002](ADR-002-repo-layout.md) (repo layout)

## Context

The toolchain is three repos in a line: `pnp-crawl` (transcription) →
`pnp-knowledge` (this repo, the memory) → `pnp-export-data` (the wiki output).
Exactly one of those stages calls a language model on the campaign's content:
the `pnp_okf` pipeline in `services/kb`, which extracts entities from
transcripts and synthesizes each concept's German body with DeepSeek.

That places a natural boundary. What leaves the KB is not raw evidence needing
interpretation — it is **already-synthesised, structured, cited German
markdown**: ATX headings, bold, bullet lists, markdown links between concepts,
and a `# Belege` citation list where every claim traces back to
`Session YYYY-MM-DD @ HH:MM:SS` plus a URL. The synthesis decisions, the tier
choice, the conflict handling and the human review gate (ADR-001: knowledge
changes arrive as reviewed `ingest/s<NN>` PRs) have all already happened
upstream of the API.

The question this ADR settles is what the *consumers* of that API are allowed
to be. The wiki agent's job is a format change: markdown → MediaWiki wikitext,
concept links → `[[Page]]` links, `[P-08]` citation markers → links to that
episode's own wiki page. It is tempting to reach for a model there anyway —
the pipeline talks to an LLM one stage earlier, an Ollama host is already
configured, and "polish the German a bit" is one prompt away.

Two properties of the downstream stages make that temptation expensive:

- **They run against a live, hand-curated wiki.** The pages carry infoboxes,
  images, human prose and categories. Publishing is an additive section merge
  (`wikimerge.py`), never a replace, and a human reviews every `.diff` before
  `04_upload.py --apply` with `FANDOM_DRY_RUN=0`. A reviewer can only usefully
  approve a diff whose provenance they can reason about.
- **They are re-run constantly.** Every stage is idempotent and re-running after
  a new session is the normal workflow. A per-run token cost would be paid over
  and over for output that is, by construction, supposed to be identical.

## Decision

**No LLM exists downstream of the knowledge base.** The KB API is the last
component in the toolchain that calls a model. Everything after it —
inventory, planning, wikitext generation, upload — is deterministic code.

1. **Conversion is a pure function.** `pnp-export-data/md2wiki.py` maps the exact
   markdown the KB emits (headings, bold/italic, bullets, concept links,
   citation markers) to wikitext; anything unrecognised passes through
   unchanged. Its own module docstring states the reason: *"no LLM is needed (or
   wanted) to turn them into wiki pages: a deterministic conversion cannot
   hallucinate, is free, and is trivially testable."*
2. **Composition is a committed data file, not a judgement call.** Which
   concepts land on which wiki page is `wiki_pages.toml` plus `pagemap.py` —
   a `lead` owns a page's identity, a `sub` appears as a section on it. Only
   exceptions are listed; an unmapped concept keeps the 1:1 path and passes
   through byte-identically. Presentation merges live *there* and never in
   `knowledge/` (ADR-001: entities are not pages).
3. **A re-run costs no tokens, only HTTP.** Those round trips are kept down
   deterministically too: stage 2 caches the concept bodies its API call already
   returned into `wiki_cache/bodies.json` for stage 3 to read; stage 3 reads live
   pages through `WikiClient.read_many` in batches of 50 rather than one request
   per page; stage 4 skips any proposal whose `.diff` is empty, because that
   edit would be a `nochange` round trip plus the edit delay. (A *missing*
   `.diff` still uploads — absence is not proof a page is unchanged.)
4. **Ollama config stays, unused.** `pnp-export-data/config.py` retains Ollama
   host/model settings for a possible future prose-polish pass. Keeping the
   configuration is free; adding an OpenAI/Anthropic dependency to that repo is
   an explicit decision, not a default.

## Alternatives considered

- **LLM prose-polish at publish time.** Run each converted page through a model
  to smooth the German, vary sentence structure, and tighten the synthesis
  before it hits the wiki. Rejected on three counts. (a) It reintroduces
  hallucination risk at the one stage where nothing verifies output any more —
  the KB's citations are attached to *specific sentences*, so a rewrite can
  silently decouple a claim from the evidence line that still sits under it, and
  no test in either repo can detect that. (b) It destroys the review gate's
  meaning: a reviewer reading an additions-only `.diff` currently knows that
  every added word came from a cited KB body, and a polish pass replaces that
  guarantee with "a model probably preserved the meaning". (c) It makes the
  pipeline non-idempotent — two runs over an unchanged bundle produce two
  different wikitexts, so stage 4's empty-diff skip stops firing and every
  re-sync becomes a real edit on a live wiki plus a token bill. If the German
  reads badly, the fix belongs in `prompts.py` upstream, where the output is
  cached, reviewed as a knowledge diff, and cited.

- **LLM-driven page composition / section selection.** Let a model decide which
  concepts belong together on a page, which sections to include, and how to
  order them — instead of maintaining `wiki_pages.toml` by hand. Rejected
  because composition is not a language problem, it is an identity problem, and
  identity is exactly what this toolchain has spent its effort making
  deterministic and auditable (ADR-001 §2: port the identity discipline, resolve
  deterministically before write). A model choosing groupings would re-decide
  them per run: a page that gathered four concepts last week gathers three this
  week, the fourth silently loses its home, and nothing tells anyone — the same
  failure class the mass-rename and prune guards exist upstream to prevent. It
  also relocates a knowledge-shaped decision into the output repo, where it
  cannot be reviewed as a knowledge diff. The committed TOML is diffable, has a
  comment beside each exception, and is wrong in the same way every run until
  someone fixes it — which is the desirable failure mode.

- **A read-only "explain this page" model in the wiki agent** (answer questions
  about a proposal rather than write it). Rejected as YAGNI, not as wrong: it
  changes no output and would be additive later. The KB API already serves the
  underlying bodies for anyone who wants to inspect provenance.

## Consequences

- **Positive:**
  - Re-running the whole publish pipeline is free and safe, so it is run often —
    which is what keeps `wiki_cache/` fresh and the create-vs-update verdict
    correct.
  - The wiki agent is fully offline-testable (`test_export.py` covers the
    converter, planning and proposal cores with no network and no model), which
    is not achievable for an LLM stage.
  - A wikitext diff is reviewable as a *mechanical* consequence of a knowledge
    diff. Everything visible on the wiki traces to a cited concept body, which
    traces to a session and timestamp.
  - The hallucination surface of the entire toolchain is one stage wide. It is
    guarded there by the measured baselines in [QUALITY.md](../QUALITY.md) and
    the conflict queue, rather than being spread thin across three repos.
- **Negative / mitigations:**
  - Output prose reads as synthesised, with no publication polish. Mitigation:
    improve it upstream in `prompts.py`, where the change is cached, versioned
    (`PROMPT_VERSION`) and reviewed.
  - `md2wiki.py` only handles the markdown subset the KB emits. A new construct
    in synthesis output passes through unconverted instead of being adapted
    intelligently. Mitigation: the subset is small, stable and pinned by tests;
    an unknown construct is visible in the `.diff`, which a human reads anyway.
  - `wiki_pages.toml` is hand-maintained and grows with the campaign.
    Mitigation: it lists only exceptions, so its size tracks genuinely merged
    pages, not concept count.

## Revisit trigger (any one of these reopens the decision)

1. `wiki_pages.toml` maintenance becomes the bottleneck on publishing — enough
   new merge decisions per session that a human cannot keep up. (Note the
   cheaper answer first: a deterministic *proposal* tool that suggests merge
   candidates for human approval, the same propose-never-write shape
   `dedup.py` already uses upstream.)
2. The wiki gains a consumer that needs genuinely generated text with no KB
   source — a hand-written "in-world" intro, a summary of several pages — that
   cannot be traced to a cited concept. That content should still be authored
   upstream as a `knowledge/sources/` document, so this trigger fires only if
   that route proves impractical.
3. `md2wiki.py`'s pass-through becomes a real defect source: unconverted
   constructs appear in reviewed diffs often enough that maintaining the mapping
   costs more than an LLM conversion stage would — including its token bill,
   its non-idempotence, and the review guarantee it forfeits.
4. Prompt-level fixes stop being able to reach a prose problem that only shows
   up in the published form (e.g. wiki-specific length or layout constraints
   that synthesis cannot know about).
