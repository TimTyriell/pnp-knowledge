"""Local HTTP commands and process supervision for the campaign workbench."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from workbench import (
    MAX_ARCHIVE,
    MAX_SOURCE_CHARS,
    CampaignInput,
    EntryInput,
    ProcessInput,
    RestoreInput,
    ReviewInput,
    SourceInput,
    WorkbenchError,
    WorkspaceStore,
    now,
    workspace_lock,
)

_workers: dict[str, subprocess.Popen] = {}
_worker_lock = threading.Lock()


def local_access(request: Request) -> None:
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "The campaign workbench is available on this computer only.")
    host = urlsplit(str(request.url)).hostname
    if host not in ("127.0.0.1", "localhost", "::1", "testserver"):
        raise HTTPException(403, "Use the local application address.")
    if request.method not in ("GET", "HEAD"):
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            allowed = {f"{request.url.scheme}://{request.url.netloc}", "http://localhost:5173", "http://127.0.0.1:5173"}
            if origin not in allowed or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
                raise HTTPException(403, "Open the app locally to make changes.")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Open the app locally to make changes.")


router = APIRouter(prefix="/api/workspaces", dependencies=[Depends(local_access)])


def workspace_root() -> Path:
    return Path(os.environ.get("PNP_WORKSPACE_DIR", Path(__file__).parent / "data" / "workspaces"))


def get_store():
    store = WorkspaceStore(workspace_root())
    try:
        yield store
    except WorkbenchError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(
            422, "The entry exceeds workbench limits. Shorten its text, name, aliases, or connections, then retry."
        ) from exc


Store = Depends(get_store)


@router.get("")
def listing(store: WorkspaceStore = Store):
    return store.listing()


@router.get("/config")
def configuration():
    from pnp_okf.config import ConfigError, DeepSeekConfig

    try:
        cfg = DeepSeekConfig.from_env()
        return {"ai_available": True, "model": cfg.extract_model, "max_source_chars": MAX_SOURCE_CHARS}
    except ConfigError:
        return {"ai_available": False, "model": None, "max_source_chars": MAX_SOURCE_CHARS}


@router.post("", status_code=201)
def create(payload: CampaignInput, store: WorkspaceStore = Store):
    return store.create(payload)


@router.post("/import", status_code=201)
async def import_bundle(
    request: Request, name: str = Query(min_length=1, max_length=120), store: WorkspaceStore = Store
):
    if not name.strip():
        raise HTTPException(422, "Campaign name cannot be blank.")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_ARCHIVE:
            raise HTTPException(413, "Bundle archive must be at most 25 MB.")
    return store.import_bundle(name.strip(), bytes(data))


def recover_jobs(store: WorkspaceStore, wid: str):
    with _worker_lock, workspace_lock(store.path(wid)):
        _recover_workspace(store, wid)
        _prune_workers()


def _recover_workspace(store: WorkspaceStore, wid: str) -> None:
    state = store.load(wid)
    changed = False
    for job in state["jobs"]:
        worker = _workers.get(job["id"])
        if job["status"] == "running" and (worker is None or worker.poll() is not None):
            job.update(
                status="failed", error="Processing was interrupted. Retry this source; cached extraction is reused."
            )
            changed = True
    if changed:
        store.save(state)


def _prune_workers() -> None:
    for jid in list(_workers):
        if _workers[jid].poll() is not None:
            del _workers[jid]


def _recover_all_workspaces(store: WorkspaceStore, locked_wid: str) -> None:
    for item in store.listing():
        if item["id"] == locked_wid:
            _recover_workspace(store, locked_wid)
            continue
        with workspace_lock(store.path(item["id"])):
            _recover_workspace(store, item["id"])
    _prune_workers()


def shutdown_workers() -> None:
    with _worker_lock:
        for jid, worker in list(_workers.items()):
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()
            del _workers[jid]


@router.get("/{wid}")
def workspace(wid: str, store: WorkspaceStore = Store):
    recover_jobs(store, wid)
    return store.view(wid)


@router.post("/{wid}/entries")
def create_entry(wid: str, payload: EntryInput, store: WorkspaceStore = Store):
    return store.edit(wid, payload)


@router.put("/{wid}/entries/{cid:path}")
def update_entry(wid: str, cid: str, payload: EntryInput, store: WorkspaceStore = Store):
    return store.edit(wid, payload, cid)


@router.post("/{wid}/sources", status_code=201)
def add_source(wid: str, payload: SourceInput, store: WorkspaceStore = Store):
    return store.add_source(wid, payload)


@router.post("/{wid}/restore")
def restore(wid: str, payload: RestoreInput, store: WorkspaceStore = Store):
    return store.restore(wid, payload)


@router.get("/{wid}/export")
def export(wid: str, store: WorkspaceStore = Store):
    return Response(
        store.export(wid),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="campaign-bundle.zip"'},
    )


@router.post("/{wid}/review")
def review(wid: str, payload: ReviewInput, store: WorkspaceStore = Store):
    return store.review(wid, payload)


def start_worker(store: WorkspaceStore, wid: str, jid: str):
    _workers[jid] = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("workbench.py")), str(store.root), wid, jid],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


@router.post("/{wid}/sources/{sid}/process", status_code=202)
def process(wid: str, sid: str, payload: ProcessInput, store: WorkspaceStore = Store):
    from pnp_okf.config import ConfigError, DeepSeekConfig

    if not payload.consent:
        raise WorkbenchError("Confirm sending this source to the model provider before processing.")
    with _worker_lock, workspace_lock(store.path(wid)):
        _recover_all_workspaces(store, wid)
        state = store.load(wid)
        if not any(s["id"] == sid for s in state["sources"]):
            raise WorkbenchError("Source not found.", 404)
        previous = next((j for j in reversed(state["jobs"]) if j["source_id"] == sid), None)
        if previous and previous["status"] in ("ready", "running"):
            return store.view(wid)
        try:
            DeepSeekConfig.from_env()
        except ConfigError as exc:
            raise WorkbenchError(
                "AI is not configured. Set DEEPSEEK_API_KEY on this computer; manual authoring remains available."
            ) from exc
        if any(j["status"] == "running" for w in store.listing() for j in store.load(w["id"])["jobs"]):
            raise WorkbenchError(
                "Another source is being processed. Wait for it to finish before starting this one.", 409
            )
        jid = uuid.uuid4().hex
        state["jobs"].append({"id": jid, "source_id": sid, "status": "running", "created_at": now(), "error": None})
        store.save(state)
        try:
            start_worker(store, wid, jid)
        except OSError as exc:
            state["jobs"][-1].update(status="failed", error="The processing worker could not start. Please retry.")
            store.save(state)
            raise WorkbenchError("The processing worker could not start. Please retry.", 503) from exc
    return store.view(wid)
