"""The resolution loop must be repeatable: settled work must not come back."""

from pathlib import Path

import yaml

from pnp_okf.dedup import MergeGroup, load_never_merge, propose
from pnp_okf.emit import prune_conflicts
from pnp_okf.models import CanonicalEntity, EntityType


def _ent(cid, etype=EntityType.CHARACTER):
    return CanonicalEntity(concept_id=cid, type=etype, canonical_name=cid.split("/")[-1])


def test_resolved_conflicts_leave_the_queue(tmp_path: Path):
    for name in ("characters__dodo", "characters__nyrella"):
        (tmp_path / f"{name}.md").write_text(
            "---\ntype: Conflict\nstatus: open\n---\nx", encoding="utf-8"
        )
    # A report living alongside the queue must survive the sweep.
    (tmp_path / "merge_proposals.md").write_text("# report", encoding="utf-8")

    removed = prune_conflicts(tmp_path, {"characters/dodo"})

    assert removed == 1
    assert (tmp_path / "characters__dodo.md").exists()      # still contested
    assert not (tmp_path / "characters__nyrella.md").exists()  # settled
    assert (tmp_path / "merge_proposals.md").exists()       # not a conflict file


def test_rejected_merge_is_not_proposed_again(tmp_path: Path):
    reg = tmp_path / "entity_registry.yaml"
    reg.write_text(
        yaml.safe_dump({"never_merge": [["characters/miko", "characters/myko"]]}),
        encoding="utf-8",
    )
    blocked = load_never_merge(reg)
    assert blocked == [{"characters/miko", "characters/myko"}]

    class _NoLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**_):
                    class M: content = '{"groups": []}'
                    class C: message = M()
                    return type("R", (), {"choices": [C()]})()

    # Myko/Miko score as a near-identical pair forever; the rejection sticks.
    ents = [_ent("characters/miko"), _ent("characters/myko")]
    cfg = type("Cfg", (), {"model": "m"})()
    assert propose(ents, cfg, client=_NoLLM()) != []          # would be proposed...
    assert propose(ents, cfg, client=_NoLLM(), never_merge=blocked) == []  # ...but isn't


def test_never_merge_ignores_unrelated_groups(tmp_path: Path):
    reg = tmp_path / "r.yaml"
    reg.write_text(yaml.safe_dump({"never_merge": [["a/x", "a/y"]]}), encoding="utf-8")
    blocked = load_never_merge(reg)
    g = MergeGroup(concept_ids=["b/p", "b/q"], canonical="b/p")
    assert not any(len(set(g.concept_ids) & b) >= 2 for b in blocked)
