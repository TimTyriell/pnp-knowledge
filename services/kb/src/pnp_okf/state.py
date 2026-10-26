"""The state pass (T5): threads, status changes and attitudes, per session.

The state pass is change-centric where extraction is entity-centric: it asks
what *happened* in one session (a quest was given, an NPC died, an NPC turned
hostile), not what exists. It is separately cached, so it cannot move a
concept id (docs/plans/T00-tracking-model.md §2, principle 1).

It is sequential by session date, and that is load-bearing. A thread's
identity is carried forward: session N's prompt lists the threads still open
after sessions 1..N-1, the model answers with an existing thread_id or "NEU",
and code mints the id once. Re-deriving identity from the model's wording
would rename threads on every resample (T00 §4.5).

``pnp run`` never calls this module. It only reads the cache that ``pnp state``
fills (decision D4, T00 §6). The cost is paid by a deliberate act.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from pnp_okf.config import DeepSeekConfig
from pnp_okf.episodes import Episodes, citation_labels
from pnp_okf.llm_client import build_client, is_retryable
from pnp_okf.models import (
    ATTITUDE_DIRS,
    THREAD_STATUSES,
    WORLD_STATUS_BY_DIR,
    CanonicalEntity,
    SessionTranscript,
)
from pnp_okf.okf import slugify
from pnp_okf.prompts import STATE_PROMPT_VERSION, STATE_SYSTEM, STATE_USER_TEMPLATE
from pnp_okf.resolve import _registry_data

log = logging.getLogger(__name__)

Evidence = Literal["observed", "claimed", "rumor", "speculation"]
ThreadKind = Literal["quest", "mystery", "promise", "debt", "deadline"]
ThreadStatus = Literal["open", "resolved", "abandoned"]
WorldStatus = Literal["alive", "dead", "missing", "captured", "transformed", "destroyed"]
Attitude = Literal["allied", "friendly", "neutral", "wary", "hostile"]

NEW_THREAD = "NEU"
PARTY = "Gruppe"

# German labels for the body text (T00: machine fields English, prose German).
# EVIDENCE_DE is shared with the thread Verlauf in emit.py (T6).
STATUS_DE = {"alive": "lebendig", "dead": "tot", "missing": "verschollen",
             "captured": "gefangen", "transformed": "verwandelt", "destroyed": "zerstört"}
ATTITUDE_DE = {"allied": "verbündet", "friendly": "freundlich", "neutral": "neutral",
               "wary": "misstrauisch", "hostile": "feindselig"}
EVIDENCE_DE = {"observed": "beobachtet", "claimed": "behauptet",
               "rumor": "Gerücht", "speculation": "Vermutung"}


class ThreadUpdate(BaseModel):
    thread_id: str = Field(
        description='Id of an open thread from the list in the prompt, or "NEU" '
        "for a thread that starts in this session."
    )
    title: str = Field(description="Short, specific German title (for NEU); otherwise the existing title.")
    kind: ThreadKind
    status: ThreadStatus = Field(description="Status at the END of this session.")
    note: str = Field(description="1-3 German sentences: what happened to this thread in this session.")
    citation_ts: str = Field(description="HH:MM:SS of the supporting moment.")
    involves: list[str] = Field(default_factory=list, description="Names of involved entities, as in the glossary.")
    evidence: Evidence = "observed"


class StatusChange(BaseModel):
    name: str = Field(description="Entity name as in the glossary.")
    value: WorldStatus
    note: str
    citation_ts: str
    evidence: Evidence = "observed"
    claimed_by: str = Field(default="", description="Who says so, when evidence is claimed or rumor.")


class AttitudeChange(BaseModel):
    name: str = Field(description="NPC or faction name as in the glossary.")
    toward: str = Field(description='"Gruppe" for the whole party, or one player character\'s name.')
    value: Attitude
    note: str
    citation_ts: str
    evidence: Evidence = "observed"


class SessionState(BaseModel):
    threads: list[ThreadUpdate] = Field(default_factory=list)
    status_changes: list[StatusChange] = Field(default_factory=list)
    attitudes: list[AttitudeChange] = Field(default_factory=list)


@dataclass
class Entry:
    """One dated, cited observation -- the unit everything else is built from."""

    session_id: str
    date: str
    url: str
    citation_ts: str
    note: str
    evidence: str


@dataclass
class ThreadRecord:
    thread_id: str            # "threads/<slug>", minted once
    title: str
    kind: str
    status: str               # status after the latest entry
    opened: str               # session_id of the first entry
    resolved: str | None      # session_id where status first became resolved/abandoned
    involves: list[str] = field(default_factory=list)   # names, de-duplicated, first-seen order
    entries: list[tuple[str, Entry]] = field(default_factory=list)  # (status_after, entry)


@dataclass
class StatusRecord:
    name: str
    value: str
    entry: Entry
    claimed_by: str = ""


@dataclass
class AttitudeRecord:
    name: str
    toward: str
    value: str
    entry: Entry


class Ledger:
    """Deterministic fold of per-session SessionState outputs, oldest first."""

    def __init__(self) -> None:
        self.threads: dict[str, ThreadRecord] = {}
        self.statuses: list[StatusRecord] = []
        self.attitudes: list[AttitudeRecord] = []
        self.warnings: list[str] = []

    def open_threads(self) -> list[ThreadRecord]:
        return [t for t in self.threads.values() if t.status == "open"]

    def _mint(self, title: str) -> str:
        base = slugify(title) or "faden"
        cid, n = f"threads/{base}", 2
        while cid in self.threads:
            cid, n = f"threads/{base}_{n}", n + 1
        return cid

    def apply(self, session_id: str, date: str, url: str, state: SessionState) -> None:
        for u in state.threads:
            entry = Entry(session_id, date, url, u.citation_ts.strip(), u.note.strip(), u.evidence)
            record = self.threads.get(u.thread_id) if u.thread_id != NEW_THREAD else None
            if record is None:
                if u.thread_id != NEW_THREAD:
                    # The model named an id we never gave it. Minting a new
                    # thread is recoverable (thread_rules: merge, T6); silently
                    # dropping the update is not.
                    self.warnings.append(f"{session_id}: unknown thread id {u.thread_id!r} -> minted new")
                cid = self._mint(u.title)
                record = ThreadRecord(cid, u.title.strip(), u.kind, u.status, opened=session_id, resolved=None)
                self.threads[cid] = record
            elif record.status != "open":
                self.warnings.append(f"{session_id}: update to closed thread {record.thread_id}")
            record.status = u.status
            if u.status != "open" and record.resolved is None:
                record.resolved = session_id
            if u.status == "open":
                record.resolved = None  # reopened
            for name in u.involves:
                if name.strip() and name.strip() not in record.involves:
                    record.involves.append(name.strip())
            record.entries.append((u.status, entry))
        for s in state.status_changes:
            self.statuses.append(StatusRecord(
                s.name.strip(), s.value,
                Entry(session_id, date, url, s.citation_ts.strip(), s.note.strip(), s.evidence),
                s.claimed_by.strip(),
            ))
        for a in state.attitudes:
            self.attitudes.append(AttitudeRecord(
                a.name.strip(), a.toward.strip() or PARTY, a.value,
                Entry(session_id, date, url, a.citation_ts.strip(), a.note.strip(), a.evidence),
            ))


def render_open_threads(ledger: Ledger) -> str:
    """The open-thread list as the prompt shows it. Deterministic: it keys the cache."""

    lines = []
    for t in sorted(ledger.open_threads(), key=lambda r: r.thread_id):
        last = t.entries[-1][1].note if t.entries else ""
        lines.append(f"- {t.thread_id} [{t.kind}] {t.title} — zuletzt: {last[:200]}")
    return "\n".join(lines) or "(keine offenen Fäden)"


# --- frozen glossary -------------------------------------------------------
# The glossary is a committed file, not a live read of the registry. The
# registry changes on every `pnp run`; reading it live would change every
# session's cache key on every run (T00 §5, "Glossary drift").

GLOSSARY_FILENAME = "state_glossary.yaml"
_GLOSSARY_TYPES = ("Character", "NPC", "Faction", "Location", "Item", "Deity", "Domain")
_MAX_ALIASES = 3


def build_glossary(registry_path: Path) -> list[dict]:
    """Entity names the state pass may refer to, from the live registry.

    Events are left out on purpose: the state pass reports changes *to*
    beings, places and things; events are what the session recap is for.
    """

    rows = []
    for e in _registry_data(registry_path).get("entities") or []:
        etype = str(e.get("type", ""))
        if etype not in _GLOSSARY_TYPES:
            continue
        aliases = [a for a in (e.get("aliases") or []) if a][:_MAX_ALIASES]
        rows.append({"type": etype, "name": e["canonical_name"], "aliases": aliases})
    rows.sort(key=lambda r: (_GLOSSARY_TYPES.index(r["type"]), r["name"].lower()))
    return rows


def write_glossary(knowledge_root: Path, rows: list[dict]) -> Path:
    path = knowledge_root / GLOSSARY_FILENAME
    header = (
        "# Frozen name list for the state pass (docs/plans/T5-state-pass.md).\n"
        "# GENERATED by `pnp state --refresh-glossary`. Its text keys the state\n"
        "# cache: refreshing it re-runs the state pass for every session.\n"
    )
    path.write_text(header + yaml.safe_dump({"entries": rows}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def load_glossary(knowledge_root: Path) -> list[dict]:
    path = knowledge_root / GLOSSARY_FILENAME
    if not path.is_file():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("entries") or []


def render_glossary(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        alias = f" (auch: {', '.join(r['aliases'])})" if r["aliases"] else ""
        lines.append(f"- {r['type']}: {r['name']}{alias}")
    return "\n".join(lines)


# --- cache and the one LLM call per session --------------------------------

def state_cache_key(t: SessionTranscript, cfg: DeepSeekConfig, glossary: str, open_threads: str) -> str:
    payload = "\n".join([
        STATE_PROMPT_VERSION, cfg.model, t.session_id, t.render_dialogue(),
        hashlib.sha256(glossary.encode("utf-8")).hexdigest(),
        hashlib.sha256(open_threads.encode("utf-8")).hexdigest(),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _cache_path(cache_dir: Path, t: SessionTranscript, key: str) -> Path:
    return cache_dir / "state" / t.session_id / f"{key}.json"


def load_cached_state(path: Path, key: str) -> SessionState | None:
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return SessionState.model_validate(blob["state"]) if blob.get("_key") == key else None


# ponytail: a malformed reply is resampled by is_retryable (ValidationError is in it),
# no separate parse-retry loop.
@retry(reraise=True, stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=2, min=2, max=30),
       retry=retry_if_exception(is_retryable))
def _call_llm(client, cfg: DeepSeekConfig, t: SessionTranscript, glossary: str, open_threads: str) -> SessionState:
    user = STATE_USER_TEMPLATE.format(
        session_id=t.session_id, date=t.date, glossary=glossary,
        open_threads=open_threads, dialogue=t.render_dialogue(),
    )
    schema = json.dumps(SessionState.model_json_schema(), ensure_ascii=False)
    completion = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": STATE_SYSTEM},
            {"role": "user", "content": user
             + "\n\nAntworte AUSSCHLIESSLICH mit einem JSON-Objekt gemäß diesem Schema:\n" + schema},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or ""
    return SessionState.model_validate_json(raw)


@dataclass
class StateRun:
    ledger: Ledger
    cached: int = 0
    called: int = 0
    uncached_estimate: int = 0


def run_state(
    transcripts: list[SessionTranscript],
    cfg: DeepSeekConfig,
    cache_dir: Path,
    glossary_rows: list[dict],
    *,
    estimate: bool = False,
    client=None,
) -> StateRun:
    """Fold every session's state into a Ledger, oldest first.

    Sequential by design: each session's prompt -- and so its cache key --
    contains the threads still open after the sessions before it. With
    ``estimate`` nothing is called; once one session is uncached every later
    key is unknowable, so the rest count as uncached too.
    """

    run = StateRun(Ledger())
    glossary = render_glossary(glossary_rows)
    blind = False
    for t in sorted(transcripts, key=lambda t: (t.date, t.session_id)):
        open_text = render_open_threads(run.ledger)
        key = state_cache_key(t, cfg, glossary, open_text)
        path = _cache_path(cache_dir, t, key)
        state = None if blind else load_cached_state(path, key)
        if state is None:
            if estimate:
                blind = True
                run.uncached_estimate += 1
                continue
            client = client or build_client(cfg)
            log.info("[state] calling %s: %s", cfg.model, t.session_id)
            state = _call_llm(client, cfg, t, glossary, open_text)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"_key": key, "state": state.model_dump(mode="json")},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
            run.called += 1
        else:
            run.cached += 1
        run.ledger.apply(t.session_id, t.date, t.url, state)
    return run


# --- T6: thread rules and name lookup --------------------------------------


def load_thread_rules(registry_path: Path) -> dict:
    """``thread_rules:`` from entity_rules.yaml -- human corrections (T6 §2)."""

    return _registry_data(registry_path).get("thread_rules") or {}


def apply_thread_rules(ledger: Ledger, rules: dict) -> None:
    """Human corrections on top of the fold. Mutates ``ledger.threads``.

    Order: ignore, merge, then title and status -- so a title or status rule
    may name the merge *winner* and still apply.
    """

    for tid in rules.get("ignore") or []:
        ledger.threads.pop(str(tid), None)

    for loser_id, winner_id in (rules.get("merge") or {}).items():
        loser = ledger.threads.get(str(loser_id))
        winner = ledger.threads.get(str(winner_id))
        if loser is None or winner is None:
            ledger.warnings.append(f"thread_rules merge {loser_id} -> {winner_id}: thread not found")
            continue
        winner.entries = sorted(
            winner.entries + loser.entries, key=lambda pe: (pe[1].date, pe[1].citation_ts)
        )
        for name in loser.involves:
            if name not in winner.involves:
                winner.involves.append(name)
        winner.opened = winner.entries[0][1].session_id
        winner.status = winner.entries[-1][0]
        if winner.status == "open":
            winner.resolved = None
        else:
            winner.resolved = next(e.session_id for s, e in winner.entries if s != "open")
        del ledger.threads[str(loser_id)]

    for tid, title in (rules.get("title") or {}).items():
        record = ledger.threads.get(str(tid))
        if record is None:
            ledger.warnings.append(f"thread_rules title {tid}: thread not found")
            continue
        record.title = str(title).strip()

    for tid, status in (rules.get("status") or {}).items():
        record = ledger.threads.get(str(tid))
        if record is None or status not in THREAD_STATUSES:
            ledger.warnings.append(f"thread_rules status {tid} -> {status!r}: thread or status not valid")
            continue
        record.status = status
        if status == "open":
            record.resolved = None
        elif record.resolved is None and record.entries:
            record.resolved = record.entries[-1][1].session_id


class NameIndex:
    """Map a state-pass name to a live concept id, or None.

    Exact canonical name or alias first (case-insensitive), then slug
    equality. A name two concepts share is ambiguous and maps to None --
    the same no-guessing rule as synthesize.link_targets.
    """

    def __init__(self, entities: list[CanonicalEntity]) -> None:
        self._owners: dict[str, set[str]] = {}
        self._slugs: dict[str, set[str]] = {}
        self._titles: dict[str, str] = {}
        for e in entities:
            self._titles[e.concept_id] = e.canonical_name
            for name in [e.canonical_name, *e.aliases]:
                if not name.strip():
                    continue
                self._owners.setdefault(name.strip().lower(), set()).add(e.concept_id)
                self._slugs.setdefault(slugify(name), set()).add(e.concept_id)

    def lookup(self, name: str) -> str | None:
        for table, key in ((self._owners, name.strip().lower()), (self._slugs, slugify(name))):
            owners = table.get(key, set())
            if len(owners) == 1:
                return next(iter(owners))
        return None

    def title(self, cid: str) -> str:
        return self._titles.get(cid, cid)


def _bullets(items: list[str]) -> list[str]:
    return [f"- {i}" for i in items] or ["- keine"]


def render_state_report(ledger: Ledger) -> str:
    """Plain markdown for the human who reviews a state run (T5 §4.2). Pure."""

    counts = Counter((t.kind, t.status) for t in ledger.threads.values())
    out = ["# Zustand (pnp state)", "", "## Zählung", ""]
    out += _bullets([f"{kind} / {status}: {n}" for (kind, status), n in sorted(counts.items())])
    out += ["", "## Fäden", "",
            "| id | kind | status | opened | resolved | entries | title |",
            "|---|---|---|---|---|---|---|"]
    for t in sorted(ledger.threads.values(), key=lambda r: r.thread_id):
        out.append(f"| {t.thread_id} | {t.kind} | {t.status} | {t.opened} | "
                   f"{t.resolved or ''} | {len(t.entries)} | {t.title} |")
    out += ["", "## Statuswechsel", ""]
    out += _bullets([
        f"{s.name} -> {s.value} ({s.entry.evidence}"
        f"{', ' + s.claimed_by if s.claimed_by else ''}), "
        f"{s.entry.session_id} @ {s.entry.citation_ts}: {s.entry.note}"
        for s in ledger.statuses
    ])
    out += ["", "## Haltungen", ""]
    out += _bullets([
        f"{a.name} -> {a.toward}: {a.value} ({a.entry.evidence}), "
        f"{a.entry.session_id} @ {a.entry.citation_ts}: {a.entry.note}"
        for a in ledger.attitudes
    ])
    out += ["", "## Warnungen", ""]
    out += _bullets(ledger.warnings)
    return "\n".join(out) + "\n"


# --- T7: world status and attitude -----------------------------------------
# Derived from the ledger, never from the model at emit time (T00 §4.6, §4.7).
# A claim never overrides an observed fact: it stays in the history, labelled
# with who said it, so the table can see both.


def _chronological(records: list) -> list:
    return sorted(records, key=lambda r: (r.entry.date, r.entry.citation_ts))


def _current(ordered: list):
    """The last observed entry, else the last entry of any evidence (T7 rule 1)."""
    observed = [r for r in ordered if r.entry.evidence == "observed"]
    return (observed or ordered)[-1]


def _since(entry: Entry, episodes: Episodes) -> str:
    labels = citation_labels([entry.url], episodes)
    return labels[0] if labels else entry.date


def _fact(value: str, entry: Entry, episodes: Episodes, claimed_by: str = "") -> dict:
    fact = {"value": value, "since": _since(entry, episodes),
            "at": entry.citation_ts, "evidence": entry.evidence}
    if claimed_by:
        fact["claimed_by"] = claimed_by
    return fact


def world_state_by_concept(
    ledger: Ledger, names: NameIndex, episodes: Episodes
) -> tuple[dict[str, dict], list[str]]:
    """``concept_id -> frontmatter fragment`` and the unmatched lines (T7 rules 1-5).

    The fragment holds any of ``world_status``, ``world_status_history`` and
    ``attitude``. Nothing here calls the model.
    """

    unmatched: list[str] = []
    statuses: dict[str, list[StatusRecord]] = {}
    for s in ledger.statuses:
        cid = names.lookup(s.name)
        if cid is None:
            unmatched.append(f"{s.name}: {s.value} (kein Konzept gefunden)")
            continue
        directory = cid.split("/", 1)[0]
        if s.value not in WORLD_STATUS_BY_DIR.get(directory, frozenset()):
            unmatched.append(f"{s.name}: {s.value} not allowed for {directory}")
            continue
        if not s.entry.citation_ts:
            unmatched.append(f"{s.name}: {s.value} ohne Zeitstempel")
            continue
        statuses.setdefault(cid, []).append(s)

    attitudes: dict[str, dict[str, list[AttitudeRecord]]] = {}
    for a in ledger.attitudes:
        cid = names.lookup(a.name)
        if cid is None:
            unmatched.append(f"{a.name}: attitude (kein Konzept gefunden)")
            continue
        directory = cid.split("/", 1)[0]
        if directory not in ATTITUDE_DIRS:
            unmatched.append(f"{a.name}: attitude not allowed for {directory}")
            continue
        if a.toward == PARTY:
            toward = "party"
        else:
            target = names.lookup(a.toward)
            if target is None or not target.startswith("characters/"):
                unmatched.append(f"{a.name} -> {a.toward}: attitude target is not a player character")
                continue
            toward = target
        if not a.entry.citation_ts:
            unmatched.append(f"{a.name} -> {a.toward}: attitude ohne Zeitstempel")
            continue
        attitudes.setdefault(cid, {}).setdefault(toward, []).append(a)

    out: dict[str, dict] = {}
    for cid, records in statuses.items():
        ordered = _chronological(records)
        current = _current(ordered)
        fragment: dict = {"world_status": _fact(current.value, current.entry, episodes, current.claimed_by)}
        if len(ordered) > 1:
            fragment["world_status_history"] = [
                _fact(r.value, r.entry, episodes, r.claimed_by) for r in ordered
            ]
        out[cid] = fragment
    for cid, per_target in attitudes.items():
        rows = []
        for toward, records in sorted(per_target.items()):
            cur = _current(_chronological(records))
            rows.append({"toward": toward, **_fact(cur.value, cur.entry, episodes)})
        out.setdefault(cid, {})["attitude"] = rows
    return out, unmatched


def _status_label(fact: dict) -> str:
    who = f" laut {fact['claimed_by']}" if fact.get("claimed_by") else ""
    return f"{STATUS_DE[fact['value']]}{who}"


def render_stand_section(fragment: dict, titles: dict[str, str]) -> str:
    """The deterministic ``## Stand`` body section (T00 §4.6). ``""`` for no facts.

    ``titles`` maps a concept id to its canonical name, so an attitude toward a
    PC renders as the name a reader knows.
    """

    if not fragment:
        return ""
    lines = ["## Stand", ""]
    status = fragment.get("world_status")
    if status:
        lines.append(f"- Status: {_status_label(status)} seit {status['since']} "
                     f"({EVIDENCE_DE[status['evidence']]}, {status['at']})")
        earlier = [h for h in fragment.get("world_status_history", []) if h != status]
        if earlier:
            lines.append("- Früher: " + "; ".join(
                f"{_status_label(h)} ({h['since']}, {EVIDENCE_DE[h['evidence']]})" for h in earlier))
    for a in fragment.get("attitude", []):
        who = "Haltung zur Gruppe" if a["toward"] == "party" else f"Haltung zu {titles.get(a['toward'], a['toward'])}"
        lines.append(f"- {who}: {ATTITUDE_DE[a['value']]} seit {a['since']} ({EVIDENCE_DE[a['evidence']]})")
    return "\n".join(lines)
