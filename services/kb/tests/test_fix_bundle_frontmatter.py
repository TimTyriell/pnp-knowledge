"""Regression test for validate.py::fix_bundle's frontmatter exclusion.

fix_bundle used to feed the whole file -- YAML frontmatter included -- to
normalize_body. apply_spellings (links.py) only protects a `](...)` link
target, not a bare URL, so a `spelling:` rule whose key happened to match a
`\\w`-bounded run inside a `resource:` URL (e.g. a `-`-delimited segment of a
YouTube video id) would silently rewrite it -- and episodes.for_url then
fails to match the mangled URL back to its citation. See
test_spellings_apply.py for fix_bundle's other retro-apply behavior -- this
one lives separately because it needs its own tmp bundle with a `resource:`
frontmatter key, and this agent's edit scope doesn't extend to that file.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pnp_okf.validate import fix_bundle, validate_bundle


def test_fix_bundle_does_not_rewrite_a_resource_url(tmp_path: Path):
    bundle = tmp_path / "bundle"
    sessions = bundle / "sessions"
    sessions.mkdir(parents=True)
    # "-" (not a word char) brackets "Lanra" inside the video id, so the
    # apply_spellings word-boundary regex matches it exactly like it would
    # in prose -- this is the shape that corrupted a real URL.
    (sessions / "2025-04-09.md").write_text(
        "---\ntitle: Session 1\nresource: https://www.youtube.com/watch?v=xYz-Lanra-123\n"
        "---\nLanra erschreckt die Gruppe.\n",
        encoding="utf-8",
    )
    registry = tmp_path / "entity_registry.yaml"
    registry.write_text(yaml.safe_dump({"entities": []}), encoding="utf-8")
    rules = tmp_path / "entity_rules.yaml"
    rules.write_text(yaml.safe_dump({"spelling": {"Lanra": "Landra"}}), encoding="utf-8")

    fix_bundle(bundle, registry)

    text = (sessions / "2025-04-09.md").read_text(encoding="utf-8")
    assert "resource: https://www.youtube.com/watch?v=xYz-Lanra-123" in text
    assert "Landra erschreckt" in text  # the body fix still happens


def test_validate_and_fix_agree_on_which_half_carries_links(tmp_path: Path):
    """`pnp validate --fix` has to converge.

    validate_bundle scanned the whole file for links while fix_bundle rewrites
    only the body, so a link-shaped string in frontmatter was reported on every
    run and fixable on none -- leaving integrity_ok false forever, which cli.py
    treats as "this bundle must not be committed".
    """

    bundle = tmp_path / "bundle"
    (bundle / "npcs").mkdir(parents=True)
    # A note quoting a bullet is how one of these ends up in frontmatter.
    (bundle / "npcs" / "hans.md").write_text(
        "---\ntype: NPC\ntitle: Hans\n"
        'relationships:\n- target: npcs/greta\n  note: "[Greta](/npcs/ghost.md): kennt ihn."\n'
        "---\n\nHans lebt hier.\n",
        encoding="utf-8",
    )
    (bundle / "npcs" / "greta.md").write_text(
        "---\ntype: NPC\ntitle: Greta\nrelationships:\n- target: npcs/hans\n---\n\nGreta auch.\n",
        encoding="utf-8",
    )

    before = validate_bundle(bundle)
    fix_bundle(bundle)
    after = validate_bundle(bundle)

    assert before.broken_links == [] and before.dangling_links == []
    assert after.broken_links == [] and after.dangling_links == []
    assert after.integrity_ok
