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

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from pnp_okf.okf import slugify

Evidence = Literal["observed", "claimed", "rumor", "speculation"]
ThreadKind = Literal["quest", "mystery", "promise", "debt", "deadline"]
ThreadStatus = Literal["open", "resolved", "abandoned"]
WorldStatus = Literal["alive", "dead", "missing", "captured", "transformed", "destroyed"]
Attitude = Literal["allied", "friendly", "neutral", "wary", "hostile"]

NEW_THREAD = "NEU"
PARTY = "Gruppe"


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
