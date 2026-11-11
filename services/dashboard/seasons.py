"""Season status and the one pipeline run the dashboard may start (docs/plans/S1-season-freeze.md)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import merge
from pnp_okf.frozen import FrozenStore
from pnp_okf.prompts import EXTRACT_PROMPT_VERSION, STATE_PROMPT_VERSION, SYNTH_PROMPT_VERSION

KB_DIR = Path(__file__).resolve().parents[1] / "kb"
KINDS = ("run", "state")
_popen = subprocess.Popen
_run = subprocess.run
_lock = threading.Lock()
_current: dict = {}


class SeasonError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def status(knowledge_dir: Path, transcript_dir: Path) -> dict:
    episodes = merge.load_episodes(knowledge_dir / "episodes.yaml")
    store = FrozenStore.load(knowledge_dir)
    stems = sorted(p.stem for p in transcript_dir.glob("*.json")) if transcript_dir.is_dir() else []
    by_video = {e["video_id"]: str(e.get("season", "")) for e in episodes["episodes"] if e.get("video_id")}
    # Transcript stems end in "_<video_id>" (pnp-crawl naming); no need to open 75 JSON files.
    season_of_stem = {
        s: next((season for video, season in by_video.items() if s.endswith("_" + video)), None) for s in stems
    }
    rows = []
    for key, spec in episodes["seasons"].items():
        manifest = store.manifests.get(key)
        rows.append(
            {
                "key": key,
                "label": spec.get("label", key),
                "episodes": sum(1 for season in by_video.values() if season == key),
                "transcripts": sum(1 for season in season_of_stem.values() if season == key),
                "frozen": None
                if manifest is None
                else {name: manifest.get(name) for name in ("frozen_at", "prompt_versions", "models", "counts")},
            }
        )
    return {
        "current": {"extract": EXTRACT_PROMPT_VERSION, "synth": SYNTH_PROMPT_VERSION, "state": STATE_PROMPT_VERSION},
        "seasons": rows,
        "unlisted_transcripts": [stem for stem, season in season_of_stem.items() if season is None],
        "error": episodes.get("error"),
    }


def _argv(kind: str, thaw: list[str], valid: set[str], estimate: bool) -> list[str]:
    if kind not in KINDS:
        raise SeasonError("Unknown run kind.")
    bad = [season for season in thaw if season not in valid]
    if bad:
        raise SeasonError(f"Unknown season: {', '.join(bad)}")
    argv = [sys.executable, "-m", "pnp_okf.cli", kind]
    if thaw:
        argv += ["--thaw", ",".join(sorted(thaw))]
    if estimate:
        argv.append("--estimate")
    return argv


def running() -> bool:
    proc = _current.get("proc")
    return proc is not None and proc.poll() is None


def estimate(kind: str, thaw: list[str], valid: set[str]) -> dict:
    done = _run(
        _argv(kind, thaw, valid, True),
        cwd=KB_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return {"ok": done.returncode == 0, "output": (done.stdout + done.stderr).strip()}


def freeze(season: str, from_cache: bool, valid: set[str]) -> dict:
    if season not in valid:
        raise SeasonError("Unknown season.", 404)
    with _lock:
        if running():
            raise SeasonError("A pipeline run is in progress.", 409)
        argv = [sys.executable, "-m", "pnp_okf.cli", "freeze", season] + (["--from-cache"] if from_cache else [])
        done = _run(
            argv, cwd=KB_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600
        )
    return {"ok": done.returncode == 0, "output": (done.stdout + done.stderr).strip()}


def start(kind: str, thaw: list[str], valid: set[str]) -> dict:
    argv = _argv(kind, thaw, valid, False)
    with _lock:
        if running():
            raise SeasonError("A pipeline run is already in progress.", 409)
        log_path = KB_DIR / "state" / "ui_run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("w", encoding="utf-8")
        proc = _popen(argv, cwd=KB_DIR, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        _current.update(
            proc=proc,
            kind=kind,
            thaw=sorted(thaw),
            log=log_path,
            started_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
    return current()


def current() -> dict:
    proc = _current.get("proc")
    log_path = _current.get("log")
    tail = ""
    if log_path and Path(log_path).is_file():
        tail = "\n".join(Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()[-40:])
    last_run = None
    last = KB_DIR / "state" / "last_run.json"
    if last.is_file():
        try:
            last_run = json.loads(last.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {
        "running": running(),
        "kind": _current.get("kind"),
        "thaw": _current.get("thaw", []),
        "started_at": _current.get("started_at"),
        "exit_code": None if proc is None else proc.poll(),
        "log_tail": tail,
        "last_run": last_run,
    }
