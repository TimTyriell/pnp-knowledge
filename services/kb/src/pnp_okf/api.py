"""Read-only HTTP API over the knowledge bundle (ARCHITECTURE §4.1, P2).

A thin FastAPI layer: concepts are read from the working tree (current
knowledge) or from a git ref (``?as_of=s26`` — the temporal model from
ADR-001), changes come from ``git diff``, conflicts from the
``knowledge/conflicts/`` queue. No writes — knowledge changes only ever
arrive via reviewed ingest branches.

Run:  python -m pnp_okf.api   (binds 127.0.0.1 only; single-operator setup)
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query

_RESERVED = {"index.md", "log.md"}


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


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}, parts[2]
    return (fm if isinstance(fm, dict) else {}), parts[2].strip()


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


def create_app(bundle_dir: Path | None = None) -> FastAPI:
    reader = BundleReader(bundle_dir or _default_bundle_dir())
    conflicts_dir = (
        reader.bundle_dir.parent.parent / "conflicts"
        if reader.bundle_dir.parent.name == "bundle"
        else reader.bundle_dir.parent / "conflicts"
    )
    app = FastAPI(title="pnp-kb", description="Read-only campaign knowledge API")

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

    return app


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8070)


if __name__ == "__main__":  # pragma: no cover
    main()
