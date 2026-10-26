"""Private player-name guard (T8, D1): whole-word hits in the bundle, and the
env-var loader. Fake names only -- the real list is never in the repo.
"""

from __future__ import annotations

import json
from pathlib import Path

from pnp_okf.validate import load_private_player_names, player_name_hits


def test_player_name_hits_finds_title_alias_and_body_but_skips_belege(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "characters").mkdir(parents=True)
    (bundle / "characters" / "alice_pc.md").write_text(
        "---\ntitle: Alice Pc\naliases:\n- Alice (Lindo)\n---\n\n"
        "Alice kämpft.\n\n# Belege\n\n[1] Alice spricht.\n",
        encoding="utf-8",
    )
    (bundle / "characters" / "bob.md").write_text(
        "---\ntitle: Bob\n---\n\nKeine Namen hier. Alicia auch nicht.\n",
        encoding="utf-8",
    )
    hits = player_name_hits(bundle, ["Alice"])
    assert sorted(hits) == [
        ("characters/alice_pc", "alias", "Alice"),
        ("characters/alice_pc", "body", "Alice"),
        ("characters/alice_pc", "title", "Alice"),
    ]


def test_player_name_hits_ignores_short_names(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "npcs").mkdir(parents=True)
    (bundle / "npcs" / "x.md").write_text("---\ntitle: X\n---\n\nAl ist da.\n", encoding="utf-8")
    assert player_name_hits(bundle, ["Al"]) == []


def test_load_private_player_names_reads_env_path(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PNP_ROSTER_PRIVATE", raising=False)
    assert load_private_player_names() is None

    private = tmp_path / "roster_private.json"
    private.write_text(json.dumps({"player_names": ["Alice"]}), encoding="utf-8")
    monkeypatch.setenv("PNP_ROSTER_PRIVATE", str(private))
    assert load_private_player_names() == ["Alice"]

    monkeypatch.setenv("PNP_ROSTER_PRIVATE", str(tmp_path / "missing.json"))
    assert load_private_player_names() is None
