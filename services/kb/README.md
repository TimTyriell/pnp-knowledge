# pnp-okf

Distill Pen & Paper actual-play transcripts into an [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) campaign bundle using the DeepSeek API.

**Campaign:** *Der Splitter des Ewigen* — a German Daggerheart actual-play series.  
**Input:** 42 diarized JSON transcripts (~647 K words).  
**Output:** A git-versioned campaign wiki (characters, NPCs, locations, factions, items, per-session recaps) + interactive `viz.html` graph.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full pipeline diagram.

Since the 2026-07-22 monorepo move this lives in
`pnp-graph-service/services/kb`; the canonical bundle is
`../../knowledge/bundle/splitter_des_ewigen` and the system-level docs are in
`../../docs/architecture/`. A **read-only HTTP API** over the bundle ships as
`python -m pnp_okf.api` (127.0.0.1:8070): `/concepts` (typed-ID or path
lookup, `?as_of=<session-tag>` for historic reads), `/changes?since=<ref>`,
`/conflicts`, `/health`.

---

## Quick start

### 1. Prerequisites

- Python 3.11+
- A [DeepSeek](https://platform.deepseek.com/) API key (`deepseek-chat` recommended)
- The `okf` reference package on your `$PATH` or venv for `viz.html` generation  
  (optional; only needed for `pnp visualize`)

### 2. Install

```bash
git clone <this repo>
cd pnp-okf

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your DEEPSEEK_API_KEY (DEEPSEEK_BASE_URL/DEEPSEEK_MODEL have
# working defaults)
```

### 4. Verify setup (no DeepSeek calls)

```bash
pnp check --transcripts /path/to/transcripts
```

### 5. PoC run — 3 sessions, end to end

```bash
pnp run \
  --transcripts /path/to/transcripts \
  --bundle ./bundle/splitter_des_ewigen \
  --limit 3
```

First run calls DeepSeek for each session + entity; subsequent runs hit the cache
in `.cache/` and are instant. Review the entity registry and add alias merges
for any Whisper recognition errors:

```bash
vim ./bundle/entity_registry.yaml   # add merge: entries
pnp run --transcripts /path --bundle ./bundle/splitter_des_ewigen --limit 3 --force
```

### 6. Full campaign

```bash
pnp run \
  --transcripts /path/to/transcripts \
  --bundle ./bundle/splitter_des_ewigen
```

### 7. Generate viz.html

Requires the `okf` reference package installed in the same venv:

```bash
pip install -e /path/to/knowledge-catalog/okf
pnp visualize --bundle ./bundle/splitter_des_ewigen
# or, explicitly via python -m:
pnp visualize --bundle ./bundle/splitter_des_ewigen --python-module
```

---

## CLI reference

```
pnp check       Verify config + count transcripts (no LLM calls)
pnp run         Full pipeline: ingest → extract → resolve → synthesize → emit
pnp extract     Extraction stage only (populate the cache)
pnp visualize   Generate viz.html by calling the okf reference CLI
```

Common flags (where applicable):

| Flag | Default | Description |
|------|---------|-------------|
| `--transcripts DIR` | `$PNP_TRANSCRIPT_DIR` or `./transcript` | Transcript JSON directory |
| `--bundle DIR` | `$PNP_BUNDLE_DIR` or `./bundle/splitter_des_ewigen` | Output bundle |
| `--cache DIR` | `$PNP_CACHE_DIR` or `./.cache` | LLM response cache |
| `--limit N` | all | Process only the first N sessions |
| `--session ID` | all | Restrict to a specific session id/date (repeatable) |
| `--force` | off | Ignore cache and re-call DeepSeek |
| `--clean` | off | Delete the bundle dir before writing (`run` only) |
| `-v` | off | Debug logging |

---

## Project layout

```
pnp-okf/
├── src/pnp_okf/
│   ├── cli.py           # CLI entry point (pnp command)
│   ├── config.py        # DeepSeek + path settings (env-driven)
│   ├── models.py        # Pydantic domain models
│   ├── ingest.py        # Stage 1: load transcript JSON
│   ├── extract.py       # Stage 2: map (DeepSeek structured output, cached)
│   ├── resolve.py       # Stage 3: entity resolution + registry
│   ├── synthesize.py    # Stage 4: concept body synthesis (DeepSeek, cached)
│   ├── emit.py          # Stage 5: write OKF .md bundle
│   ├── okf.py           # OKF writer helpers (no external deps)
│   ├── llm_client.py    # DeepSeek OpenAI-compatible client factory
│   └── prompts.py       # German system/user prompts (bump PROMPT_VERSION to invalidate cache)
├── tests/
├── ARCHITECTURE.md      # Full pipeline diagram (PlantUML)
├── .env.example
└── pyproject.toml
```

---

## Development

```bash
pytest              # offline tests (no DeepSeek required)
```

Prompts live in `src/pnp_okf/prompts.py`. Bump `PROMPT_VERSION` whenever you
change a prompt — this invalidates the cache automatically so stale responses
are never reused.
