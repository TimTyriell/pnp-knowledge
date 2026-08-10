"""Read-only HTTP API over the knowledge bundle (ARCHITECTURE §4.1, P2).

A thin FastAPI layer: concepts are read from the working tree (current
knowledge) or from a git ref (``?as_of=s26`` — the temporal model from
ADR-001), changes come from ``git diff``, conflicts from the
``knowledge/conflicts/`` queue. No writes — knowledge changes only ever
arrive via reviewed ingest branches.

Run:  python -m pnp_okf.api   (binds 127.0.0.1 only; single-operator setup)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from pnp_okf.okf import split_document

_RESERVED = {"index.md", "log.md"}
_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})")


# --- git plumbing ------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=400, detail=proc.stderr.strip()[:500])
    return proc.stdout


def _repo_root(bundle_dir: Path) -> Path:
    proc = subprocess.run(
        ["git", "-C", str(bundle_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Bundle is not inside a git repo: {bundle_dir}")
    return Path(proc.stdout.strip())


# --- concept reading ---------------------------------------------------------


_split_frontmatter = split_document  # kept as the name the routes below use


class BundleReader:
    """Reads concepts from the working tree or any git ref."""

    def __init__(self, bundle_dir: Path):
        self.bundle_dir = bundle_dir.resolve()
        self.repo_root = _repo_root(self.bundle_dir)
        self.rel_bundle = self.bundle_dir.relative_to(self.repo_root).as_posix()

    # -- listing --

    def concept_paths(self, ref: str | None) -> list[str]:
        """Concept ids (bundle-relative, no .md) at ``ref`` or the worktree."""

        if ref is None:
            files = [
                p.relative_to(self.bundle_dir).as_posix()
                for p in self.bundle_dir.rglob("*.md")
                if p.name not in _RESERVED
            ]
        else:
            out = _git(
                self.repo_root,
                "ls-tree", "-r", "--name-only", ref, "--", self.rel_bundle,
            )
            prefix = self.rel_bundle + "/"
            files = [
                line[len(prefix):]
                for line in out.splitlines()
                if line.endswith(".md")
                and line.rsplit("/", 1)[-1] not in _RESERVED
            ]
        return sorted(f[:-3] for f in files)

    # -- reading --

    def read(self, concept_path: str, ref: str | None) -> tuple[dict, str]:
        """Frontmatter + body for one concept id, or raise 404."""

        rel = f"{self.rel_bundle}/{concept_path}.md"
        if ref is None:
            path = self.repo_root / rel
            if not path.is_file():
                raise HTTPException(status_code=404, detail=f"No concept {concept_path}")
            text = path.read_text(encoding="utf-8")
        else:
            try:
                text = _git(self.repo_root, "show", f"{ref}:{rel}")
            except HTTPException:
                raise HTTPException(
                    status_code=404, detail=f"No concept {concept_path} at {ref}"
                )
        return _split_frontmatter(text)

    # -- typed-id resolution --

    def id_index(self, ref: str | None) -> dict[str, str]:
        """Map frontmatter ``id`` (e.g. NPC_HEXE) -> concept path at ``ref``."""

        if ref is not None:
            return self._id_index_at_ref(ref)
        return self._build_id_index(None)

    @lru_cache(maxsize=32)  # refs are immutable; the worktree is never cached
    def _id_index_at_ref(self, ref: str) -> dict[str, str]:
        return self._build_id_index(ref)

    def _build_id_index(self, ref: str | None) -> dict[str, str]:
        index: dict[str, str] = {}
        for cid in self.concept_paths(ref):
            fm, _ = self.read(cid, ref)
            eid = str(fm.get("id") or "").strip()
            if eid:
                index[eid] = cid
        return index

    def resolve_concept(self, cid: str, ref: str | None) -> str:
        """Accept a concept path (npcs/hexe) or a typed id (NPC_HEXE)."""

        if "/" in cid:
            return cid
        resolved = self.id_index(ref).get(cid)
        if resolved is None:
            raise HTTPException(status_code=404, detail=f"Unknown id {cid}")
        return resolved

    # -- changes --

    def changes(
        self, since: str, until: str = "HEAD", include_diff: bool = False
    ) -> list[dict]:
        out = _git(
            self.repo_root,
            "diff", "--name-status", f"{since}..{until}", "--", self.rel_bundle,
        )
        status_map = {"A": "created", "M": "updated", "D": "deleted"}
        changed: list[dict] = []
        prefix = self.rel_bundle + "/"
        for line in out.splitlines():
            status, _, path = line.partition("\t")
            if not path.endswith(".md") or path.rsplit("/", 1)[-1] in _RESERVED:
                continue
            entry: dict = {
                "concept": path[len(prefix):-3],
                "change": status_map.get(status[:1], status),
            }
            if include_diff:
                entry["diff"] = _git(
                    self.repo_root, "diff", f"{since}..{until}", "--", path
                )
            changed.append(entry)
        return changed


# --- app ---------------------------------------------------------------------


def _default_bundle_dir() -> Path:
    env = os.environ.get("PNP_BUNDLE_DIR")
    if env:
        return Path(env)
    # services/kb/src/pnp_okf/api.py -> monorepo root is four levels up.
    root = Path(__file__).resolve().parents[4]
    return root / "knowledge" / "bundle" / "splitter_des_ewigen"


def _load_last_run() -> dict | None:
    state_dir = Path(os.environ.get("PNP_STATE_DIR", "./state")).expanduser()
    path = state_dir / "last_run.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _video_id_from_resource(resource: str | None) -> str | None:
    if not resource:
        return None
    m = _VIDEO_ID_RE.search(resource)
    return m.group(1) if m else None


def _bundle_fingerprint(bundle_dir: Path) -> tuple[int, float]:
    """Cheap change signal for /status: file count + max mtime over the bundle.

    A handful of stat() calls versus /concepts' full read+YAML-parse of every
    file — /status must stay fast for a 10s dashboard poll.
    """
    mtimes = [p.stat().st_mtime for p in bundle_dir.rglob("*.md") if p.name not in _RESERVED]
    return (len(mtimes), max(mtimes) if mtimes else 0.0)


def create_app(bundle_dir: Path | None = None) -> FastAPI:
    reader = BundleReader(bundle_dir or _default_bundle_dir())
    conflicts_dir = (
        reader.bundle_dir.parent.parent / "conflicts"
        if reader.bundle_dir.parent.name == "bundle"
        else reader.bundle_dir.parent / "conflicts"
    )
    app = FastAPI(title="pnp-kb", description="Read-only campaign knowledge API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8090",
            "http://localhost:8090",
        ],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    _status_cache: dict = {"key": None, "value": None}

    @app.get("/health")
    def health() -> dict:
        head = _git(reader.repo_root, "rev-parse", "--short", "HEAD").strip()
        tags = _git(reader.repo_root, "tag", "--list", "s*").split()
        return {
            "ok": True,
            "bundle": str(reader.bundle_dir),
            "head": head,
            "session_tags": sorted(tags),
        }

    @app.get("/concepts")
    def list_concepts(
        type: str | None = None,  # noqa: A002 - query param name is the API
        tag: str | None = None,
        as_of: str | None = Query(default=None),
    ) -> list[dict]:
        results = []
        for cid in reader.concept_paths(as_of):
            fm, _ = reader.read(cid, as_of)
            if type and str(fm.get("type", "")).lower() != type.lower():
                continue
            if tag and tag not in (fm.get("tags") or []):
                continue
            results.append(
                {
                    "concept": cid,
                    "id": fm.get("id"),
                    "type": fm.get("type"),
                    "title": fm.get("title"),
                    "description": fm.get("description"),
                }
            )
        return results

    @app.get("/concepts/{cid:path}")
    def get_concept(cid: str, as_of: str | None = Query(default=None)) -> dict:
        concept_path = reader.resolve_concept(cid, as_of)
        fm, body = reader.read(concept_path, as_of)
        return {
            "concept": concept_path,
            "as_of": as_of,
            "frontmatter": fm,
            "body_md": body,
        }

    @app.get("/changes")
    def get_changes(
        since: str,
        until: str = "HEAD",
        include_diff: bool = False,
    ) -> dict:
        return {
            "since": since,
            "until": until,
            "changed": reader.changes(since, until, include_diff),
        }

    @app.get("/conflicts")
    def get_conflicts() -> list[dict]:
        if not conflicts_dir.is_dir():
            return []
        out = []
        for path in sorted(conflicts_dir.glob("*.md")):
            fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
            out.append({"file": path.name, "frontmatter": fm, "body_md": body})
        return out

    @app.get("/status")
    def status() -> dict:
        fingerprint = _bundle_fingerprint(reader.bundle_dir)
        if _status_cache["key"] == fingerprint:
            cached = dict(_status_cache["value"])
            cached["generated_at"] = (
                datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            )
            return cached

        counts_by_type: dict[str, int] = {}
        items = []
        for cid in reader.concept_paths(None):
            fm, _ = reader.read(cid, None)
            ctype = str(fm.get("type", ""))
            counts_by_type[ctype] = counts_by_type.get(ctype, 0) + 1
            if ctype != "Session":
                continue
            rel = f"{reader.rel_bundle}/{cid}.md"
            committed_at = _git(
                reader.repo_root, "log", "-1", "--format=%cI", "--", rel
            ).strip() or None
            items.append(
                {
                    "concept": cid,
                    "id": fm.get("id"),
                    "date": cid.rsplit("/", 1)[-1],
                    "video_id": _video_id_from_resource(fm.get("resource")),
                    "episode": fm.get("episode"),
                    "title": fm.get("title"),
                    "quality": fm.get("quality"),
                    "unsicher_ratio": fm.get("unsicher_ratio"),
                    "committed_at": committed_at,
                }
            )

        conflicts_list = []
        actions = []
        if conflicts_dir.is_dir():
            for path in sorted(conflicts_dir.glob("*.md")):
                fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
                entry = {
                    "file": path.name,
                    "id": fm.get("id"),
                    "concept": fm.get("concept"),
                    "title": fm.get("title"),
                    "timestamp": fm.get("timestamp"),
                }
                conflicts_list.append(entry)
                actions.append({"kind": "conflict", "label": fm.get("title"), "ref": path.name})

        head = _git(reader.repo_root, "rev-parse", "--short", "HEAD").strip()
        tags = _git(reader.repo_root, "tag", "--list", "s*").split()

        value = {
            "schema": 1,
            "service": "pnp-kb",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "last_run": _load_last_run(),
            "head": head,
            "session_tags": sorted(tags),
            "counts_by_type": counts_by_type,
            "items": sorted(items, key=lambda r: r["concept"]),
            "conflicts": conflicts_list,
            "actions": actions,
        }
        _status_cache["key"] = fingerprint
        _status_cache["value"] = value
        return value

    return app


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8070)


if __name__ == "__main__":  # pragma: no cover
    main()
