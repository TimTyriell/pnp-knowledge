# T1 — Timestamped sources and a complete episode list

| | |
|---|---|
| Branch | `feat/source-timestamps` |
| Base | `origin/main` |
| Depends on | **pnp-crawl plan C3** (`sync_episodes.py` run + human Abenteuernamen) for the *data* half. The *code* half below has no dependency, so it can be merged first |
| Design | [T00 §4.1](T00-tracking-model.md) |
| Cost | $0 for code. ~$0.05 warm re-emit, **HUMAN RUN** |
| Size | S |

## Goal

1. Every entity `sources[]` entry carries `at` (HH:MM:SS) and `url_at` (VOD
   link that starts at that second).
2. A validation counter `positional_source_ids` reports concepts whose
   `sources[].id` values are positional (`'1'`, `'2'`, …). A ratchet test pins
   it, and it must hit 0 after episodes.yaml is complete.
3. After the human completes episodes.yaml and re-emits, 0 positional ids.

## Why

- Today a claim's timestamp lives only in the prose `# Belege` list, so
  checking a fact means scrolling a 3-hour VOD.
- About 170 concepts fall back to positional ids because 8 sessions
  (2026-08-12, 08-18, 08-20, 08-25, 09-01, 09-03, 09-08, 09-22) are missing
  from `knowledge/episodes.yaml`. The missing video ids are `piUv11DCwDw`,
  `10swvSz6k7U`, `1Cjj3OVqiYA`, `1E3-Nwv4OEs`, `2EkWrNUfQi0`, `EswuiEiZZEc`,
  `bl-hX87_EC8` and `zXVsTYYR8M4`.
- The same gap would put 8 raw YouTube titles onto the wiki as page titles
  when the wiki is next synced.

## Steps

### 1. Branch

```bash
cd pnp-knowledge
git fetch origin && git switch -c feat/source-timestamps origin/main
```

### 2. Add `at` / `url_at` in `services/kb/src/pnp_okf/emit.py`

At the top of `emit.py`, next to the other `pnp_okf` imports, add:

```python
from pnp_okf.context import _parse_ts
```

`_parse_ts` already exists in `context.py` and returns seconds or `None`.
Reuse it; don't write a second parser.

Add this helper directly above `def _source_entries`:

```python
def _url_at(url: str, seconds: float) -> str:
    """``url`` opened at ``seconds`` -- YouTube honours ``t=<n>s``.

    The VOD link alone makes a reader scrub a three-hour stream for the one
    line a claim rests on; the timestamp is already known per mention.
    """

    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(seconds)}s"
```

In `_source_entries`, inside the `for sid, m in zip(...)` loop, after `entry`
is built and **before** the `if m.date:` block, add:

```python
        seconds = _parse_ts(m.citation_ts)
        if seconds is not None:
            entry["at"] = m.citation_ts.strip()
            if m.url:
                entry["url_at"] = _url_at(m.url, seconds)
```

Key order in the YAML then is `id, resource, at, url_at, last_modified`.
That is fine; nothing parses by position.

Extend the `_source_entries` docstring with one sentence:
"`at`/`url_at` (T1) carry the mention's citation timestamp so every source
opens at the moment it cites."

Don't touch `emit_sessions`. A Session's own source is the whole VOD and has
no single timestamp.

### 3. Validation counter in `services/kb/src/pnp_okf/validate.py`

1. In `class ValidationReport`, add a field after `invalid_subtypes`:
   ```python
   positional_source_ids: list[str] = field(default_factory=list)
   ```
2. Do **not** add it to `ok` or `integrity_ok`. It is a ratchet, not a gate.
   (House rule: a new check runs clean once before it may fail a build;
   PIPELINE.md §10.)
3. In `summary()`, add one line in the same style as the other counters,
   e.g. `positional source ids: N` (find how `invalid_subtypes` is printed
   and copy that pattern).
4. In `validate_bundle`, inside the per-file loop, after the
   `subtype = …` block, add:
   ```python
        sources = fm.get("sources")
        if etype is not None and isinstance(sources, list) and sources:
            ids = [str(s.get("id", "")) for s in sources if isinstance(s, dict)]
            if ids and all(i.isdigit() for i in ids):
                report.positional_source_ids.append(cid)
   ```
   `etype is not None` excludes sessions, which use `'1'` legitimately when a
   session has no episode.

### 4. Tests

In `services/kb/tests/test_okf_v02.py`:

1. Update `test_sources_fall_back_to_positional_when_labels_is_none`. The
   expected dict becomes:
   ```python
   {
       "id": "1",
       "resource": "http://x",
       "at": "00:01:00",
       "url_at": "http://x?t=60s",
       "last_modified": "2026-01-01T00:00:00Z",
   }
   ```
2. Add these tests below `test_sources_last_modified_omitted_when_mention_date_empty`:

```python
def test_sources_carry_the_citation_timestamp(tmp_path: Path):
    source = _frontmatter(tmp_path, labels=["P-08"])["sources"][0]
    assert source["at"] == "00:01:00"
    assert source["url_at"] == "http://x?t=60s"


def test_url_at_appends_to_an_existing_query(tmp_path: Path):
    entity = _entity()
    entity.mentions[0].url = "https://www.youtube.com/watch?v=abc"
    entity.mentions[0].citation_ts = "01:46:53"
    emit_entity(tmp_path, entity, _DEFAULT_BODY, labels=["P-08"])
    doc = (tmp_path / "npcs" / "testo.md").read_text(encoding="utf-8")
    source = split_document(doc)[0]["sources"][0]
    assert source["url_at"] == "https://www.youtube.com/watch?v=abc&t=6413s"


def test_unparseable_timestamp_omits_at_and_url_at(tmp_path: Path):
    entity = _entity()
    entity.mentions[0].citation_ts = "irgendwann"
    emit_entity(tmp_path, entity, _DEFAULT_BODY, labels=["P-08"])
    doc = (tmp_path / "npcs" / "testo.md").read_text(encoding="utf-8")
    source = split_document(doc)[0]["sources"][0]
    assert "at" not in source and "url_at" not in source


def test_validate_counts_positional_source_ids(tmp_path: Path):
    emit_entity(tmp_path, _entity(), _DEFAULT_BODY, labels=None)
    report = validate_bundle(tmp_path)
    assert report.positional_source_ids == ["npcs/testo"]


def test_validate_ignores_keyed_source_ids(tmp_path: Path):
    emit_entity(tmp_path, _entity(), _DEFAULT_BODY, labels=["P-08"])
    assert validate_bundle(tmp_path).positional_source_ids == []
```

3. Add the ratchet in `services/kb/tests/test_bundle_invariants.py`, at the
   end of the file:

```python
# Ratchet (PIPELINE.md §10): concepts whose sources[] ids are all positional
# ("1", "2", ...) because a cited session is missing from episodes.yaml.
# Measured 2026-10-18: <N> (8 sessions from 2026-08-12 on had no episode id).
# Target 0 once pnp-crawl/sync_episodes.py --write has run; only ever lower it.
POSITIONAL_SOURCE_BASELINE = <N>


def test_positional_source_ids_only_go_down():
    from pnp_okf.validate import validate_bundle

    found = validate_bundle(BUNDLE).positional_source_ids
    assert len(found) <= POSITIONAL_SOURCE_BASELINE, (
        f"{len(found)} concept(s) cite only positional source ids (baseline "
        f"{POSITIONAL_SOURCE_BASELINE}); first few: {found[:5]}. A cited "
        f"session is missing from knowledge/episodes.yaml -- run "
        f"pnp-crawl/sync_episodes.py --write."
    )
```

   Set `<N>` by measuring. Run this from `services/kb` and put the printed
   number in **both** places:

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from pnp_okf.validate import validate_bundle; print(len(validate_bundle(Path('../../knowledge/bundle/splitter_des_ewigen')).positional_source_ids))"
```

   It should be roughly 170. If it is 0 or above 400, **STOP and report**.

### 5. Verify

```bash
cd services/kb
.venv/Scripts/python.exe -m pytest -q tests/test_okf_v02.py tests/test_bundle_invariants.py
.venv/Scripts/python.exe -m pytest -q
cd ../.. && ruff check .
```

Expect everything green except the known `last_run` test (README rule 5).

### 6. Commit and PR

Message: `feat(kb): timestamp every source and count positional source ids`

The PR body must list the HUMAN RUN steps below.

## HUMAN RUN (after merge, in this order)

1. In pnp-crawl, run plan **C3** (`python sync_episodes.py --write`), then
   fill `title:` / `description:` for the 8 new entries in
   `pnp-knowledge/knowledge/episodes.yaml` by hand. Commit on branch
   `chore/episodes-2026-08` in pnp-knowledge.
2. Re-emit:
   ```bash
   cd services/kb
   .venv/Scripts/python.exe -m pnp_okf.cli run --estimate --transcripts ../../../pnp-crawl/transcripts_final
   ```
   The estimate must show **0 uncached extraction calls** for the existing 68
   sessions. The 3 new transcripts (2026-10-06/14/16) will be uncached;
   either accept ~$0.5 for them or move them out of `transcripts_final`
   temporarily. Then run without `--estimate`.
3. Commit the bundle, set `POSITIONAL_SOURCE_BASELINE = 0` with a comment
   saying why, and open a PR.

## Done when

- [ ] Code PR merged, tests green.
- [ ] episodes.yaml has an entry for every transcript (crawl `test_episodes.py` green).
- [ ] Re-emitted bundle: `positional_source_ids == 0`, baseline set to 0.
- [ ] Spot-check: open `url_at` of 3 random entities; each lands within ±5 s
      of the cited dialogue.

## Out of scope

- Per-mention id fallback (mixing episode ids and dates). It isn't needed
  once episodes.yaml is complete, and it would desync body markers from
  `sources[]`.
- Changing `resource` or the `# Belege` line format. pnp-export-data parses
  `Session YYYY-MM-DD` out of the body.
