# A6 — Autolink precision and duplicate proposals

| | |
|---|---|
| Branch | `fix/autolink-precision` |
| Base | `origin/main` |
| Depends on | — |
| Cost | $0 code. The warm re-emit is ~$0.05 **if** only the stoplist changes. Each `merge:` rule a human adds re-synthesizes the merged entity (deep/standard tier), cents to ~$0.50 total. **HUMAN RUN** |
| Size | M |
| Gate | Human approves stoplist entries and every merge |

## Goal

1. A new rules family, `autolink_block:`: names that must **never** be
   autolinked, because they are common German nouns that happen to be an
   entity name or alias. Measured mislinks:
   - `[Krieg]` → `characters/krieg`, 24× (the noun "war");
   - `[Goblins]` → `npcs/pilz_goblins`, 79 of 81 inbound;
   - `[Schwert]` → `items/schwert`, 28×.
2. A read-only report script, `autolink_doctor.py`, that finds more
   candidates.
3. A read-only report script, `dup_doctor.py`, that proposes `merge:` rules
   from a signal the pipeline ignores today. The synthesizer often names a
   near-duplicate concept in its first sentence ("Tarkia (auch
   [Tarkir](…))").

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c fix/autolink-precision origin/main
```

### 2. Loader in `resolve.py`

Next to `_load_alias_blocks`:

```python
def load_autolink_block(registry_path: Path) -> set[str]:
    """``autolink_block:`` -- names never autolinked (lowercased).

    Common nouns that are also entity names ("Krieg" the PC vs. "Krieg" the
    war) mislink every prose occurrence. Explicit links the model wrote are
    unaffected; this only stops the deterministic first-occurrence linker.
    """
    data = _registry_data(registry_path)
    return {str(n).strip().lower() for n in (data.get("autolink_block") or [])} - {""}
```

### 3. `synthesize.link_targets`

Add a keyword parameter: `def link_targets(entities, blocked: set[str] | frozenset[str] = frozenset())`.
Inside the loop, skip a name when `name.lower() in blocked`. Add one
docstring line. Every existing call keeps working (default empty).

In `cli.py`, change `targets = link_targets(entities)` to
`targets = link_targets(entities, load_autolink_block(registry_path))`.

### 4. Rules entries (GM approves in the PR)

At the end of `knowledge/entity_rules.yaml`, in the file's comment style:

```yaml
# autolink_block: names the deterministic autolinker must never link
# (synthesize.link_targets). For common German nouns that are also an entity
# name or alias -- "Krieg" (war) vs. the PC Krieg. Explicit links the model
# wrote are unaffected. Measured mislinks 2026-10-18: Krieg 24x, Schwert 28x.
autolink_block:
- Krieg
- Schwert
```

For **Goblins**, prefer `alias_block:` over a stoplist. The alias "Goblins"
on `npcs/pilz_goblins` is wrong in itself:

```yaml
alias_block:
  npcs/pilz_goblins:
  - goblins
```

(Check `alias_block:`'s existing entries are lowercased, as in the
`items/notiz_von_hal` example.)

### 5. `services/kb/autolink_doctor.py` (new, read-only)

Style of `rules_doctor.py`. Logic:

1. Walk the bundle bodies (not frontmatter). For every markdown link
   `[label](/dir/slug.md)`, count `(label, target)` pairs.
2. For single-word labels starting with an uppercase letter: report pairs
   where the label is **not** the target's title (frontmatter `title`) and
   the target's directory is `characters`, `npcs` or `items`. Those are the
   likeliest noun collisions.
3. Print a table sorted by count desc (`label | target | count | target
   title`), and a ready-to-paste `autolink_block:` block of the top 20 for
   the human to prune.

### 6. `services/kb/dup_doctor.py` (new, read-only)

1. Per concept (excluding sessions), take the **first paragraph** of the body.
2. Find links whose target is in the **same directory** as the concept and
   whose target title is similar to the concept title:
   `difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.75`, or
   one contains the other.
3. Also match the explicit pattern
   `\(auch \[([^\]]+)\]\((/[^)]+)\.md\)`.
4. Exclude pairs already in `never_merge:` (read via `_registry_data`).
5. Print proposals as YAML `merge:` lines. A merge rule maps a *name* to the
   surviving concept id. Use the loser's title lowercased → the winner's
   concept id. Winner = the concept with more `sources` entries.

### 7. Known duplicates (from the 2026-10-18 analysis) for the human to rule on

List these in the PR as a checklist (✔ merge / ✘ `never_merge:`):

- `npcs/vitius` / `npcs/vityus`
- `locations/tarkia` / `locations/tarkir`
- `locations/die_narbe` / `locations/narben`
- `locations/breska` / `locations/dorf_breska`
- `locations/casa_del_cookie` / `casa_de_kuki_la_casa_de_cookie` / `anwesen_casa_del_cookie`
- `locations/brocadil` / `locations/brokkadil` / `locations/boragdil`
- `items/statue_des_nerash` / `items/statue_von_nerash`
- `items/weisser_totem_der_nerash` / `items/weisses_totem_von_nerash` / `items/totem_von_nerash`
- `items/handschellen` / `items/magie_unterdrueckende_handschellen`
- `items/ring_der_teleportation` / `items/magischer_ring_teleportationsring`
- `characters/miko` / `characters/miqo` (wait for pnp-crawl C4's label decision)

Don't add any `merge:` without a ✔ from the human. For each ✔, add the
`merge:` lines (all names of the loser → winner id). For each ✘, add a
`never_merge:` group with a reason comment.

### 8. Tests

`services/kb/tests/test_autolink_block.py` (new):

```python
from pnp_okf.models import CanonicalEntity, EntityType
from pnp_okf.synthesize import link_targets, render_brief_body
from pnp_okf.models import MentionRef


def _e(cid, name, etype=EntityType.CHARACTER, note="n"):
    return CanonicalEntity(concept_id=cid, type=etype, canonical_name=name,
                           mentions=[MentionRef(session_id="s", date="d", url="u", citation_ts="00:00:01", note=note)])


def test_blocked_name_is_not_a_link_target():
    targets = link_targets([_e("characters/krieg", "Krieg")], blocked={"krieg"})
    assert "Krieg" not in targets


def test_blocked_name_stays_plain_text_in_a_brief_body():
    war = _e("domains/splitterwelt", "Splitterwelt", EntityType.DOMAIN, note="Der Krieg zerriss die Welt.")
    body = render_brief_body(war, link_targets([war, _e("characters/krieg", "Krieg")], blocked={"krieg"}))
    assert "[Krieg]" not in body


def test_unblocked_names_still_link():
    war = _e("domains/splitterwelt", "Splitterwelt", EntityType.DOMAIN, note="Lindo Laut kommt.")
    body = render_brief_body(war, link_targets([war, _e("characters/lindo_laut", "Lindo Laut")]))
    assert "[Lindo Laut](characters/lindo_laut.md)" in body
```

Plus a loader test in the style of the existing rules-file tests
(`tests/test_rules_file.py`).

### 9. Verify, commit, PR

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
.venv/Scripts/python.exe services/kb/autolink_doctor.py | head -40
.venv/Scripts/python.exe services/kb/dup_doctor.py | head -60
```

(Use the services/kb venv; run the scripts from `services/kb`.)

Commits:
1. `feat(kb): autolink_block rules family`
2. `chore(kb): autolink and duplicate doctors`
3. `chore(knowledge): block noun autolinks, rule on duplicates` (after the
   human answers)

## HUMAN RUN

```bash
pnp run --estimate      # stoplist alone: ~0 calls. Each merge: re-synth of the survivor.
pnp run
```

Then:
- Re-baseline `test_link_coverage.py` if it moved, with a comment naming A6.
- Check `grep -c "\[Krieg\]" -r knowledge/bundle` drops to the explicit
  model links only.
- Expect a small rename/prune count from merges, well under the 2% guards.

## Done when

- [ ] The three measured mislinks are gone.
- [ ] Every listed duplicate pair has a ✔ merge or ✘ never_merge rule.
- [ ] Doctors committed and documented in PIPELINE.md §12 (commands list).
