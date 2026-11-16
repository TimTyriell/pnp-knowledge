# O5 — Episode metadata for the 15 sessions since 2026-08-12 (human)

Branch: none in pnp-knowledge code (data step). Last in the O-series.
Cost $0; one network read of the YouTube playlists. **Not a worker task**:
it runs pnp-crawl's network sync and writes `knowledge/`.

## Intent

15 session notes (2026-08-12 … 2026-11-10) have no `episode:` key, because
their VOD URLs are missing from `knowledge/episodes.yaml` (60 entries).
`episodes.citation_labels` is all-or-nothing by design, so every concept that
cites one of those sessions falls back to positional source ids `'1'..'n'` —
297 concepts today, including every main PC. OKF §5.1 warns against
positional ids, and they churn every body when the labels arrive.

No code change: the fix is the existing sync (`pnp-crawl/sync_episodes.py`,
crawl C3). The ratchet `test_positional_source_ids_only_go_down`
(`tests/test_bundle_invariants.py`) then tightens.

## Steps (HUMAN RUN)

1. `cd pnp-crawl && .venv/Scripts/python.exe sync_episodes.py` (dry run; reads
   `config.PLAYLISTS`). Check that all 15 dates appear.
   **STOP** if they do not: the season's playlist is probably missing from
   `config.PLAYLISTS`. Add it there first (pnp-crawl PR).
2. `sync_episodes.py --write`, review the diff of the AUTO entries (season/team
   from the YouTube title), correct by hand where the title lies.
3. `--write` edits `pnp-knowledge/knowledge/episodes.yaml` in place
   (line-level; path from `sync_episodes.py`'s knowledge-root lookup). Check
   it wrote the main checkout's bundle, not a worktree's, and commit it in
   the bundle repo.
4. Warm `pnp run` (fold into the O1 HUMAN RUN if not yet done).
5. Lower `test_positional_source_ids_only_go_down`'s baseline to the new count
   with a comment citing O5.

## Done when

- [ ] Every session note has `episode:`.
- [ ] Positional-id concepts ≈ 0 (from 297); baseline lowered with a comment.

```bash
grep -L "^episode:" knowledge/bundle/splitter_des_ewigen/sessions/*.md | grep -v index.md   # expect nothing
grep -rlE "^- id: '[0-9]+'" knowledge/bundle/splitter_des_ewigen --include=*.md | wc -l
cd services/kb && PNP_REQUIRE_BUNDLE=1 .venv/Scripts/python.exe -m pytest -q tests/test_bundle_invariants.py
```
