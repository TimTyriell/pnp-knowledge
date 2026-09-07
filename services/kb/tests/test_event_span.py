"""Events may span a few sittings, but not the whole campaign.

A tournament ran over three sessions and must stay one event; a generic name
like "Vertrag" reappearing 35 sessions later is a different occurrence and
must not be folded into the first one.
"""

from pathlib import Path

import yaml
from pnp_okf.models import (
    EntityMention,
    EntityType,
    SessionExtraction,
    SessionTranscript,
)
from pnp_okf.resolve import resolve_entities


def _run(tmp_path: Path, session_dates, name="Vertrag", merge=None):
    reg = tmp_path / "entity_registry.yaml"
    reg.write_text(yaml.safe_dump({"merge": merge or {}}), encoding="utf-8")
    ex, tr = {}, {}
    for i, date in enumerate(session_dates):
        sid = f"s{i:03d}"
        ex[sid] = SessionExtraction(
            recap="r",
            entities=[
                EntityMention(
                    name=name, type=EntityType.EVENT, note="n", citation_ts="00:01:00"
                )
            ],
        )
        tr[sid] = SessionTranscript(session_id=sid, date=date, url="u")
    return {e.concept_id: e for e in resolve_entities(ex, tr, reg)}


def test_arc_over_three_sessions_stays_one_event(tmp_path: Path):
    ents = _run(tmp_path, ["2026-01-01", "2026-01-08", "2026-01-15"], "Turnier von Willauch")
    assert len(ents) == 1
    assert len(next(iter(ents.values())).mentions) == 3


def test_span_beyond_the_cap_starts_a_new_event(tmp_path: Path):
    ents = _run(tmp_path, ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22"])
    assert len(ents) == 2, "the 4th session exceeds the 3-session span"


def test_far_apart_sessions_never_share_an_event(tmp_path: Path):
    dates = [f"2026-{m:02d}-01" for m in range(1, 11)]
    ents = _run(tmp_path, dates)
    assert len(ents) > 1, "a generic name must not accumulate across the campaign"


def test_explicit_registry_merge_overrides_the_cap(tmp_path: Path):
    dates = [f"2026-{m:02d}-01" for m in range(1, 7)]
    ents = _run(tmp_path, dates, merge={"vertrag": "events/der_eine_vertrag"})
    assert set(ents) == {"events/der_eine_vertrag"}
    assert len(ents["events/der_eine_vertrag"].mentions) == 6
