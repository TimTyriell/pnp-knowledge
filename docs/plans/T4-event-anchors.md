# T4 — Events become session anchors; only arcs stay concepts

| | |
|---|---|
| Branch | `feat/event-anchors` |
| Base | `origin/main` (after A6 and T1 merged) |
| Depends on | A6 (autolink stoplist touches the same link index), T1 |
| Design | [T00 §4.3](T00-tracking-model.md), decision **D2** |
| Cost | $0 code. The re-emit is warm (~$0.05), but it **prunes ~280 files**: **HUMAN RUN** with `--allow-prune` and an audit note |
| Size | M |
| Gate | **GM approves the allowlist** (step 3) before the HUMAN RUN |

## Goal

- An `Event` entity is emitted as a concept file **only if** its concept id is
  in the new `event_concepts:` family in `knowledge/entity_rules.yaml`.
- Every other Event is rendered inside its session note under a new
  `# Ereignisse` section, as a `###` heading (a stable anchor) with subtype,
  timestamp and the mention note.
- Identity is unaffected: resolve still computes event ids. The rename guard
  sees them; only emit, the link index and the registry inventory leave them
  out.

## Why (measured 2026-10-18)

| | |
|---|---|
| Event concepts | 305; max span 1 session; median 36 words |
| … with an inbound link from a non-session concept | 19 (list below) |
| … the wiki can show | 1 (`events/verhandlung_mit_harl`, a live wiki page) |
| Subtypes | Kampf 90, Sonstiges 55, Entdeckung 41, Verhandlung 37, Ritual 34, Reise 21, Tod 18, Vertrag 5, Fest 3, Flucht 1 (invalid) |

Events duplicate the session recap, fragment arcs (three tournament events),
and store NPC retellings as facts (`events/tod_von_rotunas`).

Inbound-linked events (default allowlist candidates):
`zerstoerung_des_rings`, `schlacht_um_ehrenfels`, `vision_von_joran`,
`verhandlung_mit_spitzzahn`, `tod_des_seraphen`, `rueckzug_aus_dem_dungeon`,
`reise_zu_den_sanddorn_inseln`, `pakt_mit_huludan`, `lunaras_gedanken_zauber`,
`konfrontation_vor_der_kapelle`, `kampf_gegen_dormak`,
`hinrichtung_des_werwolfs`, `flucht_durch_das_portal`,
`explosion_der_gnoll_leichen`, `erkundung_des_dungeons`,
`begegnung_mit_landra`, `angriff_der_untoten_auf_die_karawane`. Must-keep:
`verhandlung_mit_harl` (wiki page, `important:`, ENTSCHEIDUNG target).

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c feat/event-anchors origin/main
```

### 2. Candidate report script: `services/kb/event_candidates.py` (new, read-only)

Follow the style of `rules_doctor.py` (module docstring that explains why,
`main() -> int`, stdout report, no writes). Logic:

1. `BUNDLE = Path(__file__).resolve().parents[2] / "knowledge" / "bundle" / "splitter_des_ewigen"`.
2. For each `events/*.md` (skip `index.md`): read the frontmatter with
   `pnp_okf.okf.split_document` and collect `title`, `subtype`, number of
   `sources`.
3. Count inbound links: for every `*.md` under the type dirs **except**
   `sessions/` and `events/`, count occurrences of
   `/events/<slug>.md` in the body.
4. Must-keep flags, read through `pnp_okf.resolve._registry_data(REGISTRY)`:
   the id is in `important:`, *or* it is the target of an
   `<!-- okf: entity=events/... -->` directive in any
   `knowledge/sources/*.md` (grep the files).
5. Print a markdown table sorted by (must_keep desc, inbound desc, subtype ==
   "Tod" desc, title), columns: `concept_id | title | subtype | inbound |
   must_keep | sources`.
6. At the end, print a ready-to-paste YAML block **`event_concepts:`** that
   proposes every row with `must_keep` **or** `inbound >= 1` **or**
   `subtype == "Tod"`.

Run it:
`cd services/kb && .venv/Scripts/python.exe event_candidates.py > ../../docs/audits/2026-10-xx-event-candidates.md`
(use today's date). Commit the report.

### 3. STOP: GM review of the allowlist

Paste the proposed `event_concepts:` block into the PR description and ask
the human to:

- remove events that aren't worth a page;
- add arcs (multi-session events). For an arc, also add `merge:` rules that
  fold each session's event name into one id, e.g.
  ```yaml
  merge:
    turnier von willauch: events/turnier_von_willauch
    arena-kämpfe in will auch: events/turnier_von_willauch
  ```
  Merge rules count as "explicit", so arcs already bypass
  `MAX_EVENT_SESSION_SPAN` (`resolve_entities`, variable `explicit`);
- decide `events/tod_von_rotunas` (an NPC's retelling). Default: *not*
  allowlisted, so it becomes an anchor in its session; the evidence flag
  arrives with T5/T7.

Continue with step 4 while waiting, but don't merge before the human
answers. Then put the approved block into `knowledge/entity_rules.yaml` as a
new top-level family at the end of the file, with a comment header in the
file's style:

```yaml
# event_concepts: Event ids that get their own concept file. Every other
# Event is a scene anchor in its session note (docs/plans/T4-event-anchors.md).
# Add an id here when an event spans sessions (an arc -- fold its pieces with
# merge:), is a turning point other pages link to, or has a wiki page.
event_concepts:
- events/verhandlung_mit_harl
- ...
```

### 4. Loader in `services/kb/src/pnp_okf/resolve.py`

Next to `_load_important`:

```python
def load_event_concepts(registry_path: Path) -> set[str]:
    """``event_concepts:`` -- the Event ids that are emitted as concepts.

    Everything else of type Event becomes a scene anchor in its session note
    (T4). Read through _registry_data like every other family (PIPELINE.md
    §5), never from the registry file alone.
    """

    data = _registry_data(registry_path)
    return {str(c).strip() for c in (data.get("event_concepts") or [])} - {""}
```

### 5. Partition in `services/kb/src/pnp_okf/cli.py` (`_run_pipeline`)

Directly after `check_rename_safety(...)` succeeds (and after `--clean`),
insert:

```python
    # T4: an Event is a concept only when entity_rules.yaml says so; the rest
    # are scene anchors inside their session note. The rename guard above
    # deliberately saw *all* entities -- identity is unchanged, only what we
    # emit as a file is.
    event_concepts = load_event_concepts(registry_path)
    anchored = [
        e for e in entities
        if e.type == EntityType.EVENT and e.concept_id not in event_concepts
    ]
    anchored_ids = {e.concept_id for e in anchored}
    entities = [e for e in entities if e.concept_id not in anchored_ids]
    log.info(
        "[events] %d event concept(s) kept, %d rendered as session anchors",
        sum(1 for e in entities if e.type == EntityType.EVENT), len(anchored),
    )
```

After this point every later use of `entities` (link index, synthesis, emit,
edges, `mention_concept_index`, prune, `write_registry`, `emit_indexes`,
`entities_by_type` in the run status) automatically sees only concepts.
Check each use between here and the end of `_run_pipeline`, and confirm none
needs the anchored ones except `emit_sessions` (next step).

Imports: `EntityType` from `pnp_okf.models`, `load_event_concepts` from
`pnp_okf.resolve`.

**Partial-run safety:** `prune_orphans` is skipped on a partial run already,
so nothing changes there.

### 6. Session anchors in `services/kb/src/pnp_okf/emit.py`

1. Add a small model near the top of `emit.py` (it's emit-internal, so don't
   put it in `models.py`):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EventAnchor:
    """One Event rendered inside its session note instead of as a concept (T4)."""

    title: str
    subtype: str
    citation_ts: str
    note: str


def event_anchors(entities: list[CanonicalEntity]) -> dict[str, list[EventAnchor]]:
    """``session_id -> anchors`` ordered by timestamp, for emit_sessions."""

    out: dict[str, list[EventAnchor]] = {}
    for e in entities:
        for m in e.mentions:
            out.setdefault(m.session_id, []).append(
                EventAnchor(e.canonical_name, e.subtype, m.citation_ts, m.note.strip())
            )
    for anchors in out.values():
        anchors.sort(key=lambda a: a.citation_ts)
    return out
```

2. `emit_sessions` gets a new keyword parameter
   `anchors: dict[str, list[EventAnchor]] | None = None`. Docstring line:
   "`anchors` (T4): Events that are not concepts, rendered as a
   `# Ereignisse` section of `###` headings so each has a stable anchor."
3. In `emit_sessions`, build the section and insert it **between** the recap
   and `# Auftretende Entitäten`. Replace:

```python
        body_parts = [
            "# Zusammenfassung",
            "",
            extraction.recap.strip(),
        ]
```

   with:

```python
        body_parts = [
            "# Zusammenfassung",
            "",
            extraction.recap.strip(),
        ]
        session_anchors = (anchors or {}).get(session_id, [])
        if session_anchors:
            body_parts += ["", "# Ereignisse"]
            for a in session_anchors:
                meta = " · ".join(p for p in (a.subtype, a.citation_ts) if p)
                body_parts += ["", f"### {a.title}", f"_{meta}_", "", a.note]
```

4. Event mentions that are anchored are no longer in `mention_concept_ids`
   (step 5 removed them), so the existing `if key not in
   mention_concept_ids: continue` already keeps them out of
   `# Auftretende Entitäten`. Check this with the test below; **don't** add a
   second filter.

### 7. Wire it in `cli.py`

In the `emit_sessions(...)` call, add `anchors=event_anchors(anchored),`.
Import `event_anchors` from `pnp_okf.emit`.

### 8. Validation: subtype "Flucht"

`validate.py` already reports `invalid_subtypes`. "Flucht" disappears once
its event is anchored, so no code change is needed. Note it in the PR.

### 9. Tests

New file `services/kb/tests/test_event_anchors.py`:

```python
"""T4: only allowlisted Events are concepts; the rest anchor in sessions."""

from __future__ import annotations

from pathlib import Path

from pnp_okf.emit import EventAnchor, emit_sessions, event_anchors
from pnp_okf.models import (
    CanonicalEntity,
    EntityMention,
    EntityType,
    MentionRef,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.okf import split_document
from pnp_okf.resolve import load_event_concepts

SID = "2026-01-20_RF_abc"


def _event(cid: str, name: str, ts: str, note: str) -> CanonicalEntity:
    return CanonicalEntity(
        concept_id=cid, type=EntityType.EVENT, canonical_name=name, subtype="Kampf",
        mentions=[MentionRef(session_id=SID, date="2026-01-20", url="http://x",
                             citation_ts=ts, note=note)],
    )


def test_event_anchors_group_by_session_and_sort_by_time():
    anchors = event_anchors([
        _event("events/b", "Kampf B", "01:00:00", "Später."),
        _event("events/a", "Kampf A", "00:10:00", "Früher."),
    ])
    assert [a.title for a in anchors[SID]] == ["Kampf A", "Kampf B"]


def test_session_note_renders_anchors_and_keeps_them_out_of_entity_list(tmp_path: Path):
    transcript = SessionTranscript(session_id=SID, date="2026-01-20", url="http://x", title="T")
    extraction = SessionExtraction(
        recap="Recap.",
        entities=[EntityMention(name="Kampf A", type=EntityType.EVENT,
                                note="Früher.", citation_ts="00:10:00")],
    )
    emit_sessions(
        tmp_path, {SID: transcript}, {SID: extraction},
        mention_concept_ids={},  # the anchored event has no concept
        anchors={SID: [EventAnchor("Kampf A", "Kampf", "00:10:00", "Früher.")]},
    )
    _fm, body = split_document((tmp_path / "sessions" / "2026-01-20.md").read_text(encoding="utf-8"))
    assert "# Ereignisse" in body
    assert "### Kampf A" in body
    assert "_Kampf · 00:10:00_" in body
    assert "# Auftretende Entitäten" not in body
    assert body.index("# Zusammenfassung") < body.index("# Ereignisse")


def test_load_event_concepts_reads_the_rules_file(tmp_path: Path):
    (tmp_path / "entity_registry.yaml").write_text("entities: []\n", encoding="utf-8")
    (tmp_path / "entity_rules.yaml").write_text(
        "event_concepts:\n- events/verhandlung_mit_harl\n", encoding="utf-8"
    )
    assert load_event_concepts(tmp_path / "entity_registry.yaml") == {"events/verhandlung_mit_harl"}
```

Check that `rules_path_for` resolves `entity_rules.yaml` next to the
registry (it does, `resolve.py`). If `SessionTranscript` or `EntityMention`
needs other required fields, follow the models.

Add a bundle test to `services/kb/tests/test_rules_applied.py` (or
`test_bundle_invariants.py` if it fits better):

```python
def test_must_keep_events_are_allowlisted():
    """An Event the wiki has a page for, or that a GM ruling or important:
    names, must stay a concept -- anchoring it would delete its file."""
    from pnp_okf.resolve import _registry_data, load_event_concepts
    data = _registry_data(REGISTRY)
    allow = load_event_concepts(REGISTRY)
    must = {c for c in (data.get("important") or []) if str(c).startswith("events/")}
    assert must <= allow, sorted(must - allow)
```

(Use the module's existing `REGISTRY` constant name; adapt if it differs.)

### 10. Verify (offline)

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
```

Expect bundle-level tests that count events (link coverage, subtype index)
to keep passing against the **old** committed bundle. They only see the
change after the HUMAN RUN. List any that will need a baseline move.

### 11. Commit and PR

Two commits:
1. `feat(kb): render non-arc events as session anchors` (code and tests)
2. `chore(knowledge): add the GM-approved event_concepts allowlist`
   (rules file and audit report)

## HUMAN RUN (after merge)

```bash
cd services/kb
.venv/Scripts/python.exe -m pnp_okf.cli run --estimate ...   # must be ~0 extraction/synthesis calls
.venv/Scripts/python.exe -m pnp_okf.cli run --allow-prune ...
```

- Expect ~280 files pruned under `events/`, ~280 new `retired:` registry
  entries, 0 dangling links (validate gates it), and a modest rise in
  `dropped_links` (links to retired events become plain text).
- Write `docs/audits/<date>-event-anchor-prune.md` in the style of
  `2026-09-22-rename-guard-override.md`: what was pruned, why, counts
  before/after, and how to roll back (`git checkout <ref> -- knowledge/`).
- Re-baseline any ratchet the run moves, with a comment naming this plan.
- In pnp-export-data, run stage 02 and check that "Verhandlung mit Harl" is
  still planned as `update`.

## Done when

- [ ] Allowlist approved by the GM and merged.
- [ ] Bundle re-emitted: `events/` holds only allowlisted ids; sessions have `# Ereignisse`.
- [ ] Validate integrity green; audit note committed.
- [ ] Wiki plan still contains the Harl page.

## Out of scope

- Evidence flags on anchors (T5/T7 add `beobachtet` / `behauptet`).
- Changing the extraction prompt's event instructions (B2).
