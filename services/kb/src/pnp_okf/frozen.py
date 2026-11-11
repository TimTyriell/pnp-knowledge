"""Read committed season ground truth for S1-season-freeze.

A manifest's existence defines a frozen season (R1); its sessions bypass paid
extraction calls (R3), and unreadable or incomplete frozen files raise instead
of silently falling back (R5).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path

from pnp_okf.models import CanonicalEntity, SessionExtraction, SessionTranscript

log = logging.getLogger(__name__)

FROZEN_DIRNAME = "frozen"


class FrozenError(RuntimeError):
    """A freeze that exists but cannot be trusted. Never caught to fall back to a paid call."""


def dialogue_sha(transcript: SessionTranscript) -> str:
    return hashlib.sha256(transcript.render_dialogue().encode("utf-8")).hexdigest()[:16]


def mention_fingerprint(entity: CanonicalEntity) -> str:
    rows = sorted((m.session_id, m.citation_ts, m.note) for m in entity.mentions)
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def safe_name(concept_id: str) -> str:
    return concept_id.replace("/", "__")


def write_json(path: Path, data: dict) -> None:
    """temp + os.replace: a kill mid-freeze must not leave a half-written ground truth."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrozenError(f"Frozen file unreadable: {path} ({exc}). Fix or restore it from git; "
                          "the pipeline will not re-buy a frozen session on its own.") from exc


def _validate_manifest(manifest: object, season: str, path: Path) -> dict:
    def invalid(reason: str) -> FrozenError:
        return FrozenError(f"Invalid frozen manifest {path}: {reason}")

    if not isinstance(manifest, dict):
        raise invalid("expected a JSON object")
    if type(manifest.get("schema")) is not int or manifest["schema"] != 1:
        raise invalid("schema must be 1")
    if manifest.get("season") != season:
        raise invalid(f"season must match directory name {season!r}")
    sessions = manifest.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise invalid("sessions must be a non-empty list")
    seen: set[str] = set()
    for item in sessions:
        if not isinstance(item, dict):
            raise invalid("each session must be an object")
        session_id = item.get("session_id")
        if (
            not isinstance(session_id, str)
            or not session_id
            or session_id in {".", ".."}
            or session_id.strip() != session_id
            or session_id.endswith((".", " "))
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in session_id)
        ):
            raise invalid("each session must have a valid filename-safe session_id")
        if session_id in seen:
            raise invalid(f"duplicate session_id {session_id!r}")
        seen.add(session_id)
    return manifest


class FrozenStore:
    def __init__(self, root: Path | None = None, thaw: frozenset[str] = frozenset()) -> None:
        self.root = root
        self.manifests: dict[str, dict] = {}
        self._season_of: dict[str, str] = {}
        self._sha: dict[str, str] = {}
        self._warned: set[str] = set()
        if root is None or not root.is_dir():
            return
        for mpath in sorted(root.glob("*/manifest.json")):
            season = mpath.parent.name
            if "all" in thaw or season in thaw:
                log.warning("[frozen] season %s is thawed for this run", season)
                continue
            manifest = _validate_manifest(_read(mpath), season, mpath)
            self.manifests[season] = manifest
            for s in manifest.get("sessions", []):
                session_id = s["session_id"]
                extraction_path = root / season / "extract" / f"{session_id}.json"
                if not extraction_path.is_file():
                    raise FrozenError(f"Frozen extraction missing: {extraction_path}")
                self._season_of[session_id] = season
                self._sha[session_id] = s.get("dialogue_sha", "")

    @classmethod
    def load(cls, knowledge_root: Path, thaw=()) -> FrozenStore:
        return cls(knowledge_root / FROZEN_DIRNAME, frozenset(thaw))

    def season_of(self, session_id: str) -> str | None:
        return self._season_of.get(session_id)

    def extraction(self, transcript: SessionTranscript) -> SessionExtraction | None:
        season = self._season_of.get(transcript.session_id)
        if season is None:
            return None
        blob = _read(self.root / season / "extract" / f"{transcript.session_id}.json")
        sid = transcript.session_id
        if sid not in self._warned and self._sha.get(sid) and self._sha[sid] != dialogue_sha(transcript):
            self._warned.add(sid)
            log.warning("[frozen] transcript of %s changed since season %s was frozen; "
                        "still using the frozen extraction (--thaw %s to re-read)", sid, season, season)
        return SessionExtraction.model_validate(blob)

    def body(self, entity: CanonicalEntity) -> str | None:
        seasons = {self._season_of.get(m.session_id) for m in entity.mentions}
        if len(seasons) != 1 or None in seasons:
            return None
        path = self.root / next(iter(seasons)) / "synth" / f"{safe_name(entity.concept_id)}.json"
        if not path.is_file():
            return None
        blob = _read(path)
        return blob["body"] if blob.get("fingerprint") == mention_fingerprint(entity) else None

    def state_blob(self, session_id: str) -> dict | None:
        season = self._season_of.get(session_id)
        if season is None:
            return None
        path = self.root / season / "state" / f"{session_id}.json"
        return _read(path) if path.is_file() else None
