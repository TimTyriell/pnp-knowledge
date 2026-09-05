"""pnp-dashboard — status view over pnp-crawl, pnp-kb, pnp-export-data, plus
a Glossar tab over the KB's entity naming.

Run:  python app.py   (binds 127.0.0.1:8090)

Status reads two local status.json files (siblings repos, paths configurable
via env) and one live HTTP call to the KB API — never writes to any of the
three source repos. See ../../docs/architecture/status-schema.md for that
contract.

The Glossar tab is the one exception: POST /api/glossary/edits writes to
knowledge/entity_rules.yaml, in THIS repo (not a sibling), loopback-only,
validated before write, and never touches knowledge/bundle/ or
entity_registry.yaml — the pipeline stays the only writer of those. See
services/dashboard/README.md.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import glossary
import merge
import rules_edit
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../pnp-knowledge/services/dashboard -> pnp-knowledge/

CRAWL_DIR = Path(os.environ.get("PNP_CRAWL_DIR", REPO_ROOT.parent / "pnp-crawl")).expanduser()
EXPORT_DIR = Path(os.environ.get("PNP_EXPORT_DIR", REPO_ROOT.parent / "pnp-export-data")).expanduser()
KB_URL = os.environ.get("PNP_KB_URL", "http://127.0.0.1:8070")
KNOWLEDGE_DIR = Path(os.environ.get("PNP_KNOWLEDGE_DIR", REPO_ROOT / "knowledge")).expanduser()

CRAWL_STATUS = CRAWL_DIR / "status" / "status.json"
CRAWL_HISTORY = CRAWL_DIR / "status" / "history.jsonl"
EXPORT_STATUS = EXPORT_DIR / "status" / "status.json"
EXPORT_HISTORY = EXPORT_DIR / "status" / "history.jsonl"
RULES_PATH = KNOWLEDGE_DIR / "entity_rules.yaml"
REGISTRY_PATH = KNOWLEDGE_DIR / "entity_registry.yaml"
EPISODES_PATH = KNOWLEDGE_DIR / "episodes.yaml"

WEB_DIST = Path(__file__).parent / "web" / "dist"

app = FastAPI(title="pnp-dashboard")


@app.get("/api/status")
def status() -> dict:
    return merge.build(CRAWL_STATUS, EXPORT_STATUS, KB_URL, EPISODES_PATH)


@app.get("/api/episodes")
def episodes() -> dict:
    """The campaign's episode list — knowledge/episodes.yaml, read-only.

    Kept out of /api/status because it changes once per session, not every
    10 seconds, and the frontend fetches it once.
    """
    return merge.load_episodes(EPISODES_PATH)


def _read_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))
    return lines


@app.get("/api/history")
def history(days: int = 90) -> dict:
    """Time series from the two local history.jsonl logs, bucketed by day.

    The KB also keeps its own history.jsonl (services/kb/state/), but it's
    not exposed over HTTP yet — left out here rather than reaching into
    another service's filesystem state directly.
    """
    cutoff = datetime.now(UTC).timestamp() - days * 86400

    def _recent(path: Path) -> list[dict]:
        out = []
        for rec in _read_history(path):
            ts = merge._parse_iso(rec.get("ts"))
            if ts and ts.timestamp() >= cutoff:
                out.append(rec)
        return out

    return {
        "crawl": _recent(CRAWL_HISTORY),
        "export": _recent(EXPORT_HISTORY),
    }


@app.get("/api/glossary")
def glossary_status() -> dict:
    return glossary.build(KNOWLEDGE_DIR, CRAWL_DIR)


@app.post("/api/glossary/edits")
def glossary_edits(payload: dict, request: Request) -> dict:
    """Preview (dry_run, default) or write staged Glossar edits to
    entity_rules.yaml. Loopback-only: this is the one write path the
    dashboard has, so it gets an explicit guard beyond uvicorn already only
    binding 127.0.0.1.
    """
    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Nur lokal erreichbar.")

    edits = payload.get("edits") or []
    dry_run = payload.get("dry_run", True)
    try:
        return rules_edit.sync(
            RULES_PATH,
            REGISTRY_PATH,
            edits,
            dry_run,
            glossary.load_registry,
            glossary.entity_name_sources,
        )
    except rules_edit.EditConflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except yaml.YAMLError as exc:
        raise HTTPException(500, detail=f"Validierung fehlgeschlagen: {exc}") from exc


if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8090)


if __name__ == "__main__":
    main()
