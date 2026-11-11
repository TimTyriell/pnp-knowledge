# Releasing a session tag

Session tags are the as-of checkpoints (ADR-001 §1): `?as_of=s<NN>` and `summary.py --as-of s<NN>` read the bundle at that tag.

The bundle is its own repo at `knowledge/` (private `TimTyriell/pnp-knowledge-bundle`), so the tags live there. After merging an `ingest/s<NN>` PR into that repo's `main`, tag the merge commit and push the tag:

```bash
git -C knowledge tag s<NN> && git -C knowledge push origin s<NN>
```

The baseline tag on the current `main` is a human step; the repo had 0 tags on 2026-10-26 (`git tag | wc -l`). Until a tag exists, its as-of reads cannot resolve.

## Releasing a frozen season

After `pnp freeze <season>` creates the snapshot, release it from the bundle's
own repository (`knowledge/`): create a branch, commit `frozen/<season>/`, open
and merge a PR, then tag the merged commit `season-<key>-v<extract version>`.
For example, Prolog extracted with v6 is tagged `season-P-v6`.

## Cache (C1)

The LLM cache lives in the bundle repo at `knowledge/cache/` and is swept by `pnp cache gc` (rules: [PIPELINE.md §6](architecture/PIPELINE.md)).

- An ingest PR carries the `cache/**` and `cache/gc_ledger.json` changes next to the bundle diff. Review them with the knowledge diff.
- Deletions only start after the first `s<NN>` tag exists, so set the baseline tag. With no tag the sweep records stale entries and deletes nothing.
- A blocked sweep (the mass guard reports `blocked`): run `pnp cache gc --dry-run`, review the list, then `pnp cache gc --allow-mass`.
- To drop a session on purpose, delete its transcript **and** `cache/extract/<session>/` in the same PR. Otherwise the live set is unknown and every sweep aborts.
- Restore a deleted entry: `git -C knowledge restore --source=<tag> -- cache/<path>`.
