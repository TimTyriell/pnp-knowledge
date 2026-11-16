"""Offline one-case extraction golden benchmark (contract: docs/plans/E1-extraction-golden-benchmark.md).

Scores model/effort/prompt configurations against one human-approved gold
reference. This module never launches a model: extraction and grading run on
subscriptions outside Python, and this file only hashes, validates, scores and
reports their files. Campaign data lives under the gitignored bench root.
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import hashlib
import json
import os
import random
import re
import secrets
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

# --- 0. Conventions ---------------------------------------------------------------------

DEFAULT_CASE = "2026-10-28_Team-A_4eyaH3z_QC8"


class BenchError(Exception):
    """Every refusal raises this. main() prints it to stderr and returns 2."""


class _Strict(BaseModel):
    # Gold is hand-edited JSON; a typo'd key must fail loudly, not be ignored.
    model_config = ConfigDict(extra="forbid")


def bench_root() -> Path:
    env = os.environ.get("PNP_BENCH_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / ".cache" / "extraction-benchmark"


# --- 1. Hashing and files ---------------------------------------------------------------


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj) -> str:
    return sha(canon(obj))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _pretty(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def write_once(path: Path, data: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as fh:
            fh.write(data)
        return True
    except FileExistsError:
        if path.read_bytes() == data:
            return False
        raise BenchError(f"refusing to overwrite {path}") from None


def write_json(path: Path, obj) -> None:
    # Mutable files only (reports, disagreement lists, samples).
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pretty(obj))


# --- 2. Case preparation ----------------------------------------------------------------

DEFAULT_RUBRIC = {
    "version": 1,
    "weights": {"F": 0.35, "C": 0.20, "N": 0.20, "E": 0.15, "G": 0.10},
    "tolerance": 2.0,
    "g_window_segments": 2,
    "calibration": {"overall": 0.90, "F": 0.85, "critical_misses": 0},
}


def _hms(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _rubric_path(case_dir: Path) -> Path:
    return case_dir.parent.parent / "rubrics" / "v1.json"


def _source_hash(case_dir: Path) -> str:
    return sha((case_dir / "source.json").read_bytes())


def load_segments(source_json: Path) -> list[dict]:
    return read_json(source_json)["segments"]


def render_dialogue(segments) -> str:
    return "\n".join(
        f"[{_hms(seg['start'])}] {seg['speaker']}: {seg['text'].strip()}" for seg in segments if seg["text"].strip()
    )


def segment_at(segments, seconds: float) -> int:
    index = 0
    for i, seg in enumerate(segments):
        if seg["start"] <= seconds:
            index = i
    return index


def build_prompt(request: dict) -> str:
    system = request["messages"][0]["content"]
    user = request["messages"][1]["content"]
    return (
        "Answer the request below exactly as the model it addresses would. Reply with the JSON object only.\n"
        "Use no tools and no other source of information.\n"
        "\n=== SYSTEM ===\n" + system + "\n\n=== USER ===\n" + user
    )


def prepare(experiment: Path, transcript: Path, case_dir: Path) -> dict:
    manifest = read_json(experiment / "manifest.json")
    transcript_bytes = transcript.read_bytes()
    request_bytes = (experiment / "request.json").read_bytes()
    schema_bytes = (experiment / "schema.json").read_bytes()
    # Every check runs before the first write, so a refusal leaves the case dir untouched.
    if sha(transcript_bytes) != manifest["transcript_sha256"]:
        raise BenchError("transcript sha256 does not match the experiment manifest")
    if sha(request_bytes) != manifest["request_sha256"]:
        raise BenchError("request.json sha256 does not match the experiment manifest")
    if sha(schema_bytes) != manifest["schema_sha256"]:
        raise BenchError("schema.json sha256 does not match the experiment manifest")
    request = json.loads(request_bytes.decode("utf-8"))
    segments = json.loads(transcript_bytes.decode("utf-8"))["segments"]
    dialogue = render_dialogue(segments)
    if dialogue not in request["messages"][1]["content"]:
        raise BenchError("rendered dialogue is not in the request's user message")
    prompt = build_prompt(request)
    case_manifest = {
        "session_id": manifest["session_id"],
        "source_sha256": sha(transcript_bytes),
        "request_sha256": sha(request_bytes),
        "schema_sha256": sha(schema_bytes),
        "prompt_sha256": sha(prompt.encode("utf-8")),
        "segments": len(segments),
    }
    write_once(case_dir / "source.json", transcript_bytes)
    write_once(case_dir / "baseline_request.json", request_bytes)
    write_once(case_dir / "schema.json", schema_bytes)
    write_once(case_dir / "dialogue.txt", dialogue.encode("utf-8"))
    write_once(case_dir / "prompt.txt", prompt.encode("utf-8"))
    write_once(case_dir / "case_manifest.json", _pretty(case_manifest))
    rubric = _rubric_path(case_dir)
    if not rubric.exists():
        write_once(rubric, _pretty(DEFAULT_RUBRIC))
    return case_manifest


# --- 3. Gold ----------------------------------------------------------------------------


class GoldAccepted(_Strict):
    type: str
    subtypes: list[str] | None


class GoldEntity(_Strict):
    id: str
    label: str
    aliases: list[str]
    required: bool
    accepted: list[GoldAccepted]
    evidence: list[str]


class GoldQuote(_Strict):
    segment: str
    quote: str


class GoldFact(_Strict):
    id: str
    statement: str
    scene: str
    subjects: list[str]
    evidence: list[GoldQuote]
    qualifiers: str = ""
    weight: int
    placement: Literal["any", "recap", "notes"] = "any"


class NoteReq(_Strict):
    id: str
    fact: str
    entity: str
    weight: int


class CriticalRule(_Strict):
    id: str
    description: str
    trigger: str
    evidence: list[str]
    rationale: str


class Question(_Strict):
    id: str
    text: str
    segments: list[str]
    items: list[str]


class GoldExcluded(_Strict):
    segments: list[str]
    reason: str


class Gold(_Strict):
    version: int
    entities: list[GoldEntity]
    facts: list[GoldFact]
    notes: list[NoteReq]
    critical: list[CriticalRule]
    questions: list[Question]
    excluded: list[GoldExcluded]


def validate_gold(gold: dict, segments) -> list[str]:
    from pnp_okf.models import EntityType

    try:
        g = Gold.model_validate(gold)
    except ValidationError as exc:
        return [f"schema: {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]

    errors: list[str] = []
    seg_text = {f"S{i:03d}": seg["text"] for i, seg in enumerate(segments)}

    def check_segment(sid: str, where: str) -> None:
        if sid not in seg_text:
            errors.append(f"{where}: unknown segment {sid}")

    for kind, ids in (
        ("entity", [e.id for e in g.entities]),
        ("fact", [f.id for f in g.facts]),
        ("note", [n.id for n in g.notes]),
        ("critical", [r.id for r in g.critical]),
        ("question", [q.id for q in g.questions]),
    ):
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            errors.append(f"duplicate {kind} id {dup}")

    entity_ids = {e.id for e in g.entities}
    fact_ids = {f.id for f in g.facts}
    entity_types = {t.value for t in EntityType}

    if not any(e.required for e in g.entities):
        errors.append("no required entity")
    for e in g.entities:
        for sid in e.evidence:
            check_segment(sid, f"entity {e.id}")
        if not e.accepted:
            errors.append(f"entity {e.id}: accepted is empty")
        for acc in e.accepted:
            if acc.type not in entity_types:
                errors.append(f"entity {e.id}: type {acc.type!r} is not an EntityType")

    if not g.facts:
        errors.append("no fact")
    for f in g.facts:
        if f.weight not in (1, 3):
            errors.append(f"fact {f.id}: weight {f.weight} not in {{1, 3}}")
        for subject in f.subjects:
            if subject not in entity_ids:
                errors.append(f"fact {f.id}: unknown subject {subject}")
        for ev in f.evidence:
            if ev.segment not in seg_text:
                errors.append(f"fact {f.id}: unknown segment {ev.segment}")
            elif ev.quote not in seg_text[ev.segment]:
                errors.append(f"fact {f.id}: quote is not a verbatim substring of {ev.segment}")

    for n in g.notes:
        if n.weight not in (1, 3):
            errors.append(f"note {n.id}: weight {n.weight} not in {{1, 3}}")
        if n.fact not in fact_ids:
            errors.append(f"note {n.id}: unknown fact {n.fact}")
        if n.entity not in entity_ids:
            errors.append(f"note {n.id}: unknown entity {n.entity}")

    for r in g.critical:
        if not r.trigger.strip():
            errors.append(f"critical {r.id}: empty trigger")
        for sid in r.evidence:
            check_segment(sid, f"critical {r.id}")
    for q in g.questions:
        for sid in q.segments:
            check_segment(sid, f"question {q.id}")
    for x in g.excluded:
        for sid in x.segments:
            check_segment(sid, "excluded")
    return errors


def review_pack(gold: dict, rubric: dict, segments, hashes: dict) -> str:
    g = Gold.model_validate(gold)
    seg_index = {f"S{i:03d}": i for i in range(len(segments))}

    def seg_ref(sid: str) -> str:
        i = seg_index.get(sid)
        return f"{sid} {_hms(segments[i]['start'])}" if i is not None else f"{sid} ?"

    def seg_text(sid: str) -> str:
        i = seg_index.get(sid)
        return segments[i]["text"] if i is not None else "(unbekanntes Segment)"

    lines = [
        f"# Gold-Prüfpaket (v{g.version})",
        "",
        f"Approval hash: {hashes['approval']}",
        "",
        f"- Gold-Hash: {hashes['gold']}",
        f"- Rubrik-Hash: {hashes['rubric']}",
        f"- Quell-Hash: {hashes['source']}",
        "",
        "## Offene Fragen",
        "",
    ]
    for q in g.questions:
        lines.append(f"- [{q.id}] {q.text}")
        lines.extend(f"  - Item: {item}" for item in q.items)
        lines.extend(f"  - {seg_ref(sid)}: {seg_text(sid)}" for sid in q.segments)
    lines += ["", "## Fakten", ""]
    scenes: dict[str, list[GoldFact]] = {}
    for f in g.facts:
        scenes.setdefault(f.scene, []).append(f)
    for scene, facts in scenes.items():
        lines.append(f"### {scene}")
        for f in facts:
            quotes = "; ".join(f'"{ev.quote}" ({seg_ref(ev.segment)})' for ev in f.evidence)
            tail = f" — {quotes}" if quotes else ""
            lines.append(f"- [{f.id}] (w={f.weight}, {f.placement}) {f.statement}{tail}")
        lines.append("")
    lines += ["## Notiz-Anforderungen", ""]
    lines += [f"- [{n.id}] Fakt {n.fact} → Entität {n.entity} (w={n.weight})" for n in g.notes]
    lines += ["", "## Entitäten", ""]
    for e in g.entities:
        req = "required" if e.required else "optional"
        acc = ", ".join(f"{a.type}" + (f" {a.subtypes}" if a.subtypes else "") for a in e.accepted)
        lines.append(
            f"- [{e.id}] {e.label} ({req}); Aliase: {', '.join(e.aliases) or '-'}; "
            f"akzeptiert: {acc}; Belege: {', '.join(seg_ref(s) for s in e.evidence)}"
        )
    lines += ["", "## Kritische Regeln", ""]
    lines += [
        f"- [{r.id}] {r.description} Auslöser: {r.trigger}; Begründung: {r.rationale}; "
        f"Belege: {', '.join(seg_ref(s) for s in r.evidence)}"
        for r in g.critical
    ]
    lines += ["", "## Ausgeschlossen", ""]
    lines += [f"- {', '.join(x.segments)}: {x.reason}" for x in g.excluded]
    cal = rubric["calibration"]
    weights = ", ".join(f"{k} {v}" for k, v in rubric["weights"].items())
    lines += [
        "",
        "## Bewertung",
        "",
        f"- Gewichte: {weights}",
        f"- Toleranz: {rubric['tolerance']}",
        f"- G-Fenster: {rubric['g_window_segments']} Segmente",
        f"- Kalibrierungsschwelle: gesamt {cal['overall']}, F {cal['F']}, "
        f"kritische Fehlgriffe {cal['critical_misses']}",
        "",
    ]
    return "\n".join(lines)


# --- 4. Approval ------------------------------------------------------------------------


def approval_hash(gold_hash, rubric_hash, source_hash) -> str:
    return sha((gold_hash + rubric_hash + source_hash).encode())


def _draft_hashes(case_dir: Path, rubric_path: Path) -> dict:
    gold_hash = hash_obj(read_json(case_dir / "gold" / "draft.json"))
    rubric_hash = hash_obj(read_json(rubric_path))
    source = _source_hash(case_dir)
    return {
        "gold": gold_hash,
        "rubric": rubric_hash,
        "source": source,
        "approval": approval_hash(gold_hash, rubric_hash, source),
    }


def approve_gold(case_dir, rubric_path, typed_hash, reviewer, approval_ref, *, isatty, environ, confirm) -> Path:
    # Human gate: the TTY and agent-environment checks are the tripwire, not a guard rule.
    if not isatty():
        raise BenchError("approval needs an interactive terminal")
    if "CLAUDECODE" in environ or any(key.startswith("CODEX_") for key in environ):
        raise BenchError("approval refused inside an agent environment")
    draft_path = case_dir / "gold" / "draft.json"
    if not draft_path.is_file():
        raise BenchError(f"missing {draft_path}")
    gold = read_json(draft_path)
    errors = validate_gold(gold, load_segments(case_dir / "source.json"))
    if errors:
        raise BenchError("gold draft has errors: " + "; ".join(errors))
    hashes = _draft_hashes(case_dir, rubric_path)
    full = hashes["approval"]
    if len(typed_hash) < 12 or not full.startswith(typed_hash):
        raise BenchError("typed hash is not a prefix of the approval hash")
    if confirm() != full[:12]:
        raise BenchError("confirmation does not match the first 12 characters of the approval hash")
    version = gold["version"]
    write_once(case_dir / "gold" / f"v{version}.json", canon(gold))
    record = {
        "approval_hash": full,
        "gold_hash": hashes["gold"],
        "rubric_hash": hashes["rubric"],
        "source_sha256": hashes["source"],
        "reviewer": reviewer,
        "approval_ref": approval_ref,
        "date": datetime.date.today().isoformat(),
    }
    approval_path = case_dir / "gold" / f"v{version}.approval.json"
    write_once(approval_path, _pretty(record))
    return approval_path


def check_approval(case_dir, rubric_path) -> tuple[dict | None, str]:
    approvals = list((case_dir / "gold").glob("v*.approval.json"))
    if not approvals:
        return None, "no approval"

    def version_of(path: Path) -> int:
        return int(path.name.split(".")[0][1:])

    latest = max(approvals, key=version_of)
    record = read_json(latest)
    gold_path = latest.with_name(latest.name.split(".")[0] + ".json")
    if not gold_path.is_file() or hash_obj(read_json(gold_path)) != record["gold_hash"]:
        return None, "gold changed since approval"
    if hash_obj(read_json(rubric_path)) != record["rubric_hash"]:
        return None, "rubric changed since approval"
    if _source_hash(case_dir) != record["source_sha256"]:
        return None, "source changed since approval"
    return read_json(gold_path), ""


# --- 5. Output validation, attempts, repair ---------------------------------------------

REPAIR_MIN = 0.98


def validate_output(raw: str, segments) -> dict:
    from pnp_okf.agent_status import _check
    from pnp_okf.context import _parse_ts
    from pnp_okf.extract import _extract_json_block
    from pnp_okf.models import SUBTYPES, SessionExtraction

    errors: list[str] = []
    try:
        _check("extract", raw)
    except Exception as exc:  # a bad answer is a verdict, never a crash
        errors.append(f"check: {exc}")
    try:
        parsed = SessionExtraction.model_validate_json(_extract_json_block(raw))
    except Exception as exc:
        return {"valid": False, "errors": errors + [f"parse: {exc}"], "extraction": None}

    if not parsed.recap.strip():
        errors.append("empty recap")
    if not parsed.entities:
        errors.append("zero entities")
    last_end = segments[-1]["end"] if segments else 0.0
    for i, ent in enumerate(parsed.entities):
        if ent.subtype and ent.subtype not in SUBTYPES.get(ent.type, ()):
            errors.append(f"entities[{i}]: subtype {ent.subtype!r} not allowed for {ent.type.value}")
        seconds = _parse_ts(ent.citation_ts)
        if seconds is None or seconds < 0 or seconds > last_end:
            errors.append(f"entities[{i}]: citation_ts {ent.citation_ts!r} is outside the transcript")
    return {"valid": not errors, "errors": errors, "extraction": parsed.model_dump(mode="json")}


def repair_similarity(raw: str, repaired: dict) -> float:
    # Compares letters and digits only: a repair may change fences and whitespace, not prose.
    a = "".join(c for c in raw if c.isalnum())
    b = "".join(c for c in json.dumps(repaired, ensure_ascii=False) if c.isalnum())
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def attempt_id(case_hash, prompt_hash, schema_hash, host, model, effort, repeat) -> str:
    return hash_obj([case_hash, prompt_hash, schema_hash, host, model, effort, repeat])[:12]


def prepare_run(run_dir: Path, case_dir: Path, matrix: dict) -> list[Path]:
    case = read_json(case_dir / "case_manifest.json")
    created: list[Path] = []
    for arm in matrix["arms"]:
        first = arm.get("first_repeat", 1)
        for repeat in range(first, first + arm["repeats"]):
            aid = attempt_id(
                case["source_sha256"],
                case["prompt_sha256"],
                case["schema_sha256"],
                arm["host"],
                arm["model"],
                arm["effort"],
                repeat,
            )
            attempt_dir = run_dir / "attempts" / f"{arm['label']}-r{repeat}-{aid}"
            record = {
                "label": arm["label"],
                "host": arm["host"],
                "model": arm["model"],
                "effort": arm["effort"],
                "repeat": repeat,
                "kind": "new",
                "attempt_id": aid,
                "case_hash": case["source_sha256"],
                "prompt_hash": case["prompt_sha256"],
                "schema_hash": case["schema_sha256"],
            }
            write_once(attempt_dir / "attempt.json", _pretty(record))
            created.append(attempt_dir)
    return created


def import_output(run_dir: Path, case_dir: Path, file: Path, label: str, provenance: Path | None) -> Path:
    data = file.read_bytes()
    case = read_json(case_dir / "case_manifest.json")
    attempt_dir = run_dir / "attempts" / f"{label}-retro-{sha(data)[:12]}"
    record = {
        "label": label,
        "kind": "retrospective",
        "case_hash": case["source_sha256"],
        "prompt_hash": case["prompt_sha256"],
        "schema_hash": case["schema_sha256"],
    }
    write_once(attempt_dir / "attempt.json", _pretty(record))
    write_once(attempt_dir / "raw.txt", data)
    if provenance is not None:
        write_once(attempt_dir / "execution.json", provenance.read_bytes())
    return attempt_dir


def attempt_state(attempt_dir: Path, segments) -> dict:
    # Derived on every call, never stored: a stored state would go stale when a file changes.
    raw_path = attempt_dir / "raw.txt"
    if not raw_path.is_file():
        return {"state": "pending", "errors": [], "extraction": None, "similarity": None}
    raw = raw_path.read_text(encoding="utf-8")
    first = validate_output(raw, segments)
    if first["valid"]:
        return {"state": "valid", "errors": [], "extraction": first["extraction"], "similarity": None}
    repair_path = attempt_dir / "repair.raw.txt"
    if not repair_path.is_file():
        return {"state": "failed", "errors": first["errors"], "extraction": None, "similarity": None}
    second = validate_output(repair_path.read_text(encoding="utf-8"), segments)
    if not second["valid"]:
        return {"state": "failed", "errors": first["errors"] + second["errors"], "extraction": None, "similarity": None}
    similarity = repair_similarity(raw, second["extraction"])
    if similarity < REPAIR_MIN:
        return {
            "state": "failed",
            "errors": first["errors"] + [f"repair rewrote the prose (similarity {similarity:.3f})"],
            "extraction": None,
            "similarity": similarity,
        }
    return {
        "state": "repaired",
        "errors": first["errors"],
        "extraction": second["extraction"],
        "similarity": similarity,
    }


def validate_run(run_dir: Path, case_dir: Path) -> dict:
    segments = load_segments(case_dir / "source.json")
    results: dict[str, dict] = {}
    attempts = run_dir / "attempts"
    if not attempts.is_dir():
        return results
    for attempt_dir in sorted(p for p in attempts.iterdir() if p.is_dir()):
        state = attempt_state(attempt_dir, segments)
        results[attempt_dir.name] = state
        if state["state"] in ("valid", "repaired"):
            write_once(attempt_dir / "extraction.json", canon(state["extraction"]))
    return results


# --- 6. Grading packets -----------------------------------------------------------------


def prepare_grading(run_dir: Path, case_dir: Path, *, salt: str | None = None) -> dict[str, str]:
    # The identity map stays under private/: grading/ must never name an attempt.
    identity_path = run_dir / "private" / "identity_map.json"
    if identity_path.is_file():
        identity = read_json(identity_path)
    else:
        identity = {"salt": salt if salt is not None else secrets.token_hex(16), "map": {}}
    anon_by_attempt: dict[str, str] = {}
    attempts = run_dir / "attempts"
    if attempts.is_dir():
        for attempt_dir in sorted(p for p in attempts.iterdir() if p.is_dir()):
            extraction_path = attempt_dir / "extraction.json"
            if not extraction_path.is_file():
                continue
            data = extraction_path.read_bytes()
            anon = sha((identity["salt"] + sha(data)).encode())[:8]
            write_once(run_dir / "grading" / anon / "output.json", data)
            anon_by_attempt[attempt_dir.name] = anon
    identity["map"].update(anon_by_attempt)
    write_json(identity_path, identity)
    return anon_by_attempt


V_CLAIM = ("supported", "contradicted", "unsupported", "unresolved")
V_LOC = ("supported", "not_supported", "unresolved")
V_FACT = ("present", "partial", "absent", "conflicting", "unresolved")
V_NOTE = ("present", "absent", "wrong_entity", "unresolved")
V_CRIT = ("violated", "not_violated", "unresolved")
# entity match: "gold:<id>" | "extra_supported" | "duplicate_of:<index>" | "unsupported" | "unresolved"


def judge_hash(judge: dict) -> str:
    return hash_obj(judge)[:12]


def sentences(text: str) -> list[str]:
    # Same boundary rule as claims.split_claims, but no minimum length and no markdown stripping.
    from pnp_okf.claims import _ABBREV, _BOUNDARY, _PROTECTED_DOT

    out: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        protected = _ABBREV.sub(lambda m: m.group(0).replace(".", _PROTECTED_DOT), line)
        pos = 0
        for m in _BOUNDARY.finditer(protected):
            out.append(protected[pos : m.end()])
            pos = m.end()
        out.append(protected[pos:])
    return [s for s in (part.replace(_PROTECTED_DOT, ".").strip() for part in out) if s]


def validate_inventory(inv: dict, extraction: dict) -> list[str]:
    errors: list[str] = []
    if inv.get("output_sha256") != hash_obj(extraction):
        errors.append("output_sha256 does not match the extraction")
    texts = {"recap": extraction["recap"]}
    for i, ent in enumerate(extraction["entities"]):
        texts[f"entity:{i}"] = ent.get("note", "")

    seen: set[str] = set()
    spans: dict[str, list[str]] = {}
    for claim in inv.get("claims", []):
        cid, loc, span = claim.get("id"), claim.get("loc"), claim.get("span", "")
        if cid in seen:
            errors.append(f"duplicate claim id {cid}")
        seen.add(cid)
        if loc not in texts:
            errors.append(f"claim {cid}: unknown loc {loc!r}")
            continue
        if not span.strip() or span not in texts[loc]:
            # An empty span would be a substring of everything and cover every sentence.
            errors.append(f"claim {cid}: span is empty or not a verbatim substring of {loc}")
            continue
        spans.setdefault(loc, []).append(span.strip())

    for loc, text in texts.items():
        for sentence in sentences(text):
            if not any(s in sentence or sentence in s for s in spans.get(loc, [])):
                errors.append(f"{loc}: sentence not covered by any claim: {sentence[:60]!r}")
    if not any(c.get("kind") == "claim" for c in inv.get("claims", [])):
        errors.append("no claim of kind 'claim'")
    return errors


# --- 7. Judgments, resolution, disagreements --------------------------------------------

_SECTIONS = {"A": ("claims", "locators"), "B": ("facts", "notes", "entities", "critical")}
_VOCAB = {"claims": V_CLAIM, "locators": V_LOC, "facts": V_FACT, "notes": V_NOTE, "critical": V_CRIT}
_KIND_SECTION = {"F": "claims", "G": "locators", "C": "facts", "N": "notes", "E": "entities", "K": "critical"}
_EVIDENCE_KEYS = ("segments", "spans", "why")


def _check_judgment_file(path: Path, packet: str, doc: dict) -> None:
    for section in _SECTIONS[packet]:
        for item_id, item in doc.get(section, {}).items():
            if section == "entities":
                match = item.get("match")
                ok = isinstance(match, str) and (
                    match in ("extra_supported", "unsupported", "unresolved")
                    or match.startswith(("gold:", "duplicate_of:"))
                )
                if not ok:
                    raise BenchError(f"{path.name}: entities {item_id}: bad match {match!r}")
            elif item.get("verdict") not in _VOCAB[section]:
                raise BenchError(f"{path.name}: {section} {item_id}: bad verdict {item.get('verdict')!r}")


def load_judgments(grading_dir: Path, packet: str, *, overlay: bool = True) -> dict[str, dict]:
    # Base file <packet>.<judge>.json, revision overlay <packet>.<judge>.x.json (same items, replaced by id).
    if not grading_dir.is_dir():
        return {}
    files = {p.name: p for p in grading_dir.iterdir() if p.is_file()}
    base_re = re.compile(rf"{packet}\.([a-z0-9]+)\.json")
    overlay_re = re.compile(rf"{packet}\.([a-z0-9]+)\.x\.json")
    judgments: dict[str, dict] = {}
    for name, path in sorted(files.items()):
        match = base_re.fullmatch(name)
        if match:
            doc = read_json(path)
            _check_judgment_file(path, packet, doc)
            judgments[match.group(1)] = doc
    if not overlay:
        return judgments
    for name, path in sorted(files.items()):
        match = overlay_re.fullmatch(name)
        if not match:
            continue
        judge = match.group(1)
        if judge not in judgments:
            raise BenchError(f"{name} has no base file {packet}.{judge}.json")
        patch = read_json(path)
        _check_judgment_file(path, packet, patch)
        for section in _SECTIONS[packet]:
            judgments[judge].setdefault(section, {}).update(patch.get(section, {}))
    return judgments


def judgment_items(packet: str, judgment: dict) -> dict[str, object]:
    items: dict[str, object] = {}
    if packet == "A":
        for cid, item in judgment.get("claims", {}).items():
            items[f"F:{cid}"] = item["verdict"]
        for idx, item in judgment.get("locators", {}).items():
            items[f"G:{idx}"] = item["verdict"]
    else:
        for fid, item in judgment.get("facts", {}).items():
            items[f"C:{fid}"] = item["verdict"]
        for rid, item in judgment.get("notes", {}).items():
            items[f"N:{rid}"] = (item["verdict"], item.get("entity_index"))
        for idx, item in judgment.get("entities", {}).items():
            items[f"E:{idx}"] = (item["match"], item["type_ok"], item["subtype_ok"])
        for rid, item in judgment.get("critical", {}).items():
            items[f"K:{rid}"] = item["verdict"]
    return items


def _unresolved(value) -> bool:
    if value == "unresolved":
        return True
    return isinstance(value, (tuple, list)) and len(value) > 0 and value[0] == "unresolved"


def _adjudicated_value(key: str, entry: dict):
    kind = key.split(":", 1)[0]
    fields = {"E": ("match", "type_ok", "subtype_ok"), "N": ("verdict", "entity_index")}.get(kind, ("verdict",))
    try:
        values = tuple(entry[field] for field in fields)
    except KeyError as exc:
        # A hand-written adjudication with a missing field must name the item, not die with KeyError.
        raise BenchError(f"adjudication {key}: missing field {exc.args[0]}") from None
    return values if kind in ("E", "N") else values[0]


def expected_binds(packet: str, grading_dir: Path, case_dir: Path) -> dict:
    def file_sha(path: Path) -> str | None:
        return sha(path.read_bytes()) if path.is_file() else None

    rubric_path = _rubric_path(case_dir)
    source_path = case_dir / "source.json"
    binds = {
        "output_sha256": file_sha(grading_dir / "output.json"),
        "source_sha256": file_sha(source_path),
        "rubric_sha256": hash_obj(read_json(rubric_path)) if rubric_path.is_file() else None,
    }
    if packet == "A":
        binds["inventory_sha256"] = file_sha(grading_dir / "inventory.json")
        return binds
    gold = None
    if rubric_path.is_file() and source_path.is_file():
        gold, _ = check_approval(case_dir, rubric_path)
    draft = case_dir / "gold" / "draft.json"
    if gold is None and draft.is_file():
        gold = read_json(draft)
    binds["gold_sha256"] = hash_obj(gold) if gold is not None else None
    return binds


def stale_reasons(packet: str, judgment: dict, expected: dict) -> list[str]:
    bound = judgment.get("binds", {})
    return [
        f"binds.{k} differs"
        for k in sorted(set(bound) | set(expected))
        if bound.get(k) != expected.get(k)
    ]


def resolve(key: str, verdicts: dict[str, object], adjudication: dict) -> tuple[object, str]:
    if key in adjudication:
        return _adjudicated_value(key, adjudication[key]), "adjudicated"
    if len(verdicts) < 2:
        return None, "missing"
    values = list(verdicts.values())
    if all(v == values[0] for v in values) and not _unresolved(values[0]):
        return values[0], "agreed"
    return None, "disputed"


def _evidence(judgment: dict, key: str) -> dict:
    prefix, ident = key.split(":", 1)
    item = judgment.get(_KIND_SECTION[prefix], {}).get(ident, {})
    return {k: item[k] for k in _EVIDENCE_KEYS if k in item}


def diff_judgments(run_dir: Path, case_dir: Path) -> dict:
    grading_root = run_dir / "grading"
    folders = sorted(p for p in grading_root.iterdir() if p.is_dir()) if grading_root.is_dir() else []
    rows: list[dict] = []
    counts = {"disputed": 0, "missing": 0}
    for folder in folders:
        adjudication_path = folder / "adjudication.json"
        adjudication = read_json(adjudication_path) if adjudication_path.is_file() else {}
        for packet in ("A", "B"):
            judgments = load_judgments(folder, packet)
            if not judgments:
                continue
            per_judge = {judge: judgment_items(packet, j) for judge, j in judgments.items()}
            exchange: dict[str, list[dict]] = {judge: [] for judge in judgments}
            for key in sorted(set().union(*per_judge.values())):
                verdicts = {judge: items[key] for judge, items in per_judge.items() if key in items}
                _, how = resolve(key, verdicts, adjudication)
                if how not in ("disputed", "missing"):
                    continue
                counts[how] += 1
                evidence = {judge: _evidence(judgments[judge], key) for judge in verdicts}
                rows.append({"anon": folder.name, "key": key, "how": how, "verdicts": verdicts, "evidence": evidence})
                if how == "disputed":
                    for judge in verdicts:
                        others = {o: ev for o, ev in evidence.items() if o != judge}
                        exchange[judge].append({"key": key, "evidence": others})
            for judge, items in exchange.items():
                write_json(run_dir / "exchange" / f"{folder.name}.{packet}.{judge}.json", items)
    write_json(run_dir / "disagreements.json", rows)
    return counts


# --- 8. Scoring ------------------------------------------------------------------------


def _share_comp(closed: float, pending: float, total: float, empty: float) -> dict:
    # Open items widen the bounds: low counts them as failures, high as successes.
    if total == 0:
        return {"value": empty, "low": empty, "high": empty}
    low = 100 * closed / total
    if not pending:
        return {"value": low, "low": low, "high": low}
    return {"value": None, "low": low, "high": 100 * (closed + pending) / total}


def _duplicate_index(match) -> int | None:
    if isinstance(match, str) and match.startswith("duplicate_of:") and match.split(":", 1)[1].isdigit():
        return int(match.split(":", 1)[1])
    return None


def _entity_score(rows: list, gold_entities: list[dict]) -> float:
    # rows: resolved (match, type_ok, subtype_ok) per emitted entity, in index order.
    required = {e["id"] for e in gold_entities if e["required"]}
    gold_ids = {e["id"] for e in gold_entities}
    seen: set[str] = set()
    supported = matched_required = matched_optional = extras = flagged = 0
    for match, type_ok, subtype_ok in rows:
        gid = match[5:] if match.startswith("gold:") else None
        if gid in gold_ids and gid not in seen:
            seen.add(gid)
            if gid in required:
                matched_required += 1
            else:
                matched_optional += 1
        elif match == "extra_supported":
            extras += 1
        else:
            # Duplicates and false positives only add to the precision denominator.
            continue
        supported += 1
        if type_ok and subtype_ok:
            flagged += 1
    emitted = len(rows)
    precision = supported / emitted if emitted else 0.0
    recall = matched_required / len(required) if required else 0.0
    identity = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    denominator = len(required) + matched_optional + extras
    classification = flagged / denominator if denominator else 0.0
    return 100 * (2 / 3 * identity + 1 / 3 * classification)


def score_output(extraction, gold, rubric, inventory, judg_a, judg_b, adjudication) -> dict:
    # judg_a / judg_b: {judge: judgment}. Every item goes through resolve(); None means open.
    verdicts: dict[str, dict[str, object]] = {}
    for packet, judgments in (("A", judg_a), ("B", judg_b)):
        for judge, judgment in judgments.items():
            for key, value in judgment_items(packet, judgment).items():
                verdicts.setdefault(key, {})[judge] = value

    open_items: set[str] = set()
    ledger: list[dict] = []

    def value_of(key: str):
        value, _ = resolve(key, verdicts.get(key, {}), adjudication)
        if value is None:
            open_items.add(key)
        return value

    # F: claims grouped by group id; one resolved verdict per group.
    groups: dict[str, list[dict]] = {}
    for claim in inventory["claims"]:
        if claim["kind"] == "claim":
            groups.setdefault(claim["group"], []).append(claim)
    supported = contradicted = unsupported = open_groups = 0
    for members in groups.values():
        keys = [f"F:{claim['id']}" for claim in members]
        values = [value_of(key) for key in keys]
        known = {v for v in values if v is not None}
        if None in values or len(known) > 1:
            if len(known) > 1:
                ledger.append({"key": keys[0], "problem": "mixed_group"})
            open_groups += 1
            open_items.update(keys)
            continue
        if values[0] == "supported":
            supported += 1
        elif values[0] == "contradicted":
            contradicted += 1
        elif values[0] == "unsupported":
            unsupported += 1
    if groups:
        f_comp = _share_comp(supported, open_groups, len(groups), empty=0.0)
    else:
        f_comp = {"value": None, "low": 0.0, "high": 0.0}

    # C: weighted share of gold facts judged present.
    facts = gold["facts"]
    fact_w = present_w = pending_c = 0
    for fact in facts:
        fact_w += fact["weight"]
        verdict = value_of(f"C:{fact['id']}")
        if verdict is None:
            pending_c += fact["weight"]
        elif verdict == "present":
            present_w += fact["weight"]
    c_comp = _share_comp(present_w, pending_c, fact_w, empty=100.0)

    # E: entities, then G (supported locators) and N (notes) use the resolved matches.
    entities = extraction["entities"]
    e_values = [value_of(f"E:{i}") for i in range(len(entities))]
    matches = [v[0] if v is not None else None for v in e_values]
    if any(v is None for v in e_values):
        low = _entity_score([v or ("unsupported", False, False) for v in e_values], gold["entities"])
        high = _entity_score([v or ("extra_supported", True, True) for v in e_values], gold["entities"])
        e_comp = {"value": None, "low": low, "high": high}
    else:
        e_score = _entity_score(e_values, gold["entities"])
        e_comp = {"value": e_score, "low": e_score, "high": e_score}

    g_closed = g_pending = 0
    for i in range(len(entities)):
        verdict = value_of(f"G:{i}")
        if verdict is None:
            g_pending += 1
        elif verdict == "supported":
            g_closed += 1
    g_comp = _share_comp(g_closed, g_pending, len(entities), empty=0.0)

    # N: a requirement is credited only with present + an index in its target records.
    note_total = credited_w = pending_n = 0
    for req in gold["notes"]:
        note_total += req["weight"]
        target = {i for i, m in enumerate(matches) if m == f"gold:{req['entity']}"}
        target |= {i for i, m in enumerate(matches) if _duplicate_index(m) in target}
        if not target:
            # An open entity match may still turn out to be the target record.
            if None in matches:
                pending_n += req["weight"]
            continue
        key = f"N:{req['id']}"
        resolved = value_of(key)
        if resolved is None:
            pending_n += req["weight"]
            continue
        verdict, index = resolved
        if verdict == "present" and index in target:
            credited_w += req["weight"]
        elif verdict in ("present", "wrong_entity"):
            ledger.append({"key": key, "problem": "wrong_entity"})
    n_comp = _share_comp(credited_w, pending_n, note_total, empty=100.0)

    critical = []
    for rule in gold["critical"]:
        if value_of(f"K:{rule['id']}") == "violated":
            critical.append(rule["id"])

    comps = {"F": f_comp, "C": c_comp, "N": n_comp, "E": e_comp, "G": g_comp}
    weights = rubric["weights"]
    q_low = sum(weights[k] * comps[k]["low"] for k in weights)
    q_high = sum(weights[k] * comps[k]["high"] for k in weights)
    q_value = None
    if all(comps[k]["value"] is not None for k in weights):
        q_value = sum(weights[k] * comps[k]["value"] for k in weights)
    return {
        "F": f_comp,
        "C": c_comp,
        "N": n_comp,
        "E": e_comp,
        "G": g_comp,
        "Q": {"value": q_value, "low": q_low, "high": q_high},
        "counts": {
            "contradicted": contradicted,
            "unsupported": unsupported,
            "claim_groups": len(groups),
            "entities": len(entities),
        },
        "critical": critical,
        "open_items": sorted(open_items),
        "ledger": ledger,
    }


# --- 9. Cost ----------------------------------------------------------------------------


def _pick(raw: dict, *paths: str):
    # First dotted path that is present (not None) in the raw usage dict.
    for path in paths:
        cur = raw
        for part in path.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is not None:
            return cur
    return None


def normalise_usage(style: str, raw: dict) -> dict:
    if style == "openai":
        # Cached tokens are a subset of the prompt tokens; reasoning is already inside output.
        return {
            "input_total": _pick(raw, "prompt_tokens", "input_tokens"),
            "cache_read": _pick(
                raw,
                "prompt_tokens_details.cached_tokens",
                "input_tokens_details.cached_tokens",
                "cached_input_tokens",
                "prompt_cache_hit_tokens",
            ),
            "cache_write": 0,
            "output_total": _pick(raw, "completion_tokens", "output_tokens"),
            "reasoning": _pick(
                raw,
                "completion_tokens_details.reasoning_tokens",
                "output_tokens_details.reasoning_tokens",
                "reasoning_output_tokens",
            ),
        }
    if style == "anthropic":
        # input_tokens excludes the cache tokens, so they are added back to the total.
        inp = raw.get("input_tokens")
        cache_read = raw.get("cache_read_input_tokens")
        cache_write = raw.get("cache_creation_input_tokens")
        total = None if None in (inp, cache_read, cache_write) else inp + cache_read + cache_write
        return {
            "input_total": total,
            "cache_read": cache_read,
            "cache_write": cache_write,
            "output_total": raw.get("output_tokens"),
            "reasoning": None,
        }
    raise BenchError(f"unknown usage style {style!r}")


def cost(turns: list[dict], price: dict | None) -> dict:
    unknown: list[str] = []
    if not turns:
        unknown.append("no turns")
    if price is None:
        unknown.append("no price row")
    if unknown:
        return {"standard": None, "observed": None, "unknown": unknown}

    standard = observed = 0.0
    standard_ok = observed_ok = True
    for turn in turns:
        inp, out = turn["input_total"], turn["output_total"]
        cache_read, cache_write = turn["cache_read"], turn["cache_write"]
        if inp is None or out is None:
            standard_ok = observed_ok = False
            unknown.append("missing usage: input_total or output_total")
            continue
        limit = price.get("max_input_tokens")
        if limit is not None and inp > limit:
            standard_ok = observed_ok = False
            unknown.append(f"input {inp} exceeds the price tier limit {limit}")
            continue
        standard += (inp * price["input"] + out * price["output"]) / 1e6
        if None in (cache_read, cache_write, price.get("cache_read"), price.get("cache_write")):
            observed_ok = False
            unknown.append("missing usage or price: cache tokens")
        else:
            uncached = inp - cache_read - cache_write
            observed += (
                uncached * price["input"]
                + cache_read * price["cache_read"]
                + cache_write * price["cache_write"]
                + out * price["output"]
            ) / 1e6
    return {
        "standard": standard if standard_ok else None,
        "observed": observed if observed_ok else None,
        "unknown": list(dict.fromkeys(unknown)),
    }


def attempt_cost(attempt_dir: Path, prices: dict) -> dict:
    usage_path = attempt_dir / "usage.json"
    if not usage_path.is_file():
        return {"standard": None, "observed": None, "unknown": ["no usage.json"]}
    docs = [read_json(usage_path)]
    missing: list[str] = []
    if (attempt_dir / "repair.raw.txt").is_file():
        if (attempt_dir / "repair.usage.json").is_file():
            docs.append(read_json(attempt_dir / "repair.usage.json"))
        else:
            missing.append("repair turn has no usage record")
    turns = [normalise_usage(doc["style"], raw) for doc in docs for raw in doc["turns"]]
    model = docs[0]["model"]
    row = next((r for r in prices.get("rows", []) if r["model"] == model), None)
    result = cost(turns, row)
    if missing:
        return {"standard": None, "observed": None, "unknown": result["unknown"] + missing}
    return result


# --- 10. Calibration -------------------------------------------------------------------

_KIND_ORDER = ("F", "G", "C", "N", "E")
_PACKET_KINDS = {"A": ("F", "G"), "B": ("C", "N", "E", "K")}


def _gold_for_scoring(case_dir: Path) -> tuple[dict, str]:
    # Approved gold when it is current; otherwise the draft, with the reason it is not approved.
    gold, reason = check_approval(case_dir, _rubric_path(case_dir))
    if gold is not None:
        return gold, ""
    draft = case_dir / "gold" / "draft.json"
    if not draft.is_file():
        raise BenchError("no approved gold and no gold/draft.json to score")
    return read_json(draft), reason


def _graded_folders(run_dir: Path) -> list[Path]:
    grading = run_dir / "grading"
    if not grading.is_dir():
        return []
    return sorted(p for p in grading.iterdir() if p.is_dir() and (p / "output.json").is_file())


def _item_texts(gold: dict, extraction: dict, inventory: dict) -> dict[str, str]:
    texts: dict[str, str] = {}
    for claim in inventory.get("claims", []):
        texts[f"F:{claim['id']}"] = claim["span"]
    for i, ent in enumerate(extraction["entities"]):
        texts[f"G:{i}"] = f"{ent['name']} @ {ent['citation_ts']}"
        texts[f"E:{i}"] = f"{ent['name']} ({ent['type']}/{ent['subtype']}): {ent['note']}"
    statement = {f["id"]: f["statement"] for f in gold["facts"]}
    label = {e["id"]: e["label"] for e in gold["entities"]}
    for fact_id, text in statement.items():
        texts[f"C:{fact_id}"] = text
    for req in gold["notes"]:
        texts[f"N:{req['id']}"] = f"{statement.get(req['fact'], '')} -> {label.get(req['entity'], '')}"
    for rule in gold["critical"]:
        texts[f"K:{rule['id']}"] = rule["description"]
    return texts


def calibration_sample(run_dir: Path, case_dir: Path, seed: int, n: int = 60, holdout: int = 20) -> list[dict]:
    gold, _ = _gold_for_scoring(case_dir)
    pool: list[tuple[str, str]] = []  # (<anon>|<key>, text)
    for folder in _graded_folders(run_dir):
        extraction = read_json(folder / "output.json")
        inv_path = folder / "inventory.json"
        inventory = read_json(inv_path) if inv_path.is_file() else {"claims": []}
        texts = _item_texts(gold, extraction, inventory)
        keys: set[str] = set()
        for packet in ("A", "B"):
            for judgment in load_judgments(folder, packet).values():
                keys.update(judgment_items(packet, judgment))
        pool.extend((f"{folder.name}|{key}", texts.get(key, "")) for key in keys)
    pool.sort()
    text_of = dict(pool)

    # K items are always in; the rest are dealt round-robin across kinds so no kind dominates.
    rng = random.Random(seed)
    by_kind: dict[str, list[str]] = {kind: [] for kind in _KIND_ORDER}
    critical_items: list[str] = []
    for item in text_of:
        kind = item.split("|", 1)[1][0]
        (critical_items if kind == "K" else by_kind[kind]).append(item)
    for kind in _KIND_ORDER:
        rng.shuffle(by_kind[kind])
    sample: list[str] = []
    position = 0
    while len(sample) < n and any(position < len(by_kind[k]) for k in _KIND_ORDER):
        for kind in _KIND_ORDER:
            if position < len(by_kind[kind]) and len(sample) < n:
                sample.append(by_kind[kind][position])
        position += 1
    rng.shuffle(sample)
    held = set(sample[max(len(sample) - holdout, 0) :])
    rows = [
        {
            "item": item,
            "kind": item.split("|", 1)[1][0],
            "set": "holdout" if item in held else "tune",
            "text": text_of[item],
        }
        for item in sorted(sample + critical_items)
    ]
    write_once(run_dir / "calibration" / "sample.json", _pretty(rows))
    return rows


def _rate(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def _calibrate_judge(packet: str, judge: dict, judged: dict, sample: dict, labels: dict, bar: dict) -> dict:
    # judged: {"<anon>|<key>": verdict} for this judge over every graded output.
    sets: dict[str, list[bool]] = {"tune": [], "holdout": []}
    per_kind: dict[str, dict[str, list[bool]]] = {}
    misses: list[str] = []
    critical_misses = 0
    kinds = {kind for p in packet.split("+") for kind in _PACKET_KINDS[p]}
    for item, row in sorted(sample.items()):
        if row["kind"] not in kinds or item not in labels:
            continue
        # A sampled item the judge never judged is a miss, not a skipped row.
        same = judged.get(item) == labels[item]
        sets[row["set"]].append(same)
        per_kind.setdefault(row["kind"], {"tune": [], "holdout": []})[row["set"]].append(same)
        if not same:
            misses.append(item)
            if row["kind"] == "K":
                critical_misses += 1
    overall = {s: _rate(flags) for s, flags in sets.items()}
    rates = {kind: {s: _rate(flags) for s, flags in d.items()} for kind, d in per_kind.items()}

    def reaches(rate, bar_value) -> bool:
        return rate is not None and rate >= bar_value

    overall_ok = all(reaches(overall[s], bar["overall"]) for s in ("tune", "holdout"))
    # F bar only where F items exist in a set; an empty set fails the overall bar above.
    f_ok = all(reaches(r, bar["F"]) for r in rates.get("F", {}).values() if r is not None)
    return {
        "judge_hash": judge_hash(judge),
        "packet": packet,
        "judge": judge,
        "pass": bool(overall_ok and f_ok and critical_misses <= bar["critical_misses"]),
        "overall": overall,
        "per_kind": rates,
        "critical_misses": critical_misses,
        "misses": misses,
    }


def calibrate(run_dir: Path, case_dir: Path, labels: dict[str, str], rubric: dict) -> dict:
    sample_path = run_dir / "calibration" / "sample.json"
    if not sample_path.is_file():
        raise BenchError("run calibration-sample first")
    sample = {row["item"]: row for row in read_json(sample_path)}
    # One judge config grades many outputs: pool its verdicts over all folders
    # before rating it, or the last folder would overwrite the others.
    # A config that judged both packets is rated on both: one file per judge hash.
    pooled: dict[str, dict] = {}
    for folder in _graded_folders(run_dir):
        for packet in ("A", "B"):
            for judgment in load_judgments(folder, packet, overlay=False).values():
                entry = pooled.setdefault(
                    judge_hash(judgment["judge"]), {"judge": judgment["judge"], "judged": {}, "packets": set()}
                )
                entry["packets"].add(packet)
                for key, value in judgment_items(packet, judgment).items():
                    entry["judged"][f"{folder.name}|{key}"] = value[0] if isinstance(value, tuple) else value
    results: dict[str, dict] = {}
    for _, entry in sorted(pooled.items()):
        packets = "+".join(sorted(entry["packets"]))
        result = _calibrate_judge(packets, entry["judge"], entry["judged"], sample, labels, rubric["calibration"])
        results[result["judge_hash"]] = result
        write_json(run_dir / "calibration" / f"{result['judge_hash']}.json", result)
    return results


def calibrated_judges(root: Path) -> set[str]:
    found: set[str] = set()
    for path in sorted((root / "runs").glob("*/calibration/*.json")):
        doc = read_json(path)
        if isinstance(doc, dict) and doc.get("pass") is True:
            found.add(path.stem)
    return found


# --- 11. Report and selection ----------------------------------------------------------

LIMITS = [
    "One session (5,072 words): no cross-session confidence interval. "
    "Repeat mean and range describe sampling noise on this case only.",
    "Once its failures inform a prompt, this case is a regression test, not an unseen test.",
    "Claims within one output are correlated; they are not independent observations.",
    "Outputs imported as retrospective were not produced under the benchmark launch protocol: "
    "comparable on quality, not on cost.",
    "Host harnesses add their own system prompt; temperature is not controllable; "
    "Claude and OpenAI effort names are not equivalent.",
    "API-equivalent cost is a proxy, not the subscription bill or quota.",
    "Extraction quality says nothing about synthesis, state or dedup quality.",
]


def _price_row(prices: dict, model: str) -> dict | None:
    return next((r for r in prices.get("rows", []) if r["model"] == model), None)


def _grading_cost(folder: Path | None, prices: dict) -> dict:
    docs = sorted(folder.glob("usage.*.json")) if folder is not None and folder.is_dir() else []
    if not docs:
        return {"standard": None, "observed": None, "unknown": ["no grading usage"]}
    parts = []
    for path in docs:
        doc = read_json(path)
        turns = [normalise_usage(doc["style"], raw) for raw in doc["turns"]]
        parts.append(cost(turns, _price_row(prices, doc["model"])))
    standard = None if any(p["standard"] is None for p in parts) else sum(p["standard"] for p in parts)
    observed = None if any(p["observed"] is None for p in parts) else sum(p["observed"] for p in parts)
    unknown = [reason for p in parts for reason in p["unknown"]]
    return {"standard": standard, "observed": observed, "unknown": list(dict.fromkeys(unknown))}


def _score_attempt(
    run_dir, attempt_dir, case_dir, gold, rubric, prices, approval_reason, anon, calibrated, segments
) -> dict:
    meta = read_json(attempt_dir / "attempt.json")
    state = attempt_state(attempt_dir, segments)
    folder = run_dir / "grading" / anon if anon else None
    record = {
        "attempt": attempt_dir.name,
        "label": meta["label"],
        "kind": meta["kind"],
        "state": state["state"],
        "status": "provisional",
        "reasons": [],
        "scores": None,
        "critical": False,
        "per_judge_Q": {},
        "cost": attempt_cost(attempt_dir, prices),
        "grading_cost": _grading_cost(folder, prices),
    }
    if state["state"] not in ("valid", "repaired"):
        record.update(status="invalid", reasons=[f"state {state['state']}"])
        return record
    if folder is None or not folder.is_dir():
        record["reasons"] = ["not graded"]
        return record
    inventory_path = folder / "inventory.json"
    if not inventory_path.is_file():
        record["reasons"] = ["no inventory"]
        return record
    inventory = read_json(inventory_path)
    if not any(c["kind"] == "claim" for c in inventory.get("claims", [])):
        record.update(status="invalid", reasons=["zero claim groups"])
        return record
    extraction = state["extraction"]
    errors = validate_inventory(inventory, extraction)
    if errors:
        record["reasons"] = ["inventory invalid: " + "; ".join(errors)]
        return record

    judg_a = load_judgments(folder, "A")
    judg_b = load_judgments(folder, "B")
    adj_path = folder / "adjudication.json"
    adjudication = read_json(adj_path) if adj_path.is_file() else {}
    scores = score_output(extraction, gold, rubric, inventory, judg_a, judg_b, adjudication)

    reasons = [f"approval: {approval_reason}"] if approval_reason else []
    for packet, judgments in (("A", judg_a), ("B", judg_b)):
        expected = expected_binds(packet, folder, case_dir)
        for judge, judgment in judgments.items():
            if judge_hash(judgment["judge"]) not in calibrated:
                reasons.append(f"judge {judge} ({packet}) not calibrated")
            reasons += [f"{judge} {packet}: {r}" for r in stale_reasons(packet, judgment, expected)]
    if len(judg_a) < 2 or len(judg_b) < 2:
        reasons.append("fewer than 2 judges")
    if scores["open_items"]:
        reasons.append(f"{len(scores['open_items'])} open item(s)")

    # Each judge alone, counted twice so resolve() sees two agreeing judges.
    per_judge = {}
    for judge in sorted(set(judg_a) | set(judg_b)):
        a = judg_a.get(judge)
        b = judg_b.get(judge)
        twin_a = {"a": a, "b": a} if a is not None else {}
        twin_b = {"a": b, "b": b} if b is not None else {}
        per_judge[judge] = score_output(extraction, gold, rubric, inventory, twin_a, twin_b, {})["Q"]

    record.update(
        status="provisional" if reasons else "official",
        reasons=reasons,
        scores=scores,
        critical=bool(scores["critical"]),
        per_judge_Q=per_judge,
    )
    return record


def _config(label: str, rows: list[dict]) -> dict:
    valid = [r for r in rows if r["state"] in ("valid", "repaired")]
    q_values = [r["scores"]["Q"]["value"] for r in rows if r["scores"] and r["scores"]["Q"]["value"] is not None]
    why_not: list[str] = []
    if any(r["kind"] == "retrospective" for r in rows):
        why_not.append("retrospective import")
    if not valid:
        why_not.append("no valid attempt")
    for r in rows:
        if r["state"] in ("failed", "pending"):
            why_not.append(f"{r['attempt']}: state {r['state']}")
        elif r["status"] != "official":
            why_not.append(f"{r['attempt']}: {r['status']}")
        if r["critical"]:
            why_not.append(f"{r['attempt']}: critical rule violated")

    def mean_cost(key: str) -> float | None:
        values = [r["cost"][key] for r in valid]
        if not values or any(v is None for v in values):
            return None
        return sum(values) / len(values)

    standard_all = [r["cost"]["standard"] for r in rows]
    per_valid = None
    if valid and not any(v is None for v in standard_all):
        per_valid = sum(standard_all) / len(valid)
    return {
        "label": label,
        "n_attempts": len(rows),
        "n_valid": len(valid),
        "q_values": q_values,
        "q_mean": sum(q_values) / len(q_values) if q_values else None,
        "q_min": min(q_values) if q_values else None,
        "q_max": max(q_values) if q_values else None,
        "eligible": not why_not,
        "why_not": why_not,
        "cost_standard": mean_cost("standard"),
        "cost_observed": mean_cost("observed"),
        "cost_per_valid": per_valid,
        "retrospective": any(r["kind"] == "retrospective" for r in rows),
    }


def score_run(run_dir: Path, case_dir: Path, prices: dict | None, baseline: str | None = None) -> dict:
    rubric = read_json(_rubric_path(case_dir))
    gold, approval_reason = _gold_for_scoring(case_dir)
    segments = load_segments(case_dir / "source.json")
    identity_path = run_dir / "private" / "identity_map.json"
    anon_of = read_json(identity_path)["map"] if identity_path.is_file() else {}
    calibrated = calibrated_judges(run_dir.parent.parent)
    prices = prices if prices is not None else {"rows": []}

    attempts_dir = run_dir / "attempts"
    attempt_dirs = sorted(p for p in attempts_dir.iterdir() if p.is_dir()) if attempts_dir.is_dir() else []
    attempts = [
        _score_attempt(
            run_dir, d, case_dir, gold, rubric, prices, approval_reason, anon_of.get(d.name), calibrated, segments
        )
        for d in attempt_dirs
    ]
    labels = sorted({a["label"] for a in attempts})
    configs = [_config(label, [a for a in attempts if a["label"] == label]) for label in labels]
    if baseline is not None:
        base = next((c for c in configs if c["label"] == baseline), None)
        if base is None:
            raise BenchError(f"baseline label {baseline!r} is not in this run")

        def diff(x, y):
            return None if x is None or y is None else x - y

        for config in configs:
            config["delta_to_baseline"] = {
                "q_mean": diff(config["q_mean"], base["q_mean"]),
                "cost_standard": diff(config["cost_standard"], base["cost_standard"]),
            }
    currencies = {row["currency"] for row in prices["rows"]}
    report = {
        "run": run_dir.name,
        "case": case_dir.name,
        "baseline": baseline,
        "currency": currencies.pop() if len(currencies) == 1 else None,
        "attempts": attempts,
        "configurations": configs,
        "selection": select(configs, rubric["tolerance"]),
        "limits": list(LIMITS),
    }
    write_json(run_dir / "report.json", report)
    (run_dir / "report.md").write_text(render_report(report), encoding="utf-8")
    return report


def select(configs: list[dict], tolerance: float) -> dict:
    eligible = [c for c in configs if c["eligible"]]
    if not eligible:
        return {
            "best_quality": None,
            "best_value": None,
            "within_tolerance": [],
            "provisional": ["no eligible configuration"],
        }
    reasons: list[str] = []
    top = max(c["q_mean"] for c in eligible)
    tied = sorted(c["label"] for c in eligible if c["q_mean"] == top)
    if len(tied) > 1:
        reasons.append("tie: " + ", ".join(tied))
    best = next(c for c in eligible if c["label"] == tied[0])
    within = sorted((c for c in eligible if c["q_mean"] >= top - tolerance), key=lambda c: c["label"])
    unknown = [c["label"] for c in within if c["cost_standard"] is None]
    best_value = None
    if unknown:
        reasons.append("cost unknown: " + ", ".join(unknown))
    else:
        cheapest = min(within, key=lambda c: (c["cost_standard"], -c["q_mean"], c["label"]))
        best_value = cheapest["label"]
    within_labels = {c["label"] for c in within}
    for c in eligible:
        if c["label"] not in within_labels and c["q_max"] >= best["q_min"]:
            reasons.append(f"rank flip: {c['label']}")
            best_value = None
    return {
        "best_quality": best["label"],
        "best_value": best_value,
        "within_tolerance": [c["label"] for c in within],
        "provisional": reasons,
    }


def _score_text(comp: dict | None) -> str:
    if comp is None:
        return "—"
    if comp["value"] is not None:
        return f"{comp['value']:.1f}"
    return f"{comp['low']:.1f}–{comp['high']:.1f} (open)"


def _money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.4f} {currency}" if currency else f"{value:.4f}"


def _delta_text(delta: dict | None, currency: str | None) -> str:
    if delta is None:
        return "—"
    q = "n/a" if delta["q_mean"] is None else f"{delta['q_mean']:+.1f}"
    if delta["cost_standard"] is None:
        cost = "unknown"
    else:
        cost = f"{delta['cost_standard']:+.4f}" + (f" {currency}" if currency else "")
    return f"Q {q}, cost {cost}"


def render_report(report: dict) -> str:
    currency = report.get("currency")
    lines = [f"# Extraction benchmark: run {report['run']}", "", f"Case: {report['case']}", ""]

    lines += [
        "## Configurations",
        "",
        "| Label | Valid / attempts | Q mean | Q range | Eligible | Standard cost | Observed cost "
        "| Cost per valid | Delta to baseline |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in report["configurations"]:
        q_mean = "n/a" if c["q_mean"] is None else f"{c['q_mean']:.1f}"
        q_range = "n/a" if c["q_min"] is None else f"{c['q_min']:.1f}–{c['q_max']:.1f}"
        eligible = "yes" if c["eligible"] else "no: " + "; ".join(c["why_not"])
        delta = _delta_text(c["delta_to_baseline"], currency) if "delta_to_baseline" in c else "—"
        lines.append(
            f"| {c['label']} | {c['n_valid']}/{c['n_attempts']} | {q_mean} | {q_range} | {eligible} | "
            f"{_money(c['cost_standard'], currency)} | {_money(c['cost_observed'], currency)} | "
            f"{_money(c['cost_per_valid'], currency)} | {delta} |"
        )

    sel = report["selection"]
    lines += [
        "",
        "## Selection",
        "",
        f"- Best quality: {sel['best_quality'] or 'none'}",
        f"- Best value: {sel['best_value'] or 'none'}",
        f"- Within tolerance: {', '.join(sel['within_tolerance']) or 'none'}",
    ]
    lines += [f"- Provisional: {reason}" for reason in sel["provisional"]] or ["- Provisional: none"]

    lines += [
        "",
        "## Outputs",
        "",
        "| Attempt | Label | Status | F | C | N | E | G | Q | Contradicted | Unsupported "
        "| Critical rules | Per-judge Q |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for a in report["attempts"]:
        s = a["scores"]
        if s is None:
            cells = ["—"] * 10
        else:
            cells = [_score_text(s[k]) for k in ("F", "C", "N", "E", "G", "Q")]
            cells += [str(s["counts"]["contradicted"]), str(s["counts"]["unsupported"])]
            cells += [", ".join(s["critical"]) or "none"]
            cells += ["; ".join(f"{j} {_score_text(q)}" for j, q in a["per_judge_Q"].items()) or "—"]
        status = f"{a['status']} ({a['state']})"
        lines.append("| " + " | ".join([a["attempt"], a["label"], status, *cells]) + " |")

    lines += ["", "## Error ledger", "", "| Attempt | Key | Problem |", "|---|---|---|"]
    ledger_rows = [
        f"| {a['attempt']} | {entry['key']} | {entry['problem']} |"
        for a in report["attempts"]
        if a["scores"]
        for entry in a["scores"]["ledger"]
    ]
    lines += ledger_rows or ["No entries."]

    lines += ["", "## Open items", ""]
    open_rows = []
    for a in report["attempts"]:
        keys = a["scores"]["open_items"] if a["scores"] else []
        if keys or a["reasons"]:
            open_rows.append(
                f"- {a['attempt']} ({a['status']}): {', '.join(keys) or 'no open items'}; "
                f"reasons: {'; '.join(a['reasons']) or 'none'}"
            )
    lines += open_rows or ["No entries."]

    lines += ["", "## Limits", ""] + [f"- {limit}" for limit in report["limits"]]
    return "\n".join(lines) + "\n"


def _approval_text(case_dir: Path) -> str:
    if not (case_dir / "source.json").is_file() or not _rubric_path(case_dir).is_file():
        return "incomplete (missing source.json or rubric)"
    gold, reason = check_approval(case_dir, _rubric_path(case_dir))
    if gold is not None:
        return f"approved (gold v{gold['version']})"
    return f"not approved: {reason}"


def _run_status(run_dir: Path, cases_by_hash: dict[str, Path]) -> list[str]:
    attempts_dir = run_dir / "attempts"
    attempt_dirs = sorted(p for p in attempts_dir.iterdir() if p.is_dir()) if attempts_dir.is_dir() else []
    case_dir = None
    for attempt_dir in attempt_dirs:
        meta_path = attempt_dir / "attempt.json"
        h = read_json(meta_path).get("case_hash") if meta_path.is_file() else None
        if h in cases_by_hash:
            case_dir = cases_by_hash[h]
            break
    states: dict[str, int] = {}
    for attempt_dir in attempt_dirs:
        segments = load_segments(case_dir / "source.json") if case_dir is not None else []
        name = attempt_state(attempt_dir, segments)["state"] if case_dir is not None else "no case"
        states[name] = states.get(name, 0) + 1

    folders = _graded_folders(run_dir)
    with_inventory = sum((f / "inventory.json").is_file() for f in folders)
    judgments: dict[str, int] = {}
    stale: int | str = "n/a"
    if case_dir is not None:
        stale = 0
    for folder in folders:
        for packet in ("A", "B"):
            for judge, judgment in load_judgments(folder, packet, overlay=False).items():
                key = f"{packet}.{judge}"
                judgments[key] = judgments.get(key, 0) + 1
                if case_dir is not None and stale_reasons(packet, judgment, expected_binds(packet, folder, case_dir)):
                    stale += 1

    report_path = run_dir / "report.json"
    open_text = "not scored"
    if report_path.is_file():
        report = read_json(report_path)
        open_text = str(sum(len(a["scores"]["open_items"]) for a in report["attempts"] if a["scores"]))
    attempt_text = ", ".join(f"{k}={v}" for k, v in sorted(states.items())) or "none"
    judgment_text = ", ".join(f"{k}={v}" for k, v in sorted(judgments.items())) or "none"
    return [
        f"run {run_dir.name}:",
        f"  attempts: {attempt_text}",
        f"  outputs with inventory: {with_inventory}/{len(folders)}",
        f"  judgments: {judgment_text}; stale: {stale}",
        f"  open items: {open_text}",
    ]


def status(root: Path) -> str:
    cases_dir = root / "cases"
    runs_dir = root / "runs"
    cases = sorted(p for p in cases_dir.iterdir() if p.is_dir()) if cases_dir.is_dir() else []
    runs = sorted(p for p in runs_dir.iterdir() if p.is_dir()) if runs_dir.is_dir() else []
    if not cases and not runs:
        return "no cases, no runs"
    lines: list[str] = []
    cases_by_hash: dict[str, Path] = {}
    for case_dir in cases:
        manifest = case_dir / "case_manifest.json"
        if manifest.is_file():
            cases_by_hash[read_json(manifest)["source_sha256"]] = case_dir
        lines.append(f"case {case_dir.name}: {_approval_text(case_dir)}")
    for run_dir in runs:
        lines += _run_status(run_dir, cases_by_hash)
    if not runs:
        lines.append("no runs")
    return "\n".join(lines)


# --- 12. CLI (stage 1 subcommands) ------------------------------------------------------


def _case_dir(root: Path, case: str) -> Path:
    return root / "cases" / case


def _run_dir(root: Path, run: str) -> Path:
    return root / "runs" / run


def _cmd_prepare(args) -> int:
    root, case = args.root or bench_root(), args.case
    manifest = prepare(args.experiment, args.transcript, _case_dir(root, case))
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_validate_gold(args) -> int:
    case_dir = _case_dir(args.root or bench_root(), args.case)
    errors = validate_gold(read_json(case_dir / "gold" / "draft.json"), load_segments(case_dir / "source.json"))
    for error in errors:
        print(error)
    return 1 if errors else 0


def _cmd_review_pack(args) -> int:
    case_dir = _case_dir(args.root or bench_root(), args.case)
    rubric_path = _rubric_path(case_dir)
    hashes = _draft_hashes(case_dir, rubric_path)
    text = review_pack(
        read_json(case_dir / "gold" / "draft.json"),
        read_json(rubric_path),
        load_segments(case_dir / "source.json"),
        hashes,
    )
    # Written to a file, not stdout: a Windows console (cp1252) cannot encode the pack.
    out = case_dir / "gold" / "review.md"
    out.write_text(text, encoding="utf-8")
    print(out)
    return 0


def _cmd_approve_gold(args) -> int:
    case_dir = _case_dir(args.root or bench_root(), args.case)

    def confirm() -> str:
        return input("Retype the first 12 characters of the approval hash: ").strip()

    path = approve_gold(
        case_dir,
        _rubric_path(case_dir),
        args.hash,
        args.reviewer,
        args.approval_ref,
        isatty=sys.stdin.isatty,
        environ=os.environ,
        confirm=confirm,
    )
    print(path)
    return 0


def _cmd_import_output(args) -> int:
    root = args.root or bench_root()
    path = import_output(
        _run_dir(root, args.run),
        _case_dir(root, args.case),
        args.file,
        args.label,
        args.provenance,
    )
    print(path)
    return 0


def _cmd_prepare_run(args) -> int:
    root = args.root or bench_root()
    matrix = read_json(args.matrix)
    for path in prepare_run(_run_dir(root, args.run), _case_dir(root, args.case), matrix):
        print(path)
    return 0


def _cmd_validate_run(args) -> int:
    root = args.root or bench_root()
    states = validate_run(_run_dir(root, args.run), _case_dir(root, args.case))
    for name, state in states.items():
        print(f"{name}: {state['state']}")
    return 0


def _cmd_prepare_grading(args) -> int:
    root = args.root or bench_root()
    mapping = prepare_grading(_run_dir(root, args.run), _case_dir(root, args.case))
    print(json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_diff_judgments(args) -> int:
    root = args.root or bench_root()
    counts = diff_judgments(_run_dir(root, args.run), _case_dir(root, args.case))
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_calibration_sample(args) -> int:
    root = args.root or bench_root()
    run_dir = _run_dir(root, args.run)
    calibration_sample(run_dir, _case_dir(root, args.case), args.seed)
    print(run_dir / "calibration" / "sample.json")
    return 0


def _cmd_calibrate(args) -> int:
    root = args.root or bench_root()
    case_dir = _case_dir(root, args.case)
    results = calibrate(_run_dir(root, args.run), case_dir, read_json(args.labels), read_json(_rubric_path(case_dir)))
    for judge, result in sorted(results.items()):
        print(f"{judge}: {'pass' if result['pass'] else 'fail'}")
    return 0 if results and all(r["pass"] for r in results.values()) else 1


def _cmd_score(args) -> int:
    root = args.root or bench_root()
    run_dir = _run_dir(root, args.run)
    prices = read_json(args.prices) if args.prices is not None else None
    score_run(run_dir, _case_dir(root, args.case), prices, args.baseline)
    print(run_dir / "report.md")
    return 0


def _cmd_status(args) -> int:
    print(status(args.root or bench_root()))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="extraction_benchmark", description="Offline extraction golden benchmark.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=None, help="benchmark root (default: PNP_BENCH_DIR or .cache)")
    common.add_argument("--case", default=DEFAULT_CASE, help="case id")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", parents=[common], help="copy a verified experiment into a case dir")
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--transcript", type=Path, required=True)
    p.set_defaults(func=_cmd_prepare)

    p = sub.add_parser("validate-gold", parents=[common], help="validate gold/draft.json")
    p.set_defaults(func=_cmd_validate_gold)

    p = sub.add_parser("review-pack", parents=[common], help="write the human review pack to gold/review.md")
    p.set_defaults(func=_cmd_review_pack)

    p = sub.add_parser("approve-gold", parents=[common], help="human-only approval of gold/draft.json")
    p.add_argument("--hash", required=True, help="typed prefix of the approval hash (at least 12 chars)")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--approval-ref", required=True)
    p.set_defaults(func=_cmd_approve_gold)

    p = sub.add_parser("import-output", parents=[common], help="import an existing output as a retrospective attempt")
    p.add_argument("--run", required=True)
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--provenance", type=Path, default=None)
    p.set_defaults(func=_cmd_import_output)

    p = sub.add_parser("prepare-run", parents=[common], help="create attempt folders from a matrix file")
    p.add_argument("--run", required=True)
    p.add_argument("--matrix", type=Path, required=True)
    p.set_defaults(func=_cmd_prepare_run)

    p = sub.add_parser("validate-run", parents=[common], help="derive attempt states for a run")
    p.add_argument("--run", required=True)
    p.set_defaults(func=_cmd_validate_run)

    p = sub.add_parser("prepare-grading", parents=[common], help="create anonymous grading folders for a run")
    p.add_argument("--run", required=True)
    p.set_defaults(func=_cmd_prepare_grading)

    p = sub.add_parser("diff-judgments", parents=[common], help="list disputed and missing judge items for a run")
    p.add_argument("--run", required=True)
    p.set_defaults(func=_cmd_diff_judgments)

    p = sub.add_parser("calibration-sample", parents=[common], help="draw the blind calibration sample")
    p.add_argument("--run", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.set_defaults(func=_cmd_calibration_sample)

    p = sub.add_parser("calibrate", parents=[common], help="score judges against human labels")
    p.add_argument("--run", required=True)
    p.add_argument("--labels", type=Path, required=True, help="JSON {item: verdict}")
    p.set_defaults(func=_cmd_calibrate)

    p = sub.add_parser("score", parents=[common], help="score a run and write report.json and report.md")
    p.add_argument("--run", required=True)
    p.add_argument("--prices", type=Path, default=None, help="JSON {rows: [price row, ...]}")
    p.add_argument("--baseline", default=None, help="configuration label to compare against")
    p.set_defaults(func=_cmd_score)

    p = sub.add_parser("status", parents=[common], help="summarise cases and runs under the root")
    p.set_defaults(func=_cmd_status)

    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BenchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
