"""Serve the production app with disposable, fictional data and no provider access."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import sys
import uuid
from pathlib import Path


def prepare(root: Path, scenario: str, unavailable_url: str):
    root.mkdir(parents=True, exist_ok=False)
    for name, folder in {
        "PNP_WORKSPACE_DIR": "workspaces",
        "PNP_KNOWLEDGE_DIR": "knowledge",
        "PNP_CRAWL_DIR": "crawl",
        "PNP_EXPORT_DIR": "export",
    }.items():
        target = root / folder
        target.mkdir()
        os.environ[name] = str(target)
    # Explicit empty values also prevent optional dotenv loading from restoring secrets.
    os.environ.update(DEEPSEEK_API_KEY="", DEEPSEEK_BASE_URL=unavailable_url)
    os.environ["PNP_KB_URL"] = unavailable_url
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    try:
        import app
        import workbench
    except ImportError as exc:
        raise RuntimeError(
            "Browser tests need the dashboard Python dependencies. From services/dashboard run "
            "uv pip install --python .venv/Scripts/python.exe -e ../kb -e '.[dev]' "
            "(Linux: .venv/bin/python), or set PNP_TEST_PYTHON to a prepared interpreter."
        ) from exc
    if not (app.WEB_DIST / "index.html").is_file():
        raise RuntimeError("Production frontend missing. Run npm run build in services/dashboard/web first.")
    # Another agent's build must not remove assets from a running test server.
    static = root / "web"
    shutil.copytree(app.WEB_DIST, static)
    app.app.router.routes[:] = [route for route in app.app.router.routes if getattr(route, "name", None) != "web"]
    app.app.mount("/", app.StaticFiles(directory=str(static), html=True), name="web")
    seed_id = None
    if scenario != "empty":
        original_now = workbench.now
        workbench.now = lambda: "2026-11-04T12:00:00Z"
        try:
            seed_id = seed(workbench, root / "workspaces", scenario)
        finally:
            workbench.now = original_now
    return app.app, seed_id


def seed(workbench, root: Path, scenario: str) -> str:
    from pnp_okf.models import SessionExtraction

    store = workbench.WorkspaceStore(root)
    workspace = store.create(
        workbench.CampaignInput(name="Copper Coast", description="A fictional reference campaign.")
    )
    for title, kind, body in [
        ("Mara", "NPC", "GM ruling: Mara owns the inn."),
        ("Copper Lantern", "Location", "A welcoming inn beside the old harbour."),
        ("Copper Tower", "Location", "An abandoned watchtower above the harbour."),
    ]:
        workspace = store.edit(
            workspace["id"],
            workbench.EntryInput(
                base_revision=workspace["revision"], title=title, type=kind, body=body,
                aliases=["Copper Towr"] if kind == "Location" else [],
            ),
        )
    workspace = store.add_source(
        workspace["id"],
        workbench.SourceInput(
            title="Session one", date="2026-11-03",
            text="Mara helped the party escape. A glass bell rings at dawn. A muddy coin was found near Copper Towr.",
        ),
    )
    state = store.load(workspace["id"])
    jid = uuid.uuid4().hex
    state["jobs"].append({
        "id": jid, "source_id": state["sources"][0]["id"], "status": "running",
        "created_at": workbench.now(), "error": None,
    })
    store.save(state)

    def extract(*_):
        if scenario == "failed":
            raise RuntimeError("Fictional extraction failure")
        return SessionExtraction(recap="The party escaped through the harbour.", entities=[
            {"name": title, "type": kind, "note": note, "citation_ts": "00:00:12"}
            for title, kind, note in [
                ("Mara", "NPC", "Helped the party escape."),
                ("Glass Bell", "Item", "It rings at dawn."),
                ("Muddy Coin", "Item", "A copper token found by the quay."),
                ("Copper Towr", "Location", "A hidden cellar lies beneath it."),
            ]
        ])

    workbench.process_job(root, workspace["id"], jid, extractor=extract)
    return workspace["id"]


async def serve(root: Path, scenario: str):
    # Playwright's descriptive output paths can exceed Windows' legacy MAX_PATH.
    if os.name == "nt" and not str(root).startswith("\\\\?\\"):
        root = Path("\\\\?\\" + str(root))
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener,
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unavailable,
    ):
        # Reserve without listening: no other local service can occupy the KB/provider address.
        unavailable.bind(("127.0.0.1", 0))
        app, seed_id = prepare(root, scenario, f"http://127.0.0.1:{unavailable.getsockname()[1]}")
        import uvicorn

        listener.bind(("127.0.0.1", 0))
        listener.listen()
        server = uvicorn.Server(uvicorn.Config(app, log_level="info", access_log=True))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Browser test server stopped before becoming ready.")
            await asyncio.sleep(0.01)
        print(json.dumps({
            "url": f"http://127.0.0.1:{listener.getsockname()[1]}",
            "root": str(root), "pid": os.getpid(), "seedId": seed_id,
        }), flush=True)
        await task


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=lambda value: Path(value).resolve())
    parser.add_argument("--scenario", choices=("empty", "review", "failed"), default="empty")
    args = parser.parse_args()
    asyncio.run(serve(args.root, args.scenario))
