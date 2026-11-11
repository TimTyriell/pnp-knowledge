"""Behavior checks for isolated campaign authoring; never invokes a model."""

import io
import zipfile

import app
import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PNP_WORKSPACE_DIR", str(tmp_path / "campaigns"))
    with TestClient(app.app, client=("127.0.0.1", 45000)) as http:
        yield http


def campaign(client):
    response = client.post("/api/workspaces", json={"name": "Copper Coast"})
    assert response.status_code == 201, response.text
    return response.json()


def add_entry(client, workspace, **overrides):
    data = {
        "base_revision": workspace["revision"],
        "title": "Mara",
        "type": "NPC",
        "body": "Owns the Copper Lantern.",
        "aliases": [],
        "related": [],
        **overrides,
    }
    response = client.post(f"/api/workspaces/{workspace['id']}/entries", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_create_edit_reopen_and_keep_identity(client):
    workspace = add_entry(client, campaign(client))
    entry = workspace["entries"][0]
    response = client.put(
        f"/api/workspaces/{workspace['id']}/entries/{entry['concept']}",
        json={
            "base_revision": workspace["revision"],
            "title": "Mara Silberhand",
            "type": "NPC",
            "body": "A GM correction.",
            "aliases": ["Mara"],
            "related": [],
        },
    )
    assert response.status_code == 200, response.text
    reopened = client.get(f"/api/workspaces/{workspace['id']}").json()
    assert reopened["entries"][0]["concept"] == entry["concept"]
    assert reopened["entries"][0]["body"] == "A GM correction."
    assert reopened["entries"][0]["title"] == "Mara Silberhand"


def test_contended_workspace_lock_is_a_conflict_and_can_be_reacquired(tmp_path):
    from workbench import WorkbenchError, workspace_lock

    with workspace_lock(tmp_path):
        with pytest.raises(WorkbenchError) as conflict:
            with workspace_lock(tmp_path):
                pytest.fail("A second writer must not acquire the workspace lock")
        assert conflict.value.status == 409
    with workspace_lock(tmp_path):
        pass
    assert (tmp_path / ".lock").read_bytes() == b"0"


def test_stale_edit_does_not_overwrite_newer_content(client):
    original = campaign(client)
    changed = add_entry(client, original)
    response = client.post(
        f"/api/workspaces/{original['id']}/entries",
        json={
            "base_revision": original["revision"],
            "title": "Lost",
            "type": "NPC",
            "body": "Stale",
        },
    )
    assert response.status_code == 409
    assert client.get(f"/api/workspaces/{original['id']}").json()["revision"] == changed["revision"]


def test_related_entry_and_export_import_preserve_content(client):
    workspace = add_entry(client, campaign(client), title="Copper Lantern", type="Location")
    workspace = add_entry(client, workspace, related=[workspace["entries"][0]["concept"]])
    exported = client.get(f"/api/workspaces/{workspace['id']}/export")
    assert exported.status_code == 200
    imported = client.post(
        "/api/workspaces/import?name=Reopened", content=exported.content, headers={"Content-Type": "application/zip"}
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["entries"] == workspace["entries"]


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for path, text in files.items():
            zipped.writestr(path, text)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "files",
    [
        {"../escape.md": "bad"},
        {"C:/escape.md": "bad"},
        {"npcs/mara.md": "---\ntype: NPC\ntitle: [bad\n---\ntext"},
    ],
)
def test_unsafe_imports_do_not_publish_workspace(client, files):
    response = client.post(
        "/api/workspaces/import?name=Bad", content=archive(files), headers={"Content-Type": "application/zip"}
    )
    assert response.status_code == 400, response.text
    assert client.get("/api/workspaces").json() == []


def test_import_preserves_unknown_frontmatter_and_auxiliary_files(client):
    raw = (
        "---\ntype: NPC\nid: NPC_MARA\ntitle: Mara\ndescription: Innkeeper\n"
        "tags: [npcs]\ntimestamp: '2026-11-03T00:00:00Z'\ncustom: {secret: true}\n"
        "---\n\nOriginal text.\n"
    )
    files = {"bundle/coast/npcs/mara.md": raw, "entity_rules.yaml": "important: [npcs/mara]\n"}
    response = client.post("/api/workspaces/import?name=Imported", content=archive(files))
    assert response.status_code == 201, response.text
    exported = client.get(f"/api/workspaces/{response.json()['id']}/export")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as zipped:
        assert zipped.read("bundle/coast/npcs/mara.md").decode() == raw
        assert zipped.read("entity_rules.yaml").decode() == files["entity_rules.yaml"]


def test_source_saved_and_duplicate_submission_reuses_source(client):
    workspace = campaign(client)
    payload = {"title": "Session one", "date": "2026-11-03", "text": "Mara helped us escape."}
    url = f"/api/workspaces/{workspace['id']}/sources"
    first = client.post(url, json=payload)
    second = client.post(url, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["sources"][0]["id"] == second.json()["sources"][0]["id"]
    assert len(second.json()["sources"]) == 1


def test_restore_keeps_a_new_history_entry(client):
    original = campaign(client)
    changed = add_entry(client, original)
    restored = client.post(
        f"/api/workspaces/{original['id']}/restore",
        json={
            "base_revision": changed["revision"],
            "revision": original["revision"],
        },
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["entries"] == []
    assert restored.json()["revision"] not in (changed["revision"], original["revision"])
    assert len(restored.json()["history"]) == 3


def test_cross_site_writes_are_rejected(client):
    response = client.post(
        "/api/workspaces", json={"name": "Unwanted"}, headers={"Origin": "https://untrusted.example"}
    )
    assert response.status_code == 403


def test_remote_writes_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PNP_WORKSPACE_DIR", str(tmp_path))
    with TestClient(app.app, client=("192.0.2.10", 123)) as remote:
        assert remote.post("/api/workspaces", json={"name": "Remote"}).status_code == 403


def test_broken_relationship_does_not_change_revision(client):
    workspace = campaign(client)
    response = client.post(
        f"/api/workspaces/{workspace['id']}/entries",
        json={
            "base_revision": workspace["revision"],
            "title": "Mara",
            "type": "NPC",
            "body": "Innkeeper",
            "related": ["locations/missing"],
        },
    )
    assert response.status_code == 400
    assert client.get(f"/api/workspaces/{workspace['id']}").json()["revision"] == workspace["revision"]


def prepared_job(client, workspace, monkeypatch, mentions):
    import workbench
    from pnp_okf.models import SessionExtraction

    response = client.post(
        f"/api/workspaces/{workspace['id']}/sources",
        json={
            "title": "Session one",
            "date": "2026-11-03",
            "text": "Mara helped us escape. The tower is old.",
        },
    )
    source = response.json()["sources"][0]
    # Only process creation is replaced. Actual extraction-result handling and all saves run.
    import workbench_api

    monkeypatch.setattr(workbench_api, "start_worker", lambda *args: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-never-sent")
    job_response = client.post(
        f"/api/workspaces/{workspace['id']}/sources/{source['id']}/process", json={"consent": True}
    )
    assert job_response.status_code == 202, job_response.text
    job = job_response.json()["jobs"][-1]
    store = workbench.WorkspaceStore(workbench_api.workspace_root())
    workbench.process_job(
        store.root,
        workspace["id"],
        job["id"],
        extractor=lambda *_: SessionExtraction(
            recap="The party escaped.",
            entities=mentions,
        ),
    )
    return store.view(workspace["id"]), source


def test_review_updates_preserve_gm_text_and_rejected_additions(client, monkeypatch):
    workspace = add_entry(client, campaign(client), body="GM ruling: Mara owns the inn.")
    workspace, source = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "Mara", "type": "NPC", "note": "Helped the party escape.", "citation_ts": "00:00:00"},
            {"name": "Old Tower", "type": "Location", "note": "An old tower.", "citation_ts": "00:00:00"},
        ],
    )
    proposals = {p["title"]: p for p in workspace["proposals"]}
    response = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": workspace["revision"],
            "decisions": [
                {"id": proposals["Mara"]["id"], "action": "accept", "body": "Opened the cellar door."},
                {"id": proposals["Old Tower"]["id"], "action": "reject"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["entries"]) == 1
    body = response.json()["entries"][0]["body"]
    assert body.startswith("GM ruling: Mara owns the inn.")
    assert "Opened the cellar door." in body and "Session one" in body
    repeated = client.post(f"/api/workspaces/{workspace['id']}/sources/{source['id']}/process", json={"consent": True})
    assert repeated.status_code == 202
    assert len(repeated.json()["jobs"]) == 1


def test_ambiguous_identity_requires_an_explicit_choice(client, monkeypatch):
    workspace = add_entry(client, campaign(client), title="Mara", aliases=["The Keeper"])
    workspace = add_entry(client, workspace, title="Mera", aliases=["The Keeper"])
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "The Keeper", "type": "NPC", "note": "Helped us.", "citation_ts": "00:00:00"},
        ],
    )
    proposal = workspace["proposals"][0]
    assert proposal["needs_decision"] is True
    payload = {"base_revision": workspace["revision"], "decisions": [{"id": proposal["id"], "action": "accept"}]}
    url = f"/api/workspaces/{workspace['id']}/review"
    assert client.post(url, json=payload).status_code == 400
    payload["decisions"][0]["target"] = workspace["entries"][0]["concept"]
    assert client.post(url, json=payload).status_code == 200


def test_ambiguous_identity_can_create_a_separate_entry(client, monkeypatch):
    workspace = add_entry(client, campaign(client), title="Mara")
    workspace = add_entry(client, workspace, title="Mera")
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "The Keeper", "type": "NPC", "note": "A different person.", "citation_ts": "00:00:00"},
        ],
    )
    proposal = workspace["proposals"][0]
    response = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": workspace["revision"],
            "decisions": [{"id": proposal["id"], "action": "accept", "target": ""}],
        },
    )
    assert response.status_code == 200, response.text
    assert {entry["title"] for entry in response.json()["entries"]} == {"Mara", "Mera", "The Keeper"}


def test_review_cannot_select_an_entry_outside_suggestion_candidates(client, monkeypatch):
    workspace = add_entry(client, campaign(client), title="Mara")
    workspace = add_entry(client, workspace, title="Other Person")
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "Mara", "type": "NPC", "note": "A note about Mara.", "citation_ts": "00:00:00"},
        ],
    )
    proposal = workspace["proposals"][0]
    unrelated = next(entry for entry in workspace["entries"] if entry["title"] == "Other Person")
    response = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": workspace["revision"],
            "decisions": [{"id": proposal["id"], "action": "accept", "target": unrelated["concept"]}],
        },
    )
    assert response.status_code == 400


def test_rejected_suggestions_survive_export_and_reimport(client, monkeypatch):
    workspace = campaign(client)
    workspace, source = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "Old Tower", "type": "Location", "note": "An old tower.", "citation_ts": "00:00:00"},
        ],
    )
    proposal = workspace["proposals"][0]
    reviewed = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": workspace["revision"],
            "decisions": [{"id": proposal["id"], "action": "reject"}],
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    exported = client.get(f"/api/workspaces/{workspace['id']}/export")
    reopened = client.post("/api/workspaces/import?name=Reopened", content=exported.content)
    assert reopened.status_code == 201, reopened.text
    restored = reopened.json()
    assert restored["proposals"][0]["status"] == "rejected"
    assert restored["jobs"][0]["status"] == "ready"
    assert restored["sources"][0]["id"] == source["id"]
    monkeypatch.setattr("pnp_okf.config.DeepSeekConfig.from_env", lambda: object())
    import workbench_api

    monkeypatch.setattr(workbench_api, "start_worker", lambda *args: None)
    response = client.post(f"/api/workspaces/{restored['id']}/sources/{source['id']}/process", json={"consent": True})
    assert response.status_code == 202
    assert len(response.json()["jobs"]) == 1


def test_restore_requeues_accepted_suggestions_for_review(client, monkeypatch):
    workspace = campaign(client)
    original_revision = workspace["revision"]
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "Old Tower", "type": "Location", "note": "An old tower.", "citation_ts": "00:00:00"},
        ],
    )
    proposal = workspace["proposals"][0]
    accepted = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": workspace["revision"],
            "decisions": [{"id": proposal["id"], "action": "accept"}],
        },
    ).json()
    assert accepted["proposals"][0]["status"] == "accepted"
    restored = client.post(
        f"/api/workspaces/{workspace['id']}/restore",
        json={
            "base_revision": accepted["revision"],
            "revision": original_revision,
        },
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["proposals"][0]["status"] == "pending"
    assert restored.json()["entries"] == []


def test_restore_keeps_only_accepted_evidence_present_in_target_revision(client, monkeypatch):
    workspace = add_entry(client, campaign(client), title="Mara")
    workspace, source = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "Mara", "type": "NPC", "note": "  Evidence A.", "citation_ts": "00:00:00"},
            {"name": "Tower", "type": "Location", "note": "Evidence B.", "citation_ts": "00:00:01"},
            {"name": "Ship", "type": "Item", "note": "Rejected evidence.", "citation_ts": "00:00:02"},
        ],
    )
    proposals = {proposal["title"]: proposal for proposal in workspace["proposals"]}
    reviewed = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": workspace["revision"],
            "decisions": [{"id": proposals["Ship"]["id"], "action": "reject"}],
        },
    ).json()
    after_a = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": reviewed["revision"],
            "decisions": [{"id": proposals["Mara"]["id"], "action": "accept"}],
        },
    ).json()
    after_b = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": after_a["revision"],
            "decisions": [{"id": proposals["Tower"]["id"], "action": "accept"}],
        },
    ).json()

    restored = client.post(
        f"/api/workspaces/{workspace['id']}/restore",
        json={"base_revision": after_b["revision"], "revision": after_a["revision"]},
    )

    assert restored.status_code == 200, restored.text
    by_title = {proposal["title"]: proposal for proposal in restored.json()["proposals"]}
    assert by_title["Mara"]["status"] == "accepted"
    assert by_title["Tower"]["status"] == "pending"
    assert by_title["Ship"]["status"] == "rejected"
    assert restored.json()["sources"][0] == source
    assert "Evidence A." in restored.json()["entries"][0]["body"]


@pytest.mark.parametrize("accept", [False, True])
def test_restore_prunes_missing_suggestion_targets_before_export(client, monkeypatch, accept):
    original = campaign(client)
    workspace = add_entry(client, original, title="Mara")
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [{"name": "Mara", "type": "NPC", "note": "Evidence.", "citation_ts": "00:00:00"}],
    )
    proposal = workspace["proposals"][0]
    assert proposal["candidates"] == [workspace["entries"][0]["concept"]]
    revision = workspace["revision"]
    if accept:
        revision = client.post(
            f"/api/workspaces/{workspace['id']}/review",
            json={
                "base_revision": revision,
                "decisions": [{"id": proposal["id"], "action": "accept"}],
            },
        ).json()["revision"]

    restored = client.post(
        f"/api/workspaces/{workspace['id']}/restore",
        json={"base_revision": revision, "revision": original["revision"]},
    )
    assert restored.status_code == 200, restored.text
    proposal = restored.json()["proposals"][0]
    assert proposal["status"] == "pending"
    assert proposal["target"] is None
    assert proposal["candidates"] == []
    exported = client.get(f"/api/workspaces/{workspace['id']}/export")
    reopened = client.post("/api/workspaces/import?name=Reopened", content=exported.content)
    assert reopened.status_code == 201, reopened.text


def test_restore_adds_existing_pending_target_to_candidates(client, monkeypatch):
    workspace = campaign(client)
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [{"name": "Old Tower", "type": "Location", "note": "Evidence.", "citation_ts": "00:00:00"}],
    )
    proposal = workspace["proposals"][0]
    assert proposal["candidates"] == []
    accepted = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={"base_revision": workspace["revision"], "decisions": [{"id": proposal["id"], "action": "accept"}]},
    ).json()
    target = accepted["entries"][0]
    edited = client.put(
        f"/api/workspaces/{workspace['id']}/entries/{target['concept']}",
        json={
            "base_revision": accepted["revision"],
            "title": target["title"],
            "type": target["type"],
            "body": "GM description without the source evidence.",
            "aliases": target["aliases"],
            "related": target["related"],
        },
    ).json()

    restored = client.post(
        f"/api/workspaces/{workspace['id']}/restore",
        json={"base_revision": edited["revision"], "revision": edited["revision"]},
    )

    assert restored.status_code == 200, restored.text
    reopened = client.post(
        "/api/workspaces/import?name=Reopened",
        content=client.get(f"/api/workspaces/{workspace['id']}/export").content,
    )
    assert reopened.status_code == 201, reopened.text
    restored_proposal = restored.json()["proposals"][0]
    assert restored_proposal["status"] == "pending"
    assert restored_proposal["target"] == target["concept"]
    assert restored_proposal["candidates"] == [target["concept"]]


def test_accepted_note_correction_survives_export_and_restore(client, monkeypatch):
    workspace = campaign(client)
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "Old Tower", "type": "Location", "note": "Model wording.", "citation_ts": "00:00:00"},
        ],
    )
    proposal = workspace["proposals"][0]
    accepted = client.post(
        f"/api/workspaces/{workspace['id']}/review",
        json={
            "base_revision": workspace["revision"],
            "decisions": [{"id": proposal["id"], "action": "accept", "body": "GM correction."}],
        },
    ).json()
    assert accepted["proposals"][0]["body"] == "GM correction."
    exported = client.get(f"/api/workspaces/{workspace['id']}/export")
    reopened = client.post("/api/workspaces/import?name=Reopened", content=exported.content)
    assert reopened.status_code == 201, reopened.text
    reopened_state = reopened.json()
    assert reopened_state["proposals"][0]["body"] == "GM correction."
    assert reopened_state["sources"][0]["text"] == "Mara helped us escape. The tower is old."
    restored = client.post(
        f"/api/workspaces/{reopened_state['id']}/restore",
        json={
            "base_revision": reopened_state["revision"],
            "revision": reopened_state["revision"],
        },
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["proposals"][0]["status"] == "accepted"
    assert restored.json()["proposals"][0]["body"] == "GM correction."


def test_failed_revision_activation_leaves_previous_knowledge(client, monkeypatch):
    import workbench

    workspace = campaign(client)
    real_replace = workbench.os.replace

    def fail_manifest(source, target):
        if str(target).endswith("workspace.json"):
            raise OSError("disk full")
        real_replace(source, target)

    monkeypatch.setattr(workbench.os, "replace", fail_manifest)
    with pytest.raises(OSError, match="disk full"):
        add_entry(client, workspace)
    assert client.get(f"/api/workspaces/{workspace['id']}").json()["entries"] == []


def test_failed_extraction_leaves_accepted_knowledge_and_safe_error(client, monkeypatch):
    import workbench
    import workbench_api

    workspace, _ = prepared_job(client, campaign(client), monkeypatch, [])
    store = workbench.WorkspaceStore(workbench_api.workspace_root())

    def fail(*_):
        raise RuntimeError("secret api key and private text")

    workbench.process_job(store.root, workspace["id"], workspace["jobs"][0]["id"], extractor=fail)
    state = store.view(workspace["id"])
    assert state["entries"] == []
    assert state["jobs"][0]["status"] == "failed"
    assert "secret" not in state["jobs"][0]["error"]


def test_processing_requires_consent_and_provider_configuration(client, monkeypatch):
    workspace = campaign(client)
    workspace = client.post(
        f"/api/workspaces/{workspace['id']}/sources",
        json={
            "title": "Session",
            "date": "2026-11-03",
            "text": "Mara helped.",
        },
    ).json()
    source = workspace["sources"][0]
    url = f"/api/workspaces/{workspace['id']}/sources/{source['id']}/process"
    assert client.post(url, json={"consent": False}).status_code == 400
    monkeypatch.setattr(
        "pnp_okf.config.DeepSeekConfig.from_env",
        lambda: (_ for _ in ()).throw(__import__("pnp_okf.config", fromlist=["ConfigError"]).ConfigError("missing")),
    )
    assert client.post(url, json={"consent": True}).status_code == 400


def test_export_includes_sources_for_reopening(client):
    workspace = campaign(client)
    workspace = client.post(
        f"/api/workspaces/{workspace['id']}/sources",
        json={
            "title": "Session one",
            "date": "2026-11-03",
            "text": "Mara helped us escape.",
        },
    ).json()
    exported = client.get(f"/api/workspaces/{workspace['id']}/export")
    reopened = client.post("/api/workspaces/import?name=Reopened", content=exported.content)
    assert reopened.status_code == 201
    assert reopened.json()["sources"][0]["text"] == "Mara helped us escape."


def test_extraction_does_not_match_same_name_with_different_entry_type(client, monkeypatch):
    workspace = add_entry(client, campaign(client), title="Mara", type="Location")
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "Mara", "type": "NPC", "note": "A person called Mara.", "citation_ts": "00:00:00"},
        ],
    )
    proposal = workspace["proposals"][0]
    assert proposal["target"] is None
    assert proposal["candidates"] == []
    assert proposal["needs_decision"] is False


def test_character_and_npc_share_identity_matching(client, monkeypatch):
    workspace = add_entry(client, campaign(client), title="Mara", type="Character")
    workspace, _ = prepared_job(
        client,
        workspace,
        monkeypatch,
        [
            {"name": "Mara", "type": "NPC", "note": "Spoke to Mara.", "citation_ts": "00:00:00"},
        ],
    )
    proposal = workspace["proposals"][0]
    assert proposal["target"] == workspace["entries"][0]["concept"]
    assert proposal["needs_decision"] is False


def test_character_and_npc_mentions_with_same_name_group_into_one_proposal(client, monkeypatch):
    workspace, _ = prepared_job(
        client,
        campaign(client),
        monkeypatch,
        [
            {"name": "Mara", "type": "NPC", "note": "The group met Mara.", "citation_ts": "00:00:00"},
            {"name": "Mara", "type": "Character", "note": "Mara joined the party.", "citation_ts": "00:00:00"},
        ],
    )
    assert len(workspace["proposals"]) == 1
    proposal = workspace["proposals"][0]
    assert proposal["type"] == "Character"
    assert "The group met Mara." in proposal["body"]
    assert "Mara joined the party." in proposal["body"]


def test_stale_job_in_other_campaign_does_not_block_new_processing(client, monkeypatch):
    import workbench_api
    from pnp_okf.config import DeepSeekConfig

    monkeypatch.setattr(DeepSeekConfig, "from_env", lambda: object())
    monkeypatch.setattr(workbench_api, "start_worker", lambda *args: None)
    first = campaign(client)
    first = client.post(
        f"/api/workspaces/{first['id']}/sources",
        json={
            "title": "One",
            "date": "2026-11-03",
            "text": "Notes",
        },
    ).json()
    source1 = first["sources"][0]
    assert (
        client.post(
            f"/api/workspaces/{first['id']}/sources/{source1['id']}/process", json={"consent": True}
        ).status_code
        == 202
    )

    second = campaign(client)
    second = client.post(
        f"/api/workspaces/{second['id']}/sources",
        json={
            "title": "Two",
            "date": "2026-11-03",
            "text": "More notes",
        },
    ).json()
    source2 = second["sources"][0]
    response = client.post(f"/api/workspaces/{second['id']}/sources/{source2['id']}/process", json={"consent": True})
    assert response.status_code == 202, response.text
    assert response.json()["jobs"][-1]["status"] == "running"
    first_state = client.get(f"/api/workspaces/{first['id']}").json()
    assert first_state["jobs"][0]["status"] == "failed"


def test_shutdown_terminates_active_worker_processes(monkeypatch):
    import workbench_api

    class Worker:
        stopped = False

        def poll(self):
            return None if not self.stopped else 0

        def terminate(self):
            self.stopped = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.stopped = True

    worker = Worker()
    monkeypatch.setitem(workbench_api._workers, "test-job", worker)
    workbench_api.shutdown_workers()
    assert worker.stopped is True
    assert "test-job" not in workbench_api._workers


def test_imported_crlf_documents_remain_visible(client):
    raw = (
        "---\r\ntype: NPC\r\nid: NPC_MARA\r\ntitle: Mara\r\ndescription: Innkeeper\r\n"
        "tags: [npcs]\ntimestamp: '2026-11-03T00:00:00Z'\r\n---\r\n\r\nOriginal text.\r\n"
    )
    response = client.post("/api/workspaces/import?name=Imported", content=archive({"bundle/coast/npcs/mara.md": raw}))
    assert response.status_code == 201, response.text
    assert response.json()["entries"][0]["title"] == "Mara"
    assert response.json()["entries"][0]["body"].strip() == "Original text."


def test_oversized_combined_model_notes_fail_without_creating_proposals(client, monkeypatch):
    import workbench
    from pnp_okf.models import SessionExtraction

    workspace = campaign(client)
    workspace = client.post(
        f"/api/workspaces/{workspace['id']}/sources",
        json={
            "title": "Session",
            "date": "2026-11-03",
            "text": "A short source.",
        },
    ).json()
    source = workspace["sources"][0]
    monkeypatch.setattr("pnp_okf.config.DeepSeekConfig.from_env", lambda: object())
    import workbench_api

    monkeypatch.setattr(workbench_api, "start_worker", lambda *args: None)
    workspace = client.post(
        f"/api/workspaces/{workspace['id']}/sources/{source['id']}/process", json={"consent": True}
    ).json()
    store = workbench.WorkspaceStore(workbench_api.workspace_root())
    result = SessionExtraction(
        recap="Recap",
        entities=[
            {"name": "A", "type": "NPC", "note": "x" * 70_000, "citation_ts": "00:00:00"},
            {"name": "B", "type": "NPC", "note": "y" * 70_000, "citation_ts": "00:00:00"},
        ],
    )
    workbench.process_job(store.root, workspace["id"], workspace["jobs"][0]["id"], extractor=lambda *_: result)
    failed = store.view(workspace["id"])
    assert failed["jobs"][0]["status"] == "failed"
    assert failed["proposals"] == []


@pytest.mark.parametrize("metadata", ["[]", "null", '"text"'])
def test_import_rejects_non_object_workspace_metadata(client, metadata):
    response = client.post(
        "/api/workspaces/import?name=Bad",
        content=archive(
            {
                "bundle/coast/npcs/mara.md": "---\ntype: NPC\nid: NPC_MARA\ntitle: Mara\n---\nNotes\n",
                "campaign-workbench.json": metadata,
            }
        ),
    )
    assert response.status_code == 400
    assert client.get("/api/workspaces").json() == []


def test_import_rejects_missing_bundle_path_in_metadata(client):
    response = client.post(
        "/api/workspaces/import?name=Bad",
        content=archive(
            {
                "campaign-workbench.json": '{"format":"pnp-workbench-v1","sources":[]}',
            }
        ),
    )
    assert response.status_code == 400


def test_import_rejects_blank_campaign_name(client):
    response = client.post(
        "/api/workspaces/import?name=%20%20",
        content=archive({"bundle/coast/npcs/mara.md": "---\ntype: NPC\ntitle: Mara\n---\nNotes\n"}),
    )
    assert response.status_code in (400, 422)


def test_related_entries_are_written_as_standard_relationships(client):
    workspace = add_entry(client, campaign(client), title="Copper Lantern", type="Location")
    target = workspace["entries"][0]["concept"]
    workspace = add_entry(client, workspace, title="Mara", type="NPC", related=[target])
    exported = client.get(f"/api/workspaces/{workspace['id']}/export")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as zipped:
        path = "bundle/campaign/npcs/mara.md"
        frontmatter = yaml.safe_load(zipped.read(path).decode().split("---", 2)[1])
    assert {edge["target"] for edge in frontmatter["relationships"]} == {target}


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_edit_preserves_rich_relationship_metadata(client, newline):
    common = (
        "type: NPC\nid: NPC_{name}\ntitle: {name}\ndescription: Person\n"
        "tags: [npcs]\ntimestamp: '2026-11-03T00:00:00Z'\ncustom: keep-me\n"
    )
    left_rel = "relationships:\n- target: npcs/bryn\n  kind: sibling\n  note: raised together\n"
    right_rel = "relationships:\n- target: npcs/mara\n  kind: sibling\n  note: raised together\n"
    files = {
        "bundle/coast/npcs/mara.md": f"---\n{common.format(name='MARA')}{left_rel}---\n\nA keeper.\n".replace(
            "\n", newline
        ),
        "bundle/coast/npcs/bryn.md": f"---\n{common.format(name='BRYN')}{right_rel}---\n\nA sibling.\n".replace(
            "\n", newline
        ),
    }
    imported = client.post("/api/workspaces/import?name=Imported", content=archive(files)).json()
    mara = next(entry for entry in imported["entries"] if entry["concept"] == "npcs/mara")
    response = client.put(
        f"/api/workspaces/{imported['id']}/entries/npcs/mara",
        json={
            "base_revision": imported["revision"],
            "title": "Mara Keeper",
            "type": "NPC",
            "body": "Updated description.",
            "aliases": [],
            "related": mara["related"],
        },
    )
    assert response.status_code == 200, response.text
    exported = client.get(f"/api/workspaces/{imported['id']}/export")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as zipped:
        mara_raw = zipped.read("bundle/coast/npcs/mara.md").decode()
        frontmatter = yaml.safe_load(mara_raw.split("---", 2)[1])
        bryn_raw = zipped.read("bundle/coast/npcs/bryn.md").decode()
        bryn_frontmatter = yaml.safe_load(bryn_raw.split("---", 2)[1])
    assert frontmatter["relationships"] == [
        {
            "target": "npcs/bryn",
            "kind": "sibling",
            "note": "raised together",
        }
    ]
    assert frontmatter["id"] == "NPC_MARA"
    assert frontmatter["custom"] == "keep-me"
    assert "Updated description." in mara_raw
    assert bryn_frontmatter["id"] == "NPC_BRYN"
    assert bryn_frontmatter["custom"] == "keep-me"
    assert bryn_frontmatter["relationships"] == [{"target": "npcs/mara", "kind": "sibling", "note": "raised together"}]
    assert "A sibling." in bryn_raw


@pytest.mark.parametrize("removing", [False, True])
def test_crlf_relationship_updates_preserve_target_and_unedited_file(client, removing):
    newline = "\r\n"
    common = "description: Keep this field\ntimestamp: '2026-11-03T00:00:00Z'\ncustom: keep-me\n"
    source_edges = (
        "workbench_related: [locations/tower]\nrelationships:\n- target: locations/tower\n  workbench_managed: true\n"
        if removing
        else ""
    )
    target_edges = "relationships:\n- target: npcs/mara\n  workbench_managed: true\n" if removing else ""
    files = {
        "bundle/coast/npcs/mara.md": (
            f"---\ntype: NPC\nid: NPC_MARA\ntitle: Mara\ntags: [npcs]\n{common}{source_edges}---\n\nMara body.\n"
        ).replace("\n", newline),
        "bundle/coast/locations/tower.md": (
            "---\ntype: Location\nid: LOC_TOWER\ntitle: Tower\ntags: [locations]\n"
            f"{common}{target_edges}---\n\nTower body.\n"
        ).replace("\n", newline),
        "bundle/coast/items/key.md": (
            f"---\ntype: Item\nid: ITEM_KEY\ntitle: Key\ntags: [items]\n{common}---\n\nUntouched item.\n"
        ).replace("\n", newline),
    }
    imported_response = client.post("/api/workspaces/import?name=Imported", content=archive(files))
    assert imported_response.status_code == 201, imported_response.text
    imported = imported_response.json()
    mara = next(entry for entry in imported["entries"] if entry["concept"] == "npcs/mara")
    target = "locations/tower" if not removing else None
    response = client.put(
        f"/api/workspaces/{imported['id']}/entries/npcs/mara",
        json={
            "base_revision": imported["revision"],
            "title": mara["title"],
            "type": mara["type"],
            "body": mara["body"],
            "aliases": mara["aliases"],
            "related": [target] if target else [],
        },
    )
    assert response.status_code == 200, response.text
    exported = client.get(f"/api/workspaces/{imported['id']}/export")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as zipped:
        mara_raw = zipped.read("bundle/coast/npcs/mara.md")
        tower_raw = zipped.read("bundle/coast/locations/tower.md")
        untouched = zipped.read("bundle/coast/items/key.md")
    mara_fm = yaml.safe_load(mara_raw.decode().split("---", 2)[1])
    tower_fm = yaml.safe_load(tower_raw.decode().split("---", 2)[1])
    expected = {"locations/tower"} if target else set()
    assert {edge["target"] for edge in mara_fm.get("relationships", [])} == expected
    assert {edge["target"] for edge in tower_fm.get("relationships", [])} == ({"npcs/mara"} if target else set())
    assert mara_fm["custom"] == tower_fm["custom"] == "keep-me"
    assert "Mara body." in mara_raw.decode() and "Tower body." in tower_raw.decode()
    assert untouched == files["bundle/coast/items/key.md"].encode()


def test_import_rejects_malformed_relationship_edges(client):
    malformed = "---\ntype: NPC\nid: NPC_MARA\ntitle: Mara\nrelationships: [bad]\n---\nNotes\n"
    response = client.post(
        "/api/workspaces/import?name=Bad",
        content=archive(
            {
                "bundle/coast/npcs/mara.md": malformed,
            }
        ),
    )
    assert response.status_code == 400
