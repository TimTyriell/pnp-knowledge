# T6 — Emit Thread concepts (quests, mysteries, promises, debts, deadlines)

| | |
|---|---|
| Branch | `feat/thread-concepts` |
| Base | `origin/main` (after T5 merged **and** its HUMAN RUN cached the state pass) |
| Depends on | T5 (ledger, cache), T2 (`teams_for`), T1 (`_url_at`) |
| Design | [T00 §4.5](T00-tracking-model.md), decision D3 (no LLM for thread bodies) |
| Cost | $0. `pnp run` only *reads* the state cache. Warm re-emit **HUMAN RUN** ~$0.05 |
| Size | M |

## Goal

`pnp run` folds the cached state pass and writes:

1. one deterministic concept file per thread, `threads/<slug>.md`;
2. a `# Offene Fäden` section in each session note, listing the threads that
   session touched;
3. `threads/index.md`, grouped by kind and status.

It also reads human corrections from a new `thread_rules:` family in
`entity_rules.yaml`, and the API can filter threads by `thread_status`.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c feat/thread-concepts origin/main
```

### 2. Thread rules: `src/pnp_okf/state.py`

Rules shape, documented in the rules-file comment (step 9):

```yaml
thread_rules:
  merge:            # loser id -> winner id (the model opened the same thread twice)
    threads/evakuierung_2: threads/evakuierung
  title:            # id -> display title (identity unchanged)
    threads/evakuierung: Evakuierung des Halblingshofs
  status:           # id -> forced thread_status (GM ruling)
    threads/raetsel_um_nox: open
  ignore:           # ids that are not threads at all
  - threads/regelfrage_zu_hope
```

Implement:

```python
def apply_thread_rules(ledger: Ledger, rules: dict) -> None:
    """Human corrections on top of the fold. Mutates ``ledger.threads``.

    Order: ignore, merge, then title and status -- so a title or status rule
    may name the merge *winner* and still apply.
    """
```

Behaviour:

- `ignore`: delete those ids.
- `merge`: for each `loser -> winner`, when both exist, extend
  `winner.entries` with `loser.entries`, re-sort by `(entry.date,
  entry.citation_ts)`, union `involves` (winner first), set
  `winner.opened` to the earliest entry's session, recompute `status` from
  the last entry's status and `resolved` as the first session where status
  became non-open (none if the last status is open), then delete the loser.
  A missing loser or winner goes to `ledger.warnings` with the id.
- `title`: overwrite `.title`.
- `status`: overwrite `.status`. If the forced value is open, set
  `resolved = None`. If not, set `resolved` to the last entry's session when
  it is currently None.

Loader: `load_thread_rules(registry_path) -> dict`, which returns
`_registry_data(registry_path).get("thread_rules") or {}`.

Tests go in `tests/test_state_ledger.py` (append): one test per rule kind,
plus "a status rule naming a merge winner still applies".

### 3. Name → concept id mapping: `src/pnp_okf/state.py`

```python
class NameIndex:
    """Map a state-pass name to a live concept id, or None.

    Exact canonical name or alias first (case-insensitive), then slug
    equality. A name two concepts share is ambiguous and maps to None --
    the same no-guessing rule as synthesize.link_targets.
    """

    def __init__(self, entities: list[CanonicalEntity]) -> None: ...
    def lookup(self, name: str) -> str | None: ...
```

Implementation:

- Build `owners: dict[str, set[str]]` from `name.strip().lower()` for
  canonical names and aliases.
- Build `slugs: dict[str, set[str]]` from `slugify(name)`.
- `lookup` returns the single owner if exactly one exists, otherwise tries
  the slug map the same way, otherwise `None`.

Tests: exact hit, alias hit, case-insensitivity, slug hit ("Lindo  Laut"),
ambiguous → None, unknown → None.

### 4. Thread rendering: `src/pnp_okf/emit.py`

Add `emit_threads(...)` below `emit_entity`. Signature:

```python
def emit_threads(
    bundle_dir: Path,
    threads: list[ThreadRecord],
    names: NameIndex,
    episodes: Episodes,
    index: ConceptIndex | None,
) -> tuple[list[str], list[str]]:
    """Write threads/<slug>.md per thread. Returns (written_ids, unmatched_names).

    Deterministic, no LLM (T00 D3): the body is the dated Verlauf of the
    thread's entries plus its participants, so every line is checkable
    against the cited moment.
    """
```

For each `ThreadRecord t` (in `thread_id` order):

1. `slug = t.thread_id.split("/", 1)[1]`.
2. `involves_ids` = `names.lookup(n)` for each name in `t.involves`; drop
   `None`. Collect misses into `unmatched` as `f"{t.thread_id}: {n}"`.
3. `entries = [e for _, e in t.entries]`.
4. `labels = citation_labels([e.url for e in entries], episodes)`. Use
   `labels[i]` if `labels` else `e.date` as the marker.
5. Status words for the `Verlauf` lines:
   `{"open": "fortgeführt", "resolved": "erledigt", "abandoned": "aufgegeben"}`.
   The **first** entry always uses "eröffnet".
6. Evidence words:
   `{"observed": "beobachtet", "claimed": "behauptet", "rumor": "Gerücht", "speculation": "Vermutung"}`.
7. Body:

```text
{first entry note}

## Verlauf

- **[{marker}]** Session {date} @ {ts} — {status word}: {note} _({evidence word})_
...

## Beteiligte

- [{title of concept}](/{concept_id}.md)     # only when involves_ids is non-empty

# Belege

[{marker}] Session {date} @ {ts} ({url})
...
```

   The `Session YYYY-MM-DD` text is **required** in both lists. It is what
   pnp-export-data's relevance gate counts (T00 §4.5). For the link title in
   `## Beteiligte`, use the canonical name from a `{concept_id: name}` map
   passed in through `NameIndex`. Add a method `NameIndex.title(cid)`.

8. Frontmatter:

```python
frontmatter = {
    "type": "Thread",
    "id": f"THREAD_{slug.upper()}",
    "title": t.title,
    "description": _short_desc(entries[0].note) if entries else t.title,
    "tags": ["threads", t.kind],
    "timestamp": f"{entries[-1].date}T00:00:00Z" if entries and entries[-1].date else _now_iso(),
    "kind": t.kind,
    "thread_status": t.status,
    "opened": first marker,
    "resolved": marker of the entry where t.resolved session first appears, else omit,
    "evidence": entries[0].evidence if entries else "observed",
    "teams": teams_for([e.url for e in entries], episodes) or omit,
    "involves": involves_ids or omit,
    "sources": [{"id": marker, "resource": e.url, "at": e.citation_ts,
                 "url_at": _url_at(e.url, secs), "last_modified": f"{e.date}T00:00:00Z"} ...],
}
```

   Omit keys whose value would be empty. `_order_frontmatter` drops `None`
   and `""` but **keeps `[]`**, so guard lists explicitly.

9. If `index` is given, run the body through `normalize_body(body, index,
   self_id=t.thread_id)` exactly like `emit_entity` does.
10. Write with `_stamp_generated` and `write_concept_text`, copying
    `emit_entity`'s last three lines.

Add `prune_threads(bundle_dir, keep: set[str]) -> int`: delete
`threads/*.md` (except `index.md`) whose id isn't in `keep`, and return the
count. It is only called when the fold covered **every** session (step 6).

### 5. Session notes: `# Offene Fäden`

`emit_sessions` gets a parameter
`threads_by_session: dict[str, list[tuple[str, str, str, str]]] | None = None`.
Each value is a list of `(thread_id, title, status_word, note)`. Render it
after `# Ereignisse` (T4) and before `# Auftretende Entitäten`:

```markdown
# Offene Fäden

- [Evakuierung des Halblingshofs](/threads/evakuierung_des_halblingshofs.md) — eröffnet: …
```

Build the dict in `cli.py` from the ledger: for each thread, for each
`(status, entry)`, append to `entry.session_id`, using the same status-word
rule (the first entry is "eröffnet").

### 6. Wire into `cli.py` `_run_pipeline`

After the T4 partition and **before** `build_concept_index`:

```python
    # T6: fold the cached state pass. Never calls the model -- estimate=True
    # stops at the first uncached session, so the fold is a cached prefix.
    glossary_rows = load_glossary(paths.knowledge_root)
    state_run = run_state(
        transcripts, cfg.for_tier("state"), paths.cache_dir, glossary_rows, estimate=True,
    ) if glossary_rows else None
    ledger = state_run.ledger if state_run else Ledger()
    state_complete = bool(state_run) and state_run.uncached_estimate == 0
    if state_run and not state_complete:
        log.warning("[state] %d session(s) have no cached state -- run `pnp state`; "
                    "threads are emitted for the cached prefix only and not pruned.",
                    state_run.uncached_estimate)
    apply_thread_rules(ledger, load_thread_rules(registry_path))
    thread_ids = sorted(ledger.threads)
```

**Partial runs:** when `partial_run` is true, skip the whole T6 block (set
`ledger = Ledger()`, `thread_ids = []`) and don't prune threads. A
`--session` run sees a subset of transcripts and would fold a wrong prefix.

Then:

- `build_concept_index(entities, tmap, spellings, extra_ids=thread_ids)`:
  add the `extra_ids: Iterable[str] = ()` parameter to `build_concept_index`
  in `emit.py` (append to `concept_ids`).
- After the entity emit loop, and **before** `emit_sessions` (link targets
  first, PIPELINE.md §7):
  ```python
    written, unmatched = emit_threads(paths.bundle_dir, list(ledger.threads.values()),
                                      NameIndex(entities), episodes, index)
    if state_complete:
        prune_threads(paths.bundle_dir, set(written))
  ```
- Write `unmatched` (and `ledger.warnings`) to
  `paths.conflicts_dir / "state_unmatched.md"`. The conflict validator in
  `test_bundle_invariants.py` skips files that aren't `type: Conflict`
  (see the `merge_proposals.md` precedent), so give this file **no**
  frontmatter, just a header line and bullets. Delete the file when both
  lists are empty.
- Pass `threads_by_session=...` to `emit_sessions`.
- Add `"threads": len(written)` and `"threads_open": sum(1 for t in
  ledger.threads.values() if t.status == "open")` to the `counts` of
  `_write_run_status`.

### 7. Index and validation

- `emit_indexes`: add a `threads/index.md`. Find how per-type indexes are
  written with `write_index` and grouped. Group the threads into sections
  `Offen`, `Erledigt`, `Aufgegeben`, and within each by kind
  (German labels: Auftrag, Rätsel, Versprechen, Schuld, Frist). Pass the
  thread records in as a new optional parameter.
- `validate.py`:
  - Required fields: change
    `required = REQUIRED_FIELDS[etype] if etype else _SESSION_FIELDS` to also
    use `_CONCEPT_FIELDS` when `dirname == "threads"`.
  - A new report list `invalid_thread_fields`: add `(cid, msg)` when
    `kind` isn't one of the 5 kinds or `thread_status` isn't one of the 3.
    Advisory, not in `integrity_ok`.
  - Duplicate-id check: `THREAD_` ids are covered by the existing
    `duplicate_ids`, so nothing to add.

### 8. API: `src/pnp_okf/api.py`

In `list_concepts`, add a query parameter
`thread_status: str | None = None`. Skip concepts whose
`fm.get("thread_status") != thread_status` when it is given. Include
`"thread_status": fm.get("thread_status")` and `"kind": fm.get("kind")` in
each result dict **only when present**, so existing consumers see no new
`null` keys.

Test in `tests/test_api.py`: add a thread file to the `repo` fixture's
second commit and assert that
`/concepts?type=Thread&thread_status=open` returns it and
`thread_status=resolved` doesn't.

### 9. Rules-file documentation

Append the empty family to `knowledge/entity_rules.yaml` with a comment
block in the file's style:

```yaml
# thread_rules: corrections to the state pass's threads (docs/plans/T6).
# merge: loser -> winner; title: id -> name; status: id -> open|resolved|abandoned;
# ignore: ids that are not threads. Thread ids come from the state pass's
# ledger (`pnp state` report), never from the bundle file name by hand.
thread_rules: {}
```

### 10. Tests: `tests/test_thread_emit.py` (new)

- `emit_threads` writes `threads/<slug>.md`. Frontmatter has `type:
  Thread`, `kind`, `thread_status` and `sources[0].url_at`. The body has
  `## Verlauf`, with the first line saying "eröffnet" and containing
  `Session 2026-01-01 @`.
- Unmatched involves names are returned, not linked.
- `thread_status: resolved` and `resolved:` are set when the last entry
  resolves.
- `emit_sessions` with `threads_by_session` renders `# Offene Fäden` with a
  `/threads/` link.
- `prune_threads` deletes only stale `threads/*.md`.
- `validate_bundle` accepts a well-formed thread (no missing required
  fields) and flags `kind: foo`.
- `_run_pipeline` with no glossary file emits no `threads/` directory. Use
  the offline pipeline test pattern in `tests/test_pipeline_offline.py`;
  read it first and extend the closest test.

### 11. Verify

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
```

### 12. Commit and PR

Message: `feat(kb): emit thread concepts and open threads per session`

## HUMAN RUN

1. `pnp run --estimate` must show ~0 calls. Then `pnp run`.
2. Spot-check 10 threads against the transcript at their `url_at`:
   - Is it a real quest/mystery/promise/debt/deadline?
   - Is the status right?
   - Is the evidence right?
3. Add `thread_rules:` corrections. Re-run (free; it is a warm fold).
4. Commit the bundle and rules. Record the counts in the PR: threads by kind
   and status, unmatched names.

## Done when

- [ ] `threads/` exists with an index; validate integrity green.
- [ ] Session notes list their threads.
- [ ] API filter works.
- [ ] Spot-check results recorded; corrections in `thread_rules:`.
