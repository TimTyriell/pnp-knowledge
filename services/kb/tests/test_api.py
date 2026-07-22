"""Offline tests for the read-only KB API (temp git repo, no network/LLM)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pnp_okf.api import create_app


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


_HEXE_V1 = """---
type: NPC
id: NPC_HEXE
title: Die Hexe
description: Antagonistin.
tags:
- npcs
---

Die Hexe lebt im Sumpf.
"""

_HEXE_V2 = _HEXE_V1.replace("im Sumpf", "in Hartwacht")

_LINDO = """---
type: Character
id: CHAR_LINDO_LAUT
title: Lindo Laut
tags:
- characters
---

Barde.
"""

_CONFLICT = """---
type: Conflict
status: open
concept: npcs/hexe
---

Beleg [1] sagt tot, Beleg [2] sagt lebendig.
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, "knowledge/bundle/camp/npcs/hexe.md", _HEXE_V1)
    _write(tmp_path, "knowledge/bundle/camp/characters/lindo_laut.md", _LINDO)
    _write(tmp_path, "knowledge/bundle/camp/index.md", "# Index\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "s01")
    _git(tmp_path, "tag", "s01")
    _write(tmp_path, "knowledge/bundle/camp/npcs/hexe.md", _HEXE_V2)
    _write(
        tmp_path,
        "knowledge/bundle/camp/locations/hartwacht.md",
        "---\ntype: Location\nid: LOC_HARTWACHT\ntitle: Hartwacht\n---\n\nStadt.\n",
    )
    _write(tmp_path, "knowledge/conflicts/npcs__hexe.md", _CONFLICT)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "s02")
    _git(tmp_path, "tag", "s02")
    return tmp_path


@pytest.fixture()
def client(repo: Path) -> TestClient:
    return TestClient(create_app(repo / "knowledge" / "bundle" / "camp"))


def test_health_lists_session_tags(client: TestClient):
    data = client.get("/health").json()
    assert data["ok"] is True
    assert data["session_tags"] == ["s01", "s02"]


def test_get_concept_by_path_and_typed_id(client: TestClient):
    by_path = client.get("/concepts/npcs/hexe").json()
    by_id = client.get("/concepts/NPC_HEXE").json()
    assert by_path["concept"] == by_id["concept"] == "npcs/hexe"
    assert "Hartwacht" in by_path["body_md"]
    assert by_path["frontmatter"]["title"] == "Die Hexe"


def test_as_of_reads_historic_state(client: TestClient):
    old = client.get("/concepts/NPC_HEXE", params={"as_of": "s01"}).json()
    assert "Sumpf" in old["body_md"]
    # Hartwacht did not exist at s01.
    assert client.get("/concepts/LOC_HARTWACHT", params={"as_of": "s01"}).status_code == 404
    assert client.get("/concepts/LOC_HARTWACHT").status_code == 200


def test_list_concepts_filters_and_skips_reserved(client: TestClient):
    all_concepts = client.get("/concepts").json()
    assert {c["concept"] for c in all_concepts} == {
        "npcs/hexe",
        "characters/lindo_laut",
        "locations/hartwacht",
    }
    npcs = client.get("/concepts", params={"type": "NPC"}).json()
    assert [c["id"] for c in npcs] == ["NPC_HEXE"]


def test_changes_between_tags(client: TestClient):
    data = client.get("/changes", params={"since": "s01", "until": "s02"}).json()
    by_concept = {c["concept"]: c["change"] for c in data["changed"]}
    assert by_concept == {
        "npcs/hexe": "updated",
        "locations/hartwacht": "created",
    }

    with_diff = client.get(
        "/changes",
        params={"since": "s01", "until": "s02", "include_diff": "true"},
    ).json()
    hexe = next(c for c in with_diff["changed"] if c["concept"] == "npcs/hexe")
    assert "Hartwacht" in hexe["diff"]


def test_conflicts_queue(client: TestClient):
    data = client.get("/conflicts").json()
    assert len(data) == 1
    assert data[0]["frontmatter"]["status"] == "open"
    assert "lebendig" in data[0]["body_md"]


def test_unknown_id_404(client: TestClient):
    assert client.get("/concepts/NPC_NIEMAND").status_code == 404
