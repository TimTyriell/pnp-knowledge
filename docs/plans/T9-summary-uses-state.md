# T9 — The pre-session recap uses tracked threads and status

| | |
|---|---|
| Branch | `feat/summary-open-threads` |
| Base | `origin/main` (after T6, T7 merged and re-emitted) |
| Depends on | T6 (`/concepts?type=Thread&thread_status=open`), T7 (`world_status` in frontmatter), T2 (`team_letter`, `teams`) |
| Cost | $0 to build. Each `summary.py` run is one DeepSeek call, as today |
| Size | S |

## Goal

`services/summary/summary.py`:

1. Fetches the open threads from the KB and gives them to the model as
   ground truth. The model no longer *guesses* "Offene Fäden" from recap
   prose.
2. Prints an **"Offene Fäden"** list deterministically (not LLM-written)
   under the recap, with links. The model is told to refer to it, not
   restate it.
3. Gets an optional `--team A` flag. It keeps only that table's sessions
   (`team_letter`) and only threads whose `teams` include that letter, so a
   Team-B recap doesn't spoil Team-A events.

## Why

- `SYSTEM_PROMPT` today asks the model to write "Offene Fäden" from the last
  3 recaps. A thread opened 10 sessions ago and still open is invisible to
  it.
- Four tables share one world. A recap for Team B that mentions Team-A
  discoveries is a spoiler.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c feat/summary-open-threads origin/main
```

### 2. `summary.py`

1. `fetch_sessions(kb_url, count, as_of, team=None)`. When `team` is set:
   - the listing has no frontmatter, so fetch the details of *all* sessions;
   - filter by `detail["frontmatter"].get("team_letter") == team`;
   - **then** take the last `count`.

   Keep the no-team path as it is (one detail call per selected session).
2. New function:

```python
def fetch_open_threads(kb_url: str, as_of: str | None, team: str | None) -> list[dict]:
    """Open Thread concepts (T6), oldest first; filtered to one table when *team* is set.

    Returns [] against a KB that predates threads, so the recap still works.
    """
```

   - `GET /concepts?type=Thread&thread_status=open` (plus `as_of`).
   - For each item, `GET /concepts/{concept}` and keep the frontmatter.
   - Filter `team in fm.get("teams", [])` when `team` is set.
   - Sort by `fm.get("opened")`, then title.
   - Catch nothing here; `main` already handles `httpx.HTTPError`.
3. `build_messages(sessions, outlook_context, threads=None)`. When `threads`
   is non-empty, append to the user content:

```text
Offene Fäden laut Wissensbasis (gesichert, nicht verändern):
- [quest] Evakuierung des Halblingshofs (seit S1-02-B)
...
```

   Change `SYSTEM_PROMPT`'s last bullet group. The model must no longer write
   its own "Offene Fäden" list. Replace that sentence with: "Die Liste
   'Offene Fäden' wird separat aus der Wissensbasis angehängt — schreibe
   KEINE eigene; beziehe dich höchstens im Fließtext darauf."
4. `render_threads(threads) -> str` (deterministic). Output:

```text
## Offene Fäden
- Auftrag: Evakuierung des Halblingshofs (seit S1-02-B) — threads/evakuierung_des_halblingshofs
```

   Kind labels: quest→Auftrag, mystery→Rätsel, promise→Versprechen,
   debt→Schuld, deadline→Frist. Return `""` for an empty list.
5. `main`:
   - add `--team` (choices are free text; the letter is uppercased);
   - call `fetch_open_threads`;
   - print `call_llm(...)`, then `render_threads(threads)`, then
     `sources_footer` (also list the thread concepts as sources).

### 3. Tests: `services/summary/test_summary.py` (append)

- `build_messages(..., threads=[fm])` puts the thread title into the user
  content, and the system prompt no longer asks for its own list.
- `render_threads` labels kinds in German and is `""` for `[]`.
- `fetch_open_threads` with `httpx.MockTransport`. Check how the existing
  tests avoid HTTP. If they don't use a transport, add a tiny
  `transport=` parameter to the two fetch functions (default `None` →
  normal client) and pass a `MockTransport` in the tests.
  - The team filter drops a thread with `teams: [A]` when `team="B"`.
  - A 200 with `[]` → `[]`.

### 4. README

In `services/summary/README.md`, document `--team` and the
threads-from-KB contract in 3–5 lines.

### 5. Verify, commit, PR

```bash
cd services/summary && python -m pytest -q
```

CI installs only `pytest httpx` here, so don't import `pnp_okf`.

Message: `feat(summary): ground open threads in the KB and filter by table`

## Done when

- [ ] `summary.py --team A` prints a recap whose "Offene Fäden" come from
      Thread concepts, with no Team-B-only thread.
- [ ] Tests green offline.
