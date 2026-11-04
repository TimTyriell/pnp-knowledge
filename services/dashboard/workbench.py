"""Isolated authoring workspaces. The live knowledge repository is never written."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import sys
import uuid
import zipfile
from contextlib import contextmanager
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath

import yaml
from pnp_okf.models import ID_PREFIX, PERSON_TYPES, TYPE_DIR, EntityType
from pnp_okf.okf import render_document, slugify, split_document
from pnp_okf.validate import validate_bundle
from pydantic import BaseModel, ConfigDict, Field

MAX_SOURCE_CHARS = 120_000
MAX_ARCHIVE = 25 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")


class WorkbenchError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CampaignInput(Payload):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class EntryInput(Payload):
    base_revision: str
    title: str = Field(min_length=1, max_length=200)
    type: EntityType = EntityType.NPC
    body: str = Field(default="", max_length=120_000)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    related: list[str] = Field(default_factory=list, max_length=100)


class SourceInput(Payload):
    title: str = Field(min_length=1, max_length=200)
    date: date
    text: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)


class Decision(Payload):
    id: str
    action: str = Field(pattern="^(accept|reject)$")
    target: str | None = None
    body: str | None = Field(default=None, max_length=120_000)


class ReviewInput(Payload):
    base_revision: str
    decisions: list[Decision] = Field(min_length=1, max_length=1000)


class RestoreInput(Payload):
    base_revision: str
    revision: str


class ProcessInput(Payload):
    consent: bool = False


def now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_name(f".{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def workspace_lock(path: Path):
    # OS locks are released even if a worker is killed; a stale file cannot block recovery.
    with (path / ".lock").open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise WorkbenchError("Campaign is being saved. Please try again.", 409) from exc
        try:
            # Windows also denies reads of a byte locked by another request.
            if not stream.read(1):
                stream.write(b"0")
                stream.flush()
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def safe_member(name: str) -> str:
    parts = PurePosixPath(name).parts
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
    if (
        not parts
        or name.startswith("/")
        or "\\" in name
        or any(
            p in (".", "..")
            or p.startswith(".")
            or p.endswith((".", " "))
            or re.search(r'[<>:"|?*\x00-\x1f]', p)
            or p.split(".")[0].lower() in reserved
            for p in parts
        )
    ):
        raise WorkbenchError("The archive contains an unsafe filename.")
    return "/".join(parts)


class WorkspaceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, wid: str) -> Path:
        if not IDENTIFIER.fullmatch(wid):
            raise WorkbenchError("Campaign not found.", 404)
        path = self.root / wid
        if not (path / "workspace.json").is_file():
            raise WorkbenchError("Campaign not found.", 404)
        return path

    def load(self, wid: str) -> dict:
        return json.loads((self.path(wid) / "workspace.json").read_text(encoding="utf-8"))

    def save(self, state: dict) -> None:
        atomic_json(self.root / state["id"] / "workspace.json", state)

    def files(self, state: dict, revision: str | None = None) -> dict[str, bytes]:
        revision = revision or state["revision"]
        if revision not in {r["revision"] for r in state["history"]}:
            raise WorkbenchError("Saved version not found.", 404)
        root = self.path(state["id"]) / "revisions" / revision
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def publish(self, state: dict, files: dict[str, bytes], message: str) -> None:
        revision = uuid.uuid4().hex
        folder = self.root / state["id"] / "revisions" / revision
        folder.mkdir(parents=True)
        for name, content in files.items():
            target = folder / safe_member(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        bundle = folder / state["bundle"]
        bundle.mkdir(parents=True, exist_ok=True)
        report = validate_bundle(bundle)
        if not report.integrity_ok:
            raise WorkbenchError(
                "Bundle has broken links, duplicate IDs, or invalid relationships. "
                "The previous version is unchanged.\n" + report.summary()[:2000]
            )
        state["revision"] = revision
        state["history"].append({"revision": revision, "message": message, "created_at": now()})
        self.save(state)

    def create(
        self,
        payload: CampaignInput,
        files: dict[str, bytes] | None = None,
        bundle: str = "bundle/campaign",
        sources: list[dict] | None = None,
        jobs: list[dict] | None = None,
        proposals: list[dict] | None = None,
    ) -> dict:
        wid = uuid.uuid4().hex
        (self.root / wid).mkdir()
        state = {
            "id": wid,
            **payload.model_dump(),
            "bundle": bundle,
            "revision": "",
            "history": [],
            "sources": sources or [],
            "jobs": jobs or [],
            "proposals": proposals or [],
        }
        self.publish(state, files or {}, "Campaign created" if files is None else "Bundle imported")
        return self.view(wid)

    def listing(self) -> list[dict]:
        return [
            self.view(p.name, summary=True)
            for p in sorted(self.root.iterdir())
            if p.is_dir() and IDENTIFIER.fullmatch(p.name) and (p / "workspace.json").is_file()
        ]

    def entries(self, state: dict, files: dict[str, bytes] | None = None) -> list[dict]:
        files = self.files(state) if files is None else files
        prefix = state["bundle"].rstrip("/") + "/" if state["bundle"] != "." else ""
        rows = []
        for name, content in sorted(files.items()):
            if not name.startswith(prefix) or not name.endswith(".md") or Path(name).name in ("index.md", "log.md"):
                continue
            fm, body = split_document(content.decode("utf-8-sig").replace("\r\n", "\n"))
            cid = name[len(prefix) : -3]
            if not isinstance(fm.get("title"), str) or not isinstance(fm.get("type"), str):
                raise WorkbenchError(f"Invalid concept document: {name}")
            aliases = fm.get("aliases", [])
            if not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
                raise WorkbenchError(f"Invalid aliases in {name}")
            relationships = fm.get("relationships", [])
            if not isinstance(relationships, list) or any(
                not isinstance(edge, dict) or not isinstance(edge.get("target"), str) for edge in relationships
            ):
                raise WorkbenchError(f"Invalid relationships in {name}")
            related = fm.get("workbench_related", [])
            if not isinstance(related, list) or any(not isinstance(target, str) for target in related):
                raise WorkbenchError(f"Invalid related entries in {name}")
            related = list(dict.fromkeys([*related, *(edge["target"] for edge in relationships)]))
            rows.append(
                {
                    "concept": cid,
                    "title": fm["title"],
                    "type": fm["type"],
                    "body": body,
                    "aliases": aliases,
                    "related": related,
                    "editable": fm["type"] in {t.value for t in EntityType},
                }
            )
        return rows

    def view(self, wid: str, summary: bool = False) -> dict:
        state = self.load(wid)
        entries = self.entries(state)
        if summary:
            return {k: state[k] for k in ("id", "name", "description", "revision")} | {"entry_count": len(entries)}
        return {k: v for k, v in state.items() if k != "bundle"} | {"entries": entries}

    @staticmethod
    def check_revision(state: dict, expected: str) -> None:
        if state["revision"] != expected:
            raise WorkbenchError(
                "Campaign changed since this draft was opened. Reload before saving; your draft is retained.", 409
            )

    def entry_file(self, state: dict, cid: str) -> str:
        return f"{state['bundle']}/{cid}.md".removeprefix("./")

    def put_entry(self, state: dict, files: dict[str, bytes], payload: EntryInput, cid: str | None = None) -> str:
        existing = {e["concept"]: e for e in self.entries(state, files)}
        if cid is not None and cid not in existing:
            raise WorkbenchError("Entry not found.", 404)
        if cid is not None and existing[cid]["type"] != payload.type.value:
            raise WorkbenchError("An existing entry's type cannot be changed here.")
        if any(target not in existing for target in payload.related):
            raise WorkbenchError("A related entry no longer exists. Choose it again.")
        aliases = list(dict.fromkeys(a.strip() for a in payload.aliases if a.strip()))
        if any(len(a) > 200 for a in aliases):
            raise WorkbenchError("An alias is too long.")
        if cid is None:
            cid = f"{TYPE_DIR[payload.type]}/{slugify(payload.title)}"
            if cid in existing:
                cid += "_" + uuid.uuid4().hex[:8]
        filename = self.entry_file(state, cid)
        fm = split_document(files[filename].decode("utf-8-sig"))[0] if filename in files else {}
        typed_id = fm.get("id") or f"{ID_PREFIX[payload.type]}_{cid.split('/')[-1].upper()}"
        old_related = set(fm.get("workbench_related", []))
        relationships = fm.get("relationships", [])
        removed = old_related - set(payload.related)
        relationships = [
            edge for edge in relationships if not (edge.get("target") in removed and edge.get("workbench_managed"))
        ]
        related_targets = {edge["target"] for edge in relationships}
        for target in payload.related:
            if target not in related_targets:
                relationships.append({"target": target, "workbench_managed": True})
        for target in removed:
            target_file = self.entry_file(state, target)
            target_fm, target_body = split_document(files[target_file].decode("utf-8-sig"))
            reverse = target_fm.get("relationships", [])
            filtered = [edge for edge in reverse if not (edge.get("target") == cid and edge.get("workbench_managed"))]
            if len(filtered) != len(reverse):
                target_fm["relationships"] = filtered
                files[target_file] = render_document(target_fm, target_body).encode("utf-8")
        fm.update(
            {
                "type": payload.type.value,
                "id": typed_id,
                "title": payload.title,
                "description": payload.body[:140] or payload.title,
                "tags": fm.get("tags") or [TYPE_DIR[payload.type]],
                "timestamp": now(),
                "aliases": aliases,
                "workbench_related": payload.related,
                "relationships": relationships,
            }
        )
        files[filename] = render_document(fm, payload.body).encode("utf-8")
        for target in payload.related:
            target_file = self.entry_file(state, target)
            target_fm, target_body = split_document(files[target_file].decode("utf-8-sig"))
            reverse = target_fm.get("relationships", [])
            if not any(edge["target"] == cid for edge in reverse):
                reverse.append({"target": cid, "workbench_managed": True})
                target_fm["relationships"] = reverse
                files[target_file] = render_document(target_fm, target_body).encode("utf-8")
        return cid

    def edit(self, wid: str, payload: EntryInput, cid: str | None = None) -> dict:
        with workspace_lock(self.path(wid)):
            state = self.load(wid)
            self.check_revision(state, payload.base_revision)
            files = self.files(state)
            self.put_entry(state, files, payload, cid)
            self.publish(state, files, f"Saved {payload.title}")
        return self.view(wid)

    def add_source(self, wid: str, payload: SourceInput) -> dict:
        with workspace_lock(self.path(wid)):
            state = self.load(wid)
            sid = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()[:32]
            if not any(s["id"] == sid for s in state["sources"]):
                state["sources"].append({"id": sid, **payload.model_dump(mode="json"), "created_at": now()})
                self.save(state)
        return self.view(wid)

    def restore(self, wid: str, payload: RestoreInput) -> dict:
        with workspace_lock(self.path(wid)):
            state = self.load(wid)
            self.check_revision(state, payload.base_revision)
            files = self.files(state, payload.revision)
            restored_ids = {entry["concept"] for entry in self.entries(state, files)}
            for proposal in state["proposals"]:
                if proposal["status"] == "accepted":
                    proposal["status"] = "pending"
                    if proposal["target"] not in restored_ids:
                        proposal["target"] = None
                        proposal["needs_decision"] = bool(proposal["candidates"])
            self.publish(state, files, "Restored earlier version")
        return self.view(wid)

    def export(self, wid: str) -> bytes:
        state = self.load(wid)
        files = self.files(state)
        report = validate_bundle(self.path(wid) / "revisions" / state["revision"] / state["bundle"])
        if not report.integrity_ok:
            raise WorkbenchError("Repair broken bundle links before exporting.")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr(
                "campaign-workbench.json",
                json.dumps(
                    {
                        "format": "pnp-workbench-v1",
                        "bundle": state["bundle"],
                        "sources": state["sources"],
                        "jobs": state["jobs"],
                        "proposals": state["proposals"],
                    },
                    ensure_ascii=False,
                ),
            )
        return buffer.getvalue()

    def import_bundle(self, name: str, data: bytes) -> dict:
        if len(data) > MAX_ARCHIVE:
            raise WorkbenchError("Bundle archive must be at most 25 MB.")
        files: dict[str, bytes] = {}
        seen = set()
        total = 0
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if len(archive.infolist()) > 5000:
                    raise WorkbenchError("Bundle contains too many files.")
                for item in archive.infolist():
                    member = safe_member(item.filename)
                    if item.is_dir():
                        continue
                    if stat.S_ISLNK(item.external_attr >> 16) or member.casefold() in seen:
                        raise WorkbenchError("Bundle contains duplicate paths or symbolic links.")
                    seen.add(member.casefold())
                    total += item.file_size
                    if item.file_size > MAX_FILE or total > MAX_ARCHIVE:
                        raise WorkbenchError("Bundle expands beyond the supported size.")
                    content = archive.read(item)
                    if member.endswith((".md", ".yaml", ".yml")):
                        text = content.decode("utf-8-sig").replace("\r\n", "\n")
                        if member.endswith(".md") and text.startswith("---\n"):
                            parts = text.split("---\n", 2)
                            if len(parts) != 3 or not isinstance(yaml.safe_load(parts[1]), dict):
                                raise WorkbenchError("A Markdown file has invalid frontmatter.")
                    files[member] = content
        except (zipfile.BadZipFile, UnicodeError, yaml.YAMLError, RuntimeError, OSError) as exc:
            raise WorkbenchError("Use a valid ZIP bundle with UTF-8 Markdown and YAML.") from exc
        metadata = {}
        sources = []
        jobs = []
        proposals = []
        if "campaign-workbench.json" in files:
            try:
                metadata = json.loads(files.pop("campaign-workbench.json"))
                if (
                    not isinstance(metadata, dict)
                    or metadata.get("format") != "pnp-workbench-v1"
                    or not isinstance(metadata.get("bundle"), str)
                    or not isinstance(metadata.get("sources"), list)
                    or not isinstance(metadata.get("jobs", []), list)
                    or not isinstance(metadata.get("proposals", []), list)
                ):
                    raise ValueError("Unknown workspace format")
                metadata["bundle"] = safe_member(metadata["bundle"]) if metadata["bundle"] != "." else "."
                if any(len(metadata.get(key, [])) > 5000 for key in ("sources", "jobs", "proposals")):
                    raise ValueError("Workspace metadata is too large")
                for source in metadata["sources"]:
                    payload = SourceInput.model_validate({k: source[k] for k in ("title", "date", "text")})
                    if not IDENTIFIER.fullmatch(source["id"]):
                        raise ValueError("Invalid source identifier")
                    sources.append(
                        {
                            "id": source["id"],
                            **payload.model_dump(mode="json"),
                            "created_at": source.get("created_at", now()),
                        }
                    )
                if len({source["id"] for source in sources}) != len(sources):
                    raise ValueError("Duplicate source identifier")
                source_ids = {source["id"] for source in sources}
                job_ids_seen = set()
                for job in metadata.get("jobs", []):
                    if (
                        not isinstance(job, dict)
                        or not IDENTIFIER.fullmatch(job.get("id", ""))
                        or job.get("source_id") not in source_ids
                        or job.get("status") not in {"running", "ready", "failed"}
                        or job.get("id") in job_ids_seen
                        or any(
                            key in job
                            and job[key] is not None
                            and (not isinstance(job[key], str) or len(job[key]) > limit)
                            for key, limit in (
                                ("created_at", 100),
                                ("finished_at", 100),
                                ("error", 2000),
                                ("recap", MAX_SOURCE_CHARS),
                            )
                        )
                    ):
                        raise ValueError("Invalid job metadata")
                    job_ids_seen.add(job["id"])
                    job = {
                        key: value
                        for key, value in job.items()
                        if key in {"id", "source_id", "status", "created_at", "finished_at", "error", "recap"}
                    }
                    if job["status"] == "running":
                        job.update(
                            status="failed", error="Processing was interrupted during export. Retry this source."
                        )
                    jobs.append(job)
                job_ids = {job["id"] for job in jobs}
                allowed_types = {item.value for item in EntityType}
                proposal_ids_seen = set()
                for proposal in metadata.get("proposals", []):
                    if (
                        not isinstance(proposal, dict)
                        or not IDENTIFIER.fullmatch(proposal.get("id", ""))
                        or proposal.get("source_id") not in source_ids
                        or proposal.get("job_id") not in job_ids
                        or proposal.get("type") not in allowed_types
                        or proposal.get("status") not in {"pending", "accepted", "rejected"}
                        or not isinstance(proposal.get("title"), str)
                        or not proposal["title"].strip()
                        or len(proposal["title"]) > 200
                        or not isinstance(proposal.get("body"), str)
                        or len(proposal["body"]) > MAX_SOURCE_CHARS
                        or not isinstance(proposal.get("candidates"), list)
                        or len(proposal["candidates"]) > 100
                        or any(not isinstance(cid, str) for cid in proposal["candidates"])
                        or proposal.get("id") in proposal_ids_seen
                        or not isinstance(proposal.get("needs_decision"), bool)
                        or (
                            "citation" in proposal
                            and proposal["citation"] is not None
                            and (not isinstance(proposal["citation"], str) or len(proposal["citation"]) > 200)
                        )
                    ):
                        raise ValueError("Invalid proposal metadata")
                    proposal_ids_seen.add(proposal["id"])
                    target = proposal.get("target")
                    if target is not None and not isinstance(target, str):
                        raise ValueError("Invalid proposal target")
                    proposals.append(
                        {
                            key: value
                            for key, value in proposal.items()
                            if key
                            in {
                                "id",
                                "job_id",
                                "source_id",
                                "title",
                                "type",
                                "body",
                                "citation",
                                "target",
                                "candidates",
                                "needs_decision",
                                "status",
                            }
                        }
                    )
            except (ValueError, TypeError, KeyError) as exc:
                raise WorkbenchError("The workspace metadata is invalid.") from exc
        roots = set()
        directories = {*TYPE_DIR.values(), "sessions", "threads"}
        for filename in files:
            parts = PurePosixPath(filename).parts
            if len(parts) >= 2 and parts[-2] in directories and filename.endswith(".md"):
                roots.add("/".join(parts[:-2]) or ".")
        if not roots and metadata:
            roots.add(metadata["bundle"])
        if len(roots) != 1:
            raise WorkbenchError("Choose an archive containing exactly one OKF campaign bundle.")
        bundle = roots.pop()
        if metadata and metadata["bundle"] != bundle:
            raise WorkbenchError("The workspace metadata does not match the bundle path.")
        # Validate the imported shape before exposing any workspace in the listing.
        probe = {"bundle": bundle}
        imported_entries = self.entries(probe, files)
        entry_ids = {entry["concept"] for entry in imported_entries}
        for proposal in proposals:
            if any(target not in entry_ids for target in proposal["candidates"]):
                raise WorkbenchError("The workspace metadata refers to a missing suggestion target.")
            if proposal["status"] == "pending" and proposal["target"] is not None:
                if proposal["target"] not in proposal["candidates"] or proposal["target"] not in entry_ids:
                    raise WorkbenchError("The workspace metadata refers to an invalid suggestion target.")
        return self.create(CampaignInput(name=name), files, bundle, sources, jobs, proposals)

    def review(self, wid: str, payload: ReviewInput) -> dict:
        with workspace_lock(self.path(wid)):
            state = self.load(wid)
            self.check_revision(state, payload.base_revision)
            files = self.files(state)
            proposals = {p["id"]: p for p in state["proposals"]}
            if len({d.id for d in payload.decisions}) != len(payload.decisions):
                raise WorkbenchError("Choose each suggestion only once.")
            for decision in payload.decisions:
                proposal = proposals.get(decision.id)
                if proposal is None or proposal["status"] != "pending":
                    raise WorkbenchError("A suggestion has already been reviewed. Reload the campaign.", 409)
                if decision.action == "reject":
                    proposal["status"] = "rejected"
                    continue
                if decision.target and decision.target not in proposal["candidates"]:
                    raise WorkbenchError("Choose one of the suggested matches or create a separate entry.")
                if proposal["needs_decision"] and decision.target is None:
                    raise WorkbenchError("Choose an existing entry or 'Create a separate entry' first.")
                target = proposal["target"] if decision.target is None else decision.target
                entries = {e["concept"]: e for e in self.entries(state, files)}
                existing = entries.get(target) if target else None
                if target and existing is None:
                    raise WorkbenchError("The selected entry no longer exists.")
                source = next(s for s in state["sources"] if s["id"] == proposal["source_id"])
                note = proposal["body"] if decision.body is None else decision.body.strip()
                if not note:
                    raise WorkbenchError("The accepted note cannot be empty.")
                # Evidence is additive. Never replace a GM description with sampled prose.
                addition = f"### {source['title']} ({source['date']})\n\n{note}"
                body = existing["body"] if existing else ""
                if addition not in body:
                    body = f"{body}\n\n{addition}".strip()
                entry = EntryInput(
                    base_revision=state["revision"],
                    title=existing["title"] if existing else proposal["title"],
                    type=existing["type"] if existing else proposal["type"],
                    body=body,
                    aliases=existing["aliases"] if existing else [],
                    related=existing["related"] if existing else [],
                )
                cid = self.put_entry(state, files, entry, target or None)
                proposal.update(status="accepted", target=cid, body=note)
            self.publish(state, files, f"Reviewed {len(payload.decisions)} suggestions")
        return self.view(wid)


def extract_source(source: dict, cache: Path):
    """The only network boundary. Calls the existing cached KB extractor."""
    from pnp_okf.config import DeepSeekConfig
    from pnp_okf.extract import extract_session
    from pnp_okf.models import Segment, SessionTranscript

    transcript = SessionTranscript(
        session_id=source["id"],
        date=source["date"],
        url="",
        title=source["title"],
        segments=[
            Segment(start=0, end=0, speaker="GM notes", text=source["text"]),
        ],
    )
    return extract_session(transcript, DeepSeekConfig.from_env().for_tier("extract"), cache)


def process_job(root: Path, wid: str, jid: str, extractor=extract_source) -> None:
    store = WorkspaceStore(root)
    try:
        state = store.load(wid)
        job = next(j for j in state["jobs"] if j["id"] == jid)
        source = next(s for s in state["sources"] if s["id"] == job["source_id"])
        result = extractor(source, store.path(wid) / "cache")
        if len(result.entities) > 1000:
            raise WorkbenchError("The extraction returned too many entries. Split the source into smaller sessions.")
        if len(result.recap) > MAX_SOURCE_CHARS or sum(len(item.note) for item in result.entities) > MAX_SOURCE_CHARS:
            raise WorkbenchError("The extraction returned too much text. Split the source into smaller sessions.")
        with workspace_lock(store.path(wid)):
            state = store.load(wid)
            entries = store.entries(state)
            job = next(j for j in state["jobs"] if j["id"] == jid)
            grouped = {}
            for mention in result.entities:
                if not mention.name.strip() or not mention.note.strip() or len(mention.note) > 120_000:
                    continue
                identity_space = "person" if mention.type in PERSON_TYPES else mention.type.value
                key = (identity_space, mention.name.strip().casefold())
                if key in grouped:
                    grouped[key]["body"] += "\n\n" + mention.note
                    if mention.type == EntityType.CHARACTER:
                        grouped[key]["type"] = mention.type.value
                    continue
                candidates = []
                exact = []
                match_types = {mention.type.value}
                if mention.type in PERSON_TYPES:
                    match_types.update(item.value for item in PERSON_TYPES)
                for entry in entries:
                    if entry["type"] not in match_types:
                        continue
                    names = [entry["title"], *entry["aliases"]]
                    if any(n.casefold() == mention.name.strip().casefold() for n in names):
                        exact.append(entry["concept"])
                    elif any(
                        SequenceMatcher(None, n.casefold(), mention.name.casefold()).ratio() >= 0.75 for n in names
                    ):
                        candidates.append(entry["concept"])
                target = exact[0] if len(exact) == 1 else None
                candidates = exact if exact else candidates
                grouped[key] = {
                    "id": uuid.uuid4().hex,
                    "job_id": jid,
                    "source_id": source["id"],
                    "title": mention.name.strip()[:200],
                    "type": mention.type.value,
                    "body": mention.note,
                    "citation": mention.citation_ts,
                    "target": target,
                    "candidates": candidates,
                    "needs_decision": bool(candidates) and target is None,
                    "status": "pending",
                }
            state["proposals"].extend(grouped.values())
            job.update(status="ready", finished_at=now(), recap=result.recap)
            store.save(state)
    except Exception:
        # Provider errors may echo request text or credentials. Keep them out of responses/logs.
        with workspace_lock(store.path(wid)):
            state = store.load(wid)
            job = next(j for j in state["jobs"] if j["id"] == jid)
            job.update(
                status="failed",
                finished_at=now(),
                error=(
                    "Processing failed. Check your provider settings or shorten the source, then retry. "
                    "Your accepted knowledge is unchanged."
                ),
            )
            store.save(state)


if __name__ == "__main__":
    process_job(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
