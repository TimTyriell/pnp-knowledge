# Releasing a session tag

Session tags are the as-of checkpoints (ADR-001 §1): `?as_of=s<NN>` and `summary.py --as-of s<NN>` read the bundle at that tag.

After merging an `ingest/s<NN>` PR into `main`, tag the merge commit and push the tag:

```bash
git tag s<NN> && git push origin s<NN>
```

The baseline tag on the current `main` is a human step; the repo had 0 tags on 2026-10-26 (`git tag | wc -l`). Until a tag exists, its as-of reads cannot resolve.
