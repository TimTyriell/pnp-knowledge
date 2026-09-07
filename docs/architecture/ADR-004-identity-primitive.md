# ADR-004 — Concept identity stays derived from the name, for now

**Status:** Accepted, 2026-09-07
**Supersedes nothing. Related:** ADR-001 (OKF-in-git as system of record)

## Context

A concept's identity is its `concept_id`, and that id is *derived*:

```
concept_id = TYPE_DIR[type] + "/" + slugify(apply_spellings(<name the LLM chose>))
```

The typed id in frontmatter (`NPC_HEXE`) is derived from the same slug
(`models.py:222`), so it is not an independent identity either.

This means identity is a function of a non-deterministic model output.
Re-extraction resamples the model, the model rewords a name, and the id moves.
Measured on the prompt-v6 rebuild: **432 of 868 ids moved in a single
re-extraction.** Everything keyed on `concept_id` detaches when that happens —
the `ignore:`, `important:`, `never_merge:`, `alias_block:` and
`canonical_name:` rule families, and `wiki_pages.toml` in `pnp-export-data`.
The 2026-08 incident and the v6 migration are both this failure.

## What the field does

External review (2026-09-06) found a consistent split:

- **Systems that derive identity from the name** — Microsoft GraphRAG,
  LightRAG, nano-graphrag — list entity disambiguation as a standing
  limitation in their own documentation. GraphRAG's docs concede that "Jon"
  and "Jon Márquez" remain separate nodes.
- **Systems that specifically claim to solve dedup across repeated runs** —
  Graphiti/Zep, Cognee — assign an **opaque id once** and treat name and
  aliases as mutable attributes hanging off it.

The same shape holds far outside the LLM world: Wikidata QIDs persist through
renames *and* merges with the label as a separate editable field; Zettelkasten
practice puts a permanent UID in the filename precisely so the descriptive part
can change; Docusaurus separates frontmatter `id` from `slug`; git separates a
content hash from a branch name.

**Derive-from-name is the design the field moved away from.** We are on the
criticised side of that split, knowingly.

## Decision

**Keep derived ids. Close the reachable failure modes instead.** Shipped:

| Mitigation | Where |
|---|---|
| Reanchor a reworded name against aliases of *live* concepts, not just retired ones | `resolve._reanchor_to_live_alias` |
| An id the registry already knows never loses a fuzzy fold | `resolve.merge_near_duplicates` |
| Token-order-insensitive slug matching | `resolve._fuzzy_match` |
| Mass-rename guard tightened 10% → 2% | `emit.check_rename_safety` |
| A churn ratchet that fails the build when ids move | `tests/test_identity_churn.py` |

## Rejected alternative: registry-issued opaque ids

The structurally correct fix, and the one the field settled on. Rejected *for
now*, not on principle.

The cheap version is real and was costed: keep `npcs/harald.md` as the
derived, regenerable filename, and move only the **rule key** to a stable id
minted once and stored in frontmatter. Human-readable git diffs survive; a
rename moves a file but never detaches a rule. That is a few dozen lines —
genuinely smaller than the matching work already shipped above.

Why it is still deferred:

1. **It is a cross-repo migration.** `pnp-export-data/wiki_pages.toml` keys on
   `concept_id`. Doing this properly means migrating that map too, in the same
   change, or the downstream break is worse than the problem being fixed.
2. **The mitigations above are not yet measured against a real re-extraction.**
   The churn ratchet currently reads 35, and that number is *stale rule work*,
   not model rewording — the registry lags `entity_rules.yaml` by one run. Until
   a re-extraction actually happens, we do not know how much churn survives the
   live-alias reanchor. Spending a cross-repo migration before that measurement
   is guessing.

**This ADR is an admission, not a defence.** The mitigations reduce churn; they
do not make identity stable, because identity is still a model output.

## Consequences

- Every re-extraction is a rename event. Run `pytest tests/test_identity_churn.py`
  between extraction and emit; `check_rename_safety` is the runtime backstop.
- `rules_doctor.py` stays necessary — dead rules are a permanent maintenance
  category rather than a bug to be fixed once.
- A concept whose `canonical_name` is corrected keeps an id derived from the
  *old* spelling, permanently. `items/notiz_von_tyrex` (canonical name "Notiz
  von Tyrael") is the live example: a Whisper mishearing fossilised into an id.

## Revisit triggers

Adopt registry-issued ids when **any** of these holds:

1. The churn ratchet cannot be held at 0 after a real re-extraction with the
   live-alias reanchor in place.
2. A second consumer beyond `wiki_pages.toml` starts keying on `concept_id` —
   the migration cost grows with each one, so the cheapest moment is before the
   second appears.
3. Dead rules exceed ~10% of `entity_rules.yaml` (currently 54 of ~570).
4. Any re-extraction trips `check_rename_safety` at the 2% threshold again.
