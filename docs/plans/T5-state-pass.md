# T5 — The state pass: threads, status changes, attitudes, evidence

| | |
|---|---|
| Branch | `feat/state-pass` |
| Base | `origin/main` (after A2, A4, T3 merged; T4 recommended first so the glossary has no Events) |
| Depends on | A2 (retry predicate `is_retryable`), A4 (version constants pattern), T3 (`RULES_GLOSSARY`) |
| Design | [T00 §4.4–4.7, §5](T00-tracking-model.md), decisions D4, D5 |
| Cost | $0 for code. **HUMAN RUN**: trial `--limit 3` ≈ $0.10, then full ≈ $2–4 |
| Size | L. Do it in the commit order given; each commit leaves the suite green |

## Goal

Add a new subcommand, `pnp state`. It reads every transcript **sequentially
by date** and asks the model only for what *changed* in that session:

- **threads**: quests, mysteries, promises, debts, deadlines, each opened,
  advanced, resolved or abandoned;
- **status changes**: alive / dead / missing / captured / transformed /
  destroyed;
- **attitude changes**: NPC or faction toward the party or one PC;
- each item with a timestamp and an **evidence kind**
  (observed / claimed / rumor / speculation).

Results are cached per session. A pure fold (`Ledger`) turns the cached
outputs into a deterministic campaign state. This plan stops at the cache,
the ledger and a review report. Emitting into the bundle is T6 (threads) and
T7 (status, attitude).

## Why

See T00 §1. The existing extraction is entity-centric ("what exists"); this
pass is change-centric ("what happened to whom, and is it settled"). It runs
separately so it can't move concept ids (T00 principle 1).

## Files touched / created

| File | Change |
|---|---|
| `src/pnp_okf/state.py` | **new**: models, glossary, ledger, cache, LLM call, runner |
| `src/pnp_okf/prompts.py` | add `STATE_PROMPT_VERSION`, `STATE_SYSTEM`, `STATE_USER_TEMPLATE` |
| `src/pnp_okf/config.py` | `state_model` field, `DEEPSEEK_STATE_MODEL`, `for_tier("state")` |
| `src/pnp_okf/cli.py` | `state` subcommand, `cmd_state` |
| `tests/test_state_ledger.py` | **new** |
| `tests/test_state_runner.py` | **new** |
| `docs/architecture/PIPELINE.md` | new §3a "the state pass" (short) |
| `.env.example` (repo root) | document `DEEPSEEK_STATE_MODEL` |

---

## Commit 1: models and the ledger (pure, no LLM)

### 1.1 `src/pnp_okf/state.py` — models

Module docstring (write it fully, in this repo's style). It explains:

- the state pass is change-centric, sequential and separately cached;
- why it is sequential: thread identity is carried forward, never
  re-derived from wording (link `docs/plans/T00-tracking-model.md` §4.5);
- that `pnp run` never calls it, it only reads its cache (D4).

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
```

### 1.2 Ledger records

```python
from dataclasses import dataclass, field

from pnp_okf.okf import slugify


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
```

### 1.3 `Ledger`

```python
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
```

### 1.4 Tests: `tests/test_state_ledger.py`

Write the tests **first** (repo skill: test-driven-development), then the
code. They must cover:

```python
from pnp_okf.state import Ledger, SessionState, ThreadUpdate, StatusChange, AttitudeChange, render_open_threads


def _t(tid="NEU", title="Evakuierung", status="open", **kw):
    return ThreadUpdate(thread_id=tid, title=title, kind="quest", status=status,
                        note=kw.get("note", "n"), citation_ts="00:01:00",
                        involves=kw.get("involves", []), evidence=kw.get("evidence", "observed"))


def test_new_thread_is_minted_from_its_title():
    led = Ledger()
    led.apply("s1", "2026-01-01", "u", SessionState(threads=[_t()]))
    assert list(led.threads) == ["threads/evakuierung"]
    assert led.threads["threads/evakuierung"].opened == "s1"


def test_same_title_twice_gets_a_suffix():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t(), _t()]))
    assert list(led.threads) == ["threads/evakuierung", "threads/evakuierung_2"]


def test_update_by_id_keeps_identity_even_if_title_changes():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t()]))
    led.apply("s2", "d", "u", SessionState(threads=[_t("threads/evakuierung", "Ganz anderer Titel", "resolved")]))
    rec = led.threads["threads/evakuierung"]
    assert rec.title == "Evakuierung" and rec.status == "resolved" and rec.resolved == "s2"
    assert len(led.threads) == 1


def test_unknown_id_mints_and_warns():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t("threads/gibts_nicht", "X")]))
    assert "threads/x" in led.threads
    assert any("unknown thread id" in w for w in led.warnings)


def test_reopening_clears_resolved():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t(status="resolved")]))
    led.apply("s2", "d", "u", SessionState(threads=[_t("threads/evakuierung", status="open")]))
    assert led.threads["threads/evakuierung"].resolved is None


def test_open_threads_render_is_deterministic_and_excludes_closed():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t(title="B"), _t(title="A", status="resolved")]))
    text = render_open_threads(led)
    assert "threads/b" in text and "threads/a" not in text
    assert render_open_threads(Ledger()) == "(keine offenen Fäden)"


def test_status_and_attitude_are_recorded_with_evidence():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(
        status_changes=[StatusChange(name="Rotunas", value="dead", note="n", citation_ts="02:02:27")],
        attitudes=[AttitudeChange(name="Vitius", toward="", value="hostile", note="n", citation_ts="00:10:00", evidence="claimed")],
    ))
    assert led.statuses[0].value == "dead" and led.statuses[0].entry.evidence == "observed"
    assert led.attitudes[0].toward == "Gruppe" and led.attitudes[0].entry.evidence == "claimed"


def test_involves_is_deduplicated_in_first_seen_order():
    led = Ledger()
    led.apply("s1", "d", "u", SessionState(threads=[_t(involves=["Xenia", "Hof"])]))
    led.apply("s2", "d", "u", SessionState(threads=[_t("threads/evakuierung", involves=["Hof", "Brim"])]))
    assert led.threads["threads/evakuierung"].involves == ["Xenia", "Hof", "Brim"]
```

Commit: `feat(kb): add the state-pass models and a deterministic ledger`

---

## Commit 2: frozen glossary

### 2.1 Glossary functions in `state.py`

```python
from pathlib import Path

import yaml

from pnp_okf.resolve import _registry_data

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
        aliases = [a for a in (e.get("aliases") or []) if a][: _MAX_ALIASES]
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
```

`knowledge_root` is `Paths._knowledge_root`. It is a property with a leading
underscore; add a public alias property `knowledge_root` to `Paths` in
`config.py` (one line: `return self._knowledge_root`).

### 2.2 Tests (append to `tests/test_state_ledger.py`)

- `build_glossary` excludes Events, caps aliases at 3, and sorts by type
  order then name (build a tmp registry plus an empty `entity_rules.yaml`).
- `write_glossary` → `load_glossary` round-trips, and the header survives.
- `render_glossary` output is byte-identical across two calls.

Commit: `feat(kb): freeze the state-pass glossary to a committed file`

---

## Commit 3: prompt, config, cached LLM call

### 3.1 `prompts.py`

Append at the end of the file:

```python
# Version of the state-pass prompt (T5). Independent of the extraction and
# synthesis versions (A4): bumping it re-runs only `pnp state` (~$2-4), never
# extraction, so it cannot move a concept id.
STATE_PROMPT_VERSION = "1"

STATE_SYSTEM = (
    """\
Du führst das Kampagnen-Protokoll einer deutschsprachigen Daggerheart-Runde.
Du erhältst das Transkript EINER Session, eine Liste bekannter Namen und die
Liste der offenen Fäden VOR dieser Session. Melde NUR, was sich in DIESER
Session verändert hat.

1. Fäden (threads): Aufträge (quest), Rätsel (mystery), Versprechen (promise),
   Schulden/Gefallen (debt), Fristen (deadline).
   - Ein bekannter Faden: nutze seine thread_id aus der Liste EXAKT.
   - Ein neuer Faden: thread_id "NEU" und ein kurzer, eindeutiger Titel
     ("Evakuierung des Halblingshofs", nicht "Auftrag").
   - status ist der Stand am ENDE der Session: open, resolved, abandoned.
   - Melde einen Faden nur, wenn in dieser Session etwas mit ihm passiert.
2. Statuswechsel (status_changes): alive, dead, missing, captured,
   transformed, destroyed (destroyed nur für Orte/Gegenstände).
3. Haltungen (attitudes): wie eine Figur oder Fraktion zur Gruppe ("Gruppe")
   oder zu EINEM Spielercharakter steht: allied, friendly, neutral, wary,
   hostile. Nur bei einer erkennbaren Änderung oder ersten Festlegung.

Beleg-Art (evidence) für JEDEN Eintrag:
- observed: am Tisch gespielt oder von der Spielleitung als Tatsache erzählt.
- claimed: eine Figur BEHAUPTET es (claimed_by = wer), die Gruppe sah es nicht.
- rumor: Gerücht, Legende, Hörensagen.
- speculation: Vermutung der Spielenden.
Die Spielleitung spricht auch NPCs: was ein NPC sagt, ist "claimed", nicht
"observed" -- auch wenn die Spielleitung es ausspricht.

Regeln:
- Erfinde nichts. Jeder Eintrag braucht einen Zeitstempel (HH:MM:SS).
- Benutze Namen aus der Namensliste, wenn die Figur dort steht.
- Reale Personen (Spielende) sind KEINE Figuren. Ein Name in Klammern hinter
  einem Sprecher ist die Figur; der Name davor ist die reale Person.
- Regelmechanik ist kein Weltgeschehen:
"""
    + RULES_GLOSSARY
)

STATE_USER_TEMPLATE = """\
Session-ID: {session_id}
Datum: {date}

Bekannte Namen:
{glossary}

Offene Fäden vor dieser Session:
{open_threads}

Transkript:
{dialogue}
"""
```

`RULES_GLOSSARY` must be defined above `STATE_SYSTEM` in the file (T3 put it
near the top), or this raises NameError at import.

Pin the new prompt the same way A4 pins the others. In
`tests/test_prompt_pins.py`:

- add `state_fingerprint()`, hashing `STATE_SYSTEM`, `STATE_USER_TEMPLATE`
  and `json.dumps(SessionState.model_json_schema(), sort_keys=True)`;
- add `STATE_PINS = {"1": "<fill>"}`;
- add `test_state_prompt_matches_its_version`.

Fill the hash the way A4 step 5 describes.

### 3.2 `config.py`

- `DeepSeekConfig` gets the field `state_model: str = DEFAULT_MODEL`.
- `from_env`: `state = os.environ.get("DEEPSEEK_STATE_MODEL", model).strip()`,
  passed as `state_model=state`.
- `for_tier`: add before the `deep` check:
  ```python
        if tier == "state":
            return replace(self, model=self.state_model)
  ```
- Document `DEEPSEEK_STATE_MODEL` in the repo-root `.env.example` under the
  LLM section, commented out, with one line on cost (~$2–4 per full state
  pass on pro).

### 3.3 Cache and call in `state.py`

```python
import hashlib
import json
import logging

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from pnp_okf.config import DeepSeekConfig
from pnp_okf.llm_client import build_client, is_retryable   # is_retryable from A2
from pnp_okf.models import SessionTranscript
from pnp_okf.prompts import STATE_PROMPT_VERSION, STATE_SYSTEM, STATE_USER_TEMPLATE

log = logging.getLogger(__name__)


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
```

Put the system prompt first and the glossary early in the user message: the
provider's prefix cache only hits on an exact shared prefix (PIPELINE.md §6).

If A2's `is_retryable` doesn't treat `pydantic.ValidationError` as
retryable, extend A2's predicate here in the same PR. A malformed JSON reply
is worth one resample. Follow the extract.py precedent: it retries a recap
with no entities.

### 3.4 Runner

```python
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
```

### 3.5 Tests: `tests/test_state_runner.py`

Use a fake client like `tests/test_extract_guard.py::_FakeClient`, extended
to record the `messages` of each call and to return a different canned
payload per call (a list consumed in order). Cover:

1. Two sessions. The first returns a `NEU` thread; the second call's user
   message contains `threads/<slug>` (carried forward). Assert
   `run.called == 2`.
2. A second `run_state` over the same transcripts and cache makes **0**
   calls (`run.cached == 2`).
3. `estimate=True` on an empty cache makes 0 client calls and reports
   `uncached_estimate == 2`.
4. Changing session 1's cached output (write a different blob under its key)
   changes session 2's key: with `estimate=True`, session 2 reports uncached.
5. `state_cache_key` changes when the glossary text changes.

Build `SessionTranscript`s with 2–3 `Segment`s each. Give the config
`DeepSeekConfig(api_key="x", model="m", base_url="https://example.invalid")`.
Call `_call_llm.__wrapped__` where you need to bypass retry, as
`test_extract_guard.py` does.

Commit: `feat(kb): add the cached, sequential state pass`

---

## Commit 4: CLI `pnp state` and a review report

### 4.1 `cli.py`

```python
def cmd_state(args: argparse.Namespace) -> int:
    """Threads, status changes and attitudes per session (T5). Costs money
    unless every session is cached -- run with --estimate first."""

    paths = Paths.resolve(args.transcripts, args.bundle, args.cache)
    if args.session:
        log.error("pnp state is sequential: use --limit N (the first N sessions), not --session.")
        return 2
    if args.refresh_glossary:
        rows = build_glossary(paths.registry_path)
        out = write_glossary(paths.knowledge_root, rows)
        log.info("Wrote %d glossary entries to %s -- every session's state key changes.", len(rows), out)
        return 0
    rows = load_glossary(paths.knowledge_root)
    if not rows:
        log.error("No %s yet -- run `pnp state --refresh-glossary` first.", GLOSSARY_FILENAME)
        return 2
    cfg = DeepSeekConfig.from_env().for_tier("state")
    transcripts = sorted(load_transcripts(paths.transcript_dir), key=lambda t: (t.date, t.session_id))
    if args.limit:
        transcripts = transcripts[: args.limit]
    run = run_state(transcripts, cfg, paths.cache_dir, rows, estimate=args.estimate)
    if args.estimate:
        print(f"{run.cached} cached, {run.uncached_estimate} would be called on {cfg.model}.")
        return 0
    report = render_state_report(run.ledger)
    out = paths.cache_dir / "state" / "ledger_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    log.info("%d called, %d cached; report: %s", run.called, run.cached, out)
    for w in run.ledger.warnings:
        log.warning("[state] %s", w)
    return 0
```

Parser (in `_build_parser`, after `extract`):

```python
    state = sub.add_parser("state", help="Threads/status/attitude pass (T5; costs money)")
    _add_common(state)
    state.add_argument("--estimate", action="store_true", help="Count uncached sessions; call nothing")
    state.add_argument("--refresh-glossary", action="store_true",
                       help="Rewrite knowledge/state_glossary.yaml from the registry (invalidates the state cache)")
    state.set_defaults(func=cmd_state)
```

### 4.2 `render_state_report(ledger) -> str` in `state.py`

Plain markdown for a human reviewer:

1. Counts by thread kind and status.
2. One table of all threads: id, kind, status, opened, resolved, entries,
   title.
3. The status changes, with evidence.
4. The attitude changes, with evidence.
5. The warnings.

Pure function. Test that it contains each thread id and the warning text.

### 4.3 PIPELINE.md

Add a short **§3a "The state pass"**:

- what it does;
- it is sequential;
- what keys it (the cache key);
- the glossary file;
- `pnp run` only reads it;
- the cost;
- the cascade rule ("an edit to an early session re-runs every later one").

Add one row to §13: "touch the state pass → T00 §5".

Commit: `feat(kb): pnp state subcommand with estimate and review report`

---

## Verify (offline)

```bash
cd services/kb
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pnp_okf.cli state --help
cd ../.. && ruff check .
```

## HUMAN RUN (after merge)

1. `pnp state --refresh-glossary`. Commit `knowledge/state_glossary.yaml` on
   a branch `chore/state-glossary`.
2. `pnp state --estimate` → expect `0 cached, 68 would be called`
   (or 71 with the new sessions).
3. Trial: `pnp state --limit 3` (~$0.10). Read
   `.cache/state/ledger_report.md` against the transcripts of the first 3
   sessions (P-01..P-03). Check:
   - Are the threads real? Is there anything obvious missing?
   - Is the evidence right? In Session Zero, NPC claims should be `claimed`.
   - Are there player names in `involves`? (They must not appear.)

   If quality is poor, **adjust the prompt, bump `STATE_PROMPT_VERSION`**
   and repeat the trial. That is cheap at `--limit 3`.
4. Full run `pnp state` (~$2–4, off-peak: not 01–04 or 06–10 UTC on
   weekdays).
5. Paste the report's counts into the PR for T6.

## Done when

- [ ] Four commits merged, suite green, `pnp state --estimate` makes no network call.
- [ ] Trial reviewed by the human; full run cached; report counts recorded.

## Out of scope

- Writing anything into `knowledge/bundle/` (T6, T7).
- Re-running extraction, or adding the glossary to `EXTRACT_SYSTEM` (B2).
- Parallelism. The pass is sequential by design; 68 calls take ~1–2 h.
