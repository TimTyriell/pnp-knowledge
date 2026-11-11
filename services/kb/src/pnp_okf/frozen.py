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
from datetime import UTC, datetime
from pathlib import Path

from pnp_okf.config import DeepSeekConfig, Paths
from pnp_okf.context import excerpts_for, load_sources, secondary_sources_for, sources_for
from pnp_okf.episodes import Episodes, video_id
from pnp_okf.extract import _frozen_prompt_version, load_cached_extraction
from pnp_okf.ingest import load_transcripts
from pnp_okf.models import CanonicalEntity, EntityType, SessionExtraction, SessionTranscript
from pnp_okf.prompts import STATE_PROMPT_VERSION, SYNTH_PROMPT_VERSION
from pnp_okf.resolve import load_event_concepts, require_rules, resolve_entities
from pnp_okf.synthesize import _cache_key as synth_cache_key
from pnp_okf.synthesize import _cache_path as synth_cache_path

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


def freeze_season(paths: Paths, season: str, cfg: DeepSeekConfig, *, from_cache: bool = False) -> dict:
    """Snapshot one season from the caches into knowledge/frozen/<season>/. No model call."""
    from pnp_okf.state import load_glossary, run_state

    episodes = Episodes.load(paths.episodes_path)
    transcripts = load_transcripts(paths.transcript_dir)
    members = [t for t in transcripts
               if str((episodes.for_url(t.url) or {}).get("season", "")) == season]
    if not members:
        raise FrozenError(f"No transcript belongs to season {season!r} per {paths.episodes_path}.")
    member_ids = {t.session_id for t in members}

    # Default mode reads through the existing freeze, so a re-run only fills gaps.
    # --from-cache thaws this season: the cache is the new truth and overwrites.
    store = FrozenStore.load(paths.knowledge_root, {season} if from_cache else ())
    extract_cfg = cfg.for_tier("extract")
    extractions = {}
    for t in transcripts:
        ex = load_cached_extraction(paths.cache_dir, t, extract_cfg, frozen=store)
        if ex is not None:
            extractions[t.session_id] = ex
    missing = sorted(member_ids - set(extractions))
    if missing:
        raise FrozenError(f"Cannot freeze season {season}: no extraction for {len(missing)} "
                          f"session(s): {', '.join(missing)}. Run `pnp run` first.")

    out = paths.frozen_dir / season
    old = _read(out / "manifest.json") if (out / "manifest.json").is_file() and not from_cache else None

    def put(path: Path, data: dict) -> None:
        if from_cache or not path.exists():
            write_json(path, data)

    for t in members:
        put(out / "extract" / f"{t.session_id}.json", extractions[t.session_id].model_dump(mode="json"))

    require_rules(paths.registry_path)
    tmap = {t.session_id: t for t in transcripts if t.session_id in extractions}
    entities = resolve_entities(extractions, tmap, paths.registry_path)
    event_concepts = load_event_concepts(paths.registry_path)
    sections = load_sources(paths.sources_dir)
    bodies_missing: list[str] = []
    for e in entities:
        if e.tier == "brief" or (e.type == EntityType.EVENT and e.concept_id not in event_concepts):
            continue            # rendered locally / not a concept: nothing to freeze
        if not all(m.session_id in member_ids for m in e.mentions):
            continue
        dest = out / "synth" / f"{safe_name(e.concept_id)}.json"
        if dest.exists() and not from_cache:
            continue
        tier_cfg = cfg.for_tier(e.tier)
        key = synth_cache_key(e, tier_cfg, sources_for(e, sections),
                              excerpts_for(e, tmap) if e.tier == "deep" else "",
                              secondary_sources_for(e, sections))
        src = synth_cache_path(paths.cache_dir, e, key)
        if not src.is_file():
            bodies_missing.append(e.concept_id)
            continue
        write_json(dest, {"fingerprint": mention_fingerprint(e), "body": _read(src)["body"]})

    state_sessions = 0
    rows = load_glossary(paths.knowledge_root)
    if rows:
        run = run_state(transcripts, cfg.for_tier("state"), paths.cache_dir, rows,
                        estimate=True, frozen=store)
        if member_ids <= set(run.states):       # all or nothing: a partial state freeze would fork the ledger
            for sid in sorted(member_ids):
                put(out / "state" / f"{sid}.json", run.states[sid].model_dump(mode="json"))
            state_sessions = len(member_ids)

    def stamp() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    old_shas = {s["session_id"]: s.get("dialogue_sha", "") for s in old["sessions"]} if old else {}
    manifest = {
        "schema": 1,
        "season": season,
        "label": episodes.season_label(season),
        # A gap-filling re-run keeps the original provenance: the data is as old as it was.
        "frozen_at": old["frozen_at"] if old else stamp(),
        "prompt_versions": {
            "extract": old["prompt_versions"]["extract"] if old
            else ",".join(sorted({_frozen_prompt_version(t) for t in members})),
            "synth": old["prompt_versions"]["synth"] if old else SYNTH_PROMPT_VERSION,
            "state": STATE_PROMPT_VERSION if state_sessions else None,
        },
        "models": old["models"] if old else
            {"extract": extract_cfg.model, "deep": cfg.model, "standard": cfg.light_model},
        "sessions": [
            {"session_id": t.session_id, "date": t.date, "video_id": video_id(t.url),
             "episode_id": episodes.id_for_url(t.url),
             "dialogue_sha": old_shas.get(t.session_id) or dialogue_sha(t)}
            for t in sorted(members, key=lambda t: t.session_id)
        ],
        "counts": {
            "sessions": len(members),
            "bodies": len(list((out / "synth").glob("*.json"))) if (out / "synth").is_dir() else 0,
            "bodies_missing": len(bodies_missing),
            "state_sessions": state_sessions,
        },
        "bodies_missing": sorted(bodies_missing),
    }
    write_json(out / "manifest.json", manifest)     # last: the manifest is what makes it frozen (R1)
    return manifest
