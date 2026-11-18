"""Subscription launcher for the extraction benchmark (plan: docs/plans/E2-subscription-launcher.md).

extraction_benchmark.py stays offline: it hashes, validates and scores files. This module is
the one place that starts a model, always as a fresh headless Claude Code or Codex process on
the human's subscription login: no API key, no provider SDK, no tools for the model. Inputs are
inlined into the prompt, so a judge never needs file access and never sees a path, a label or
a model name of the output it grades.

Resumable by design: a task is pending exactly when its output file is missing, so a rerun
after a usage limit (exit 75) picks up where the last run stopped. A limit on one host stops
that host only; the other host keeps working.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from functools import partial
from pathlib import Path

import extraction_benchmark as eb
from extraction_benchmark import BenchError

QUOTA = 75  # EX_TEMPFAIL: a host hit its usage limit; rerun the same command after the reset.
HOSTS = ("claude-code", "codex")
API_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY")
# Codex has no "no tools" switch (EXTRACTION-BENCHMARK.md §5). Any of these items means the
# worker looked beyond its prompt, which breaks blinding: the reply is rejected.
FORBIDDEN_ITEMS = ("command_execution", "file_change", "mcp_tool_call", "web_search")
_QUOTA_TEXT = re.compile(r"usage limit|rate limit|hit your .*limit", re.I)
_ID = re.compile(r"[a-z0-9]+")
TIMEOUT_S = 1800
LOG_FILE = "launch.log.jsonl"

# Plain ASCII without quotes or & | < > ^ %: the npm .cmd shims pass arguments through cmd.exe.
SYSTEM_LINE = "Follow the task in the user message exactly. Use no tools. Reply with the requested JSON only."

# Task texts live here as constants, not as .txt files: git autocrlf would change a file's
# bytes per checkout and with them prompt_sha256, which pins judges in history and calibration.
# T5-T7 are the headers proven in the hand-run grading of 2026-11-15; T4 is the doc's T4
# without file access. Generation (T3) sends the case's prompt.txt unchanged.
PROMPTS = {
    "repair": """TASK: fix only the format of a reply that failed validation.

You get the reply and the validator error below. You have no tools. Do not call other models or APIs.
Change format only: JSON syntax, code fences, brackets and commas, a field's type, or a single
value the error names (for example a timestamp in the wrong form). For a named value, change
only what the error names, as little as possible. Never change any wording in the recap or in
notes. Do not add, remove or reorder entities, claims or sentences.

Reply with the repaired JSON object only, no commentary, no code fence.""",
    "inventory": """TASK: list the checkable claims in one anonymous extraction of a tabletop-RPG session.

Below is the extraction's text, already split into numbered sentences: the recap ("r" ids) and the
note of each entity record ("e<record>." ids). You do not see the transcript and you do not judge
truth. You only decide, per sentence, what is a checkable claim and which claims say the same thing.
You have no tools. Do not call other models or APIs.

For every sentence id give one entry:
- "kind": "claim" if the sentence asserts something about the game world or the session's events
  that could be checked against a transcript; "not_claim" for headings, pure transitions, or text
  that asserts nothing.
- "group": a group name ("g001", "g002", ...). Claims that state the same fact, anywhere in the
  recap or in any note, share one group. A claim and its contradiction get different groups.
  Different facts never share a group. "not_claim" entries get "group": null.
- "parts": optional. Only when one sentence holds several clearly separate facts, split it:
  a list of {"span": "<exact, character-for-character piece of that sentence>", "group": "..."}.
  The pieces together should cover the factual content. Do not split a single fact.

Reply with one JSON object only, no commentary, no code fence:
{"sentences": {"r1": {"kind": "claim", "group": "g001"},
               "e0.1": {"kind": "claim", "group": null,
                        "parts": [{"span": "...", "group": "g002"}, {"span": "...", "group": "g003"}]},
               "e0.2": {"kind": "not_claim", "group": null}}}
Every sentence id must appear exactly once.""",
    "judge_a": """TASK: judge the factual claims and the citation locators of one anonymous extraction of a
tabletop-RPG session, against the transcript only.

You get the transcript (one segment per line, id first), the extraction (a recap and entity
records), and a list of claims taken from it. You are not told which system made the extraction; do
not guess. Use only the transcript: not what you may know about this campaign or setting.
You have no tools. Do not run commands or read files. Do not call other models or APIs.

Claims: give each claim id one verdict:
- "supported": the transcript supports it. A belief, rumour or uncertain statement that the
  extraction reports as such, and that a speaker really voiced, is "supported".
- "contradicted": the transcript says otherwise (wrong person, wrong fact, a rumour stated as fact
  that the transcript marks as uncertain counts here only if it changes the meaning).
- "unsupported": nothing in the transcript supports it.
- "unresolved": the transcript is too unclear to decide.
Transcription spelling variants of names are not errors. Claims that share a "group" state the same
fact and must get the same verdict.

Locators: each entity record has a citation timestamp; the "window" column lists the segment that
contains it plus two segments either side. Verdict per record index:
- "supported": a passage relevant to that entity or event starts inside the window.
- "not_supported": no such passage inside the window.
- "unresolved": unclear.

For every item give "segments" (at most three segment ids you relied on; empty if none) and "why"
(at most 15 words).

Reply with one JSON object only, no commentary, no code fence:
{"claims":   {"C001": {"verdict": "supported", "segments": ["S012"], "why": "..."}},
 "locators": {"0": {"verdict": "supported", "segments": ["S012"], "why": "..."}}}
Every claim id and every record index must appear exactly once.""",
    "judge_b": """TASK: judge one anonymous extraction of a tabletop-RPG session against a gold reference.

You get the transcript (one segment per line, id first), the gold reference (entities, facts, note
requirements, critical rules) and the extraction (a recap and entity records, each with a note).
You are not told which system made the extraction; do not guess. The gold reference defines what
counts; use the transcript only to settle doubt. Do not use what you may know about this campaign.
You have no tools. Do not run commands or read files. Do not call other models or APIs.
Transcription spelling variants of names (also those listed as aliases) are the same name.

1. "facts": for every gold fact id, is the fact stated anywhere in the extraction (recap or any note)?
   "present" (stated, including its material qualifiers such as "allegedly" or "according to X"),
   "partial" (stated, but a material qualifier or part is missing), "absent",
   "conflicting" (the extraction states the opposite), "unresolved".
   Give "spans": at most one short exact quote from the extraction (empty list if absent).
2. "notes": for every gold note-requirement id (fact + target entity): is that fact stated in the
   NOTE of a record that represents the target entity? "present", "absent" (not in any note, or only
   in the recap, or the target entity has no record), "wrong_entity" (stated only in the note of a
   record for a different entity), "unresolved". "entity_index": index of the record whose note
   holds it, else null.
3. "entities": for every record index: "match" is "gold:<gold entity id>" (same entity as that gold
   entity, aliases included), "extra_supported" (a real entity of this session that the gold does
   not list; give transcript segments), "duplicate_of:<lower index>" (same entity as an earlier
   record), "unsupported" (not an entity the transcript supports, e.g. a player or a rules term),
   or "unresolved". "type_ok": for a gold match, the record's type is one of the gold entity's
   accepted types; for "extra_supported", the type is reasonable; otherwise false. "subtype_ok":
   for a gold match, the record's subtype is in the accepted subtype list of that type, or that
   list is null; for "extra_supported", the subtype is reasonable or empty; otherwise false.
4. "critical": for every critical rule id: "violated" (the extraction meets the rule's trigger),
   "not_violated", "unresolved". Give at most one exact quote in "spans" if violated.

"why" is at most 12 words everywhere.

Reply with one JSON object only, no commentary, no code fence:
{"facts":    {"F001": {"verdict": "present", "spans": ["..."], "why": "..."}},
 "notes":    {"N001": {"verdict": "present", "entity_index": 0, "why": "..."}},
 "entities": {"0": {"match": "gold:E01", "type_ok": true, "subtype_ok": true, "segments": ["S012"]}},
 "critical": {"K01": {"verdict": "not_violated", "spans": [], "why": "..."}}}
Every gold fact id, note id, critical id and every record index must appear exactly once.""",
}


def prompt_sha(name: str) -> str:
    return eb.sha((SYSTEM_LINE + "\n" + PROMPTS[name]).encode("utf-8"))


# --- config and environment ---------------------------------------------------------------


def _check_worker(where: str, worker: dict) -> None:
    if worker.get("host") not in HOSTS:
        raise BenchError(f"{where}: host must be one of {', '.join(HOSTS)}, not {worker.get('host')!r}")
    for field in ("model", "effort"):
        if not worker.get(field):
            raise BenchError(f"{where}: {field} missing")


def load_config_dict(config: dict) -> dict:
    for judge in config.get("judges", []):
        # load_judgments only reads files named <packet>.<[a-z0-9]+>.json: any other id would be
        # graded, paid for, and then silently ignored by scoring.
        if not _ID.fullmatch(str(judge.get("id", ""))):
            raise BenchError(f"judge id {judge.get('id')!r} must match [a-z0-9]+")
        _check_worker(f"judge {judge['id']}", judge)
    _check_worker("inventory", config.get("inventory", {}))
    for arm in config.get("arms", []):
        _check_worker(f"arm {arm.get('label')}", arm)
    return config


def load_config(path: Path) -> dict:
    return load_config_dict(eb.read_json(path))


def check_env(environ) -> None:
    keys = [k for k in API_KEYS if environ.get(k)]
    if keys:
        raise BenchError(f"API key set in this shell ({', '.join(keys)}): benchmark runs use subscriptions only")
    # Same tripwire as approve_gold: only the human's terminal or the scheduler spends quota.
    if "CLAUDECODE" in environ or any(k.startswith("CODEX_") for k in environ):
        raise BenchError("refusing to launch from inside an agent session; run it in your own terminal")


def child_env(environ) -> dict:
    return {k: v for k, v in environ.items() if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}


# --- processes ----------------------------------------------------------------------------


def _exe(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise BenchError(f"{name} CLI not found on PATH")
    return path


def _spawn(argv: list[str], stdin_text: str, cwd, env: dict, timeout: int) -> tuple[int, str, str]:
    # The only subprocess call in the benchmark. The prompt goes in on stdin, never as an argument.
    try:
        done = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    return done.returncode, done.stdout or "", done.stderr or ""


def argv_for(host: str, model: str, effort: str, out: Path | None) -> list[str]:
    # Flags from the Gate 0 probe (EXTRACTION-BENCHMARK.md §5). Model and effort are always explicit.
    if host == "claude-code":
        return [
            _exe("claude"),
            "-p",
            "--model",
            model,
            "--effort",
            effort,
            "--tools",
            "",
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--system-prompt",
            SYSTEM_LINE,
            "--output-format",
            "json",
        ]
    # `-c key=value` falls back to a plain string when the value is not TOML, so the effort
    # needs no inner quotes that cmd.exe could mangle.
    return [
        _exe("codex"),
        "exec",
        "-m",
        model,
        "-c",
        f"model_reasoning_effort={effort}",
        "-s",
        "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
        "-o",
        str(out),
        "-",
    ]


def _result(ok=False, text="", usage=None, reported_model=None, error="", quota=False) -> dict:
    return {"ok": ok, "text": text, "usage": usage, "reported_model": reported_model, "error": error, "quota": quota}


def parse_claude(stdout: str, requested: str) -> dict:
    try:
        doc = json.loads(stdout)
    except json.JSONDecodeError:
        return _result(error="claude: no JSON result on stdout")
    if doc.get("is_error"):
        quota = doc.get("api_error_status") == 429 or doc.get("api_error") == "usage_limit_reached"
        return _result(error=str(doc.get("result") or doc.get("api_error") or "claude error"), quota=quota)
    models = list(doc.get("modelUsage") or {})
    # Claude Code can switch models under quota pressure; a judge or arm answered by another
    # model must not be recorded under the requested one.
    if requested not in models:
        return _result(error=f"model fallback: requested {requested}, host reported {', '.join(models) or 'none'}")
    return _result(ok=True, text=str(doc.get("result") or ""), usage=doc.get("usage"), reported_model=requested)


def parse_codex(stdout: str, last_text: str) -> dict:
    usage = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind in ("turn.failed", "error"):
            message = str((event.get("error") or {}).get("message") or event.get("message") or kind)
            return _result(error=message, quota=bool(_QUOTA_TEXT.search(message)))
        item = event.get("item") or {}
        if kind == "item.completed" and item.get("type") in FORBIDDEN_ITEMS:
            return _result(error=f"tool use ({item['type']}) breaks blinding")
        if kind == "turn.completed":
            usage = event.get("usage")
    if not last_text.strip():
        return _result(error="codex: empty answer")
    # Codex events do not echo the model: the requested one is recorded (doc §5).
    return _result(ok=True, text=last_text, usage=usage)


_VERSIONS: dict[str, str] = {}


def cli_version(host: str, env: dict) -> str:
    if host not in _VERSIONS:
        _, out, _ = _spawn([_exe("claude" if host == "claude-code" else "codex"), "--version"], "", None, env, 60)
        _VERSIONS[host] = out.strip()
    return _VERSIONS[host]


def call(host: str, model: str, effort: str, prompt: str, environ) -> dict:
    env = child_env(environ)
    tmp = Path(tempfile.mkdtemp(prefix="pnp-bench-"))  # empty, outside the repo
    try:
        out = tmp / "last.txt" if host == "codex" else None
        argv = argv_for(host, model, effort, out)
        started = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
        t0 = time.monotonic()
        rc, stdout, stderr = _spawn(argv, prompt, str(tmp), env, TIMEOUT_S)
        seconds = round(time.monotonic() - t0, 1)
        if host == "claude-code":
            res = parse_claude(stdout, model)
        else:
            res = parse_codex(stdout, out.read_text(encoding="utf-8") if out.is_file() else "")
        if not res["ok"] and _QUOTA_TEXT.search(stderr):
            res["quota"] = True
        if res["ok"] and rc != 0:
            res = _result(error=f"exit {rc}")
        if not res["ok"] and not res["error"]:
            res["error"] = stderr.strip()[-300:] or f"exit {rc}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res.update(
        host=host,
        model=model,
        effort=effort,
        argv=argv[1:],
        started=started,
        seconds=seconds,
        finished=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        cli=cli_version(host, env),
        style="anthropic" if host == "claude-code" else "openai",
    )
    return res


def log_call(root: Path, entry: dict) -> None:
    # The quota ledger: what each run actually spent, including failures and limit hits.
    root.mkdir(parents=True, exist_ok=True)
    with (root / LOG_FILE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _usage_doc(res: dict) -> dict:
    return {
        "style": res["style"],
        "model": res["model"],
        "turns": [res["usage"]] if res["usage"] else [],
        "provenance": {"host": res["host"], "cli": res["cli"], "started": res["started"], "finished": res["finished"]},
    }


class _Session:
    """One launcher process: which hosts are out of quota, how many tasks failed."""

    def __init__(self, root: Path, environ):
        check_env(environ)
        self.root, self.environ = root, environ
        self.exhausted: set[str] = set()
        self.failures = 0

    def ask(self, task: str, worker: dict, prompt: str) -> dict | None:
        host = worker["host"]
        if host in self.exhausted:
            return None
        res = call(host, worker["model"], worker["effort"], prompt, self.environ)
        log_call(
            self.root,
            {k: res[k] for k in ("host", "model", "effort", "ok", "quota", "error", "started", "seconds", "cli")}
            | {"task": task},
        )
        if res["quota"]:
            self.exhausted.add(host)
            print(f"{host}: usage limit, skipping its remaining tasks: {res['error']}", file=sys.stderr)
            return None
        if not res["ok"]:
            self.fail(f"{task}: {res['error']}")
            return None
        return res

    def fail(self, message: str) -> None:
        self.failures += 1
        print(f"failed: {message}", file=sys.stderr)

    def code(self) -> int:
        return QUOTA if self.exhausted else 1 if self.failures else 0


def _next_free(folder: Path, stem: str, suffix: str) -> Path:
    n = 1
    while (folder / f"{stem}{n}{suffix}").exists():
        n += 1
    return folder / f"{stem}{n}{suffix}"


def _parse_reply(text: str) -> dict:
    from pnp_okf.extract import _extract_json_block

    reply = json.loads(_extract_json_block(text))
    if not isinstance(reply, dict):
        raise ValueError("reply is not a JSON object")
    return reply


def _header(worker: dict, prompt_name: str) -> dict:
    return {
        "host": worker["host"],
        "model": worker["model"],
        "effort": worker["effort"],
        "prompt_sha256": prompt_sha(prompt_name),
    }


# --- prompt builders ------------------------------------------------------------------------


def transcript_lines(segments) -> str:
    # Positional ids, the same S### the gold cites.
    return "\n".join(
        f"S{i:03d} [{eb._hms(seg['start'])}] {seg['speaker']}: {str(seg['text']).strip()}"
        for i, seg in enumerate(segments)
    )


def sentence_ids(extraction: dict) -> list[tuple[str, str, str, str | None]]:
    out = [(f"r{k}", "recap", s, None) for k, s in enumerate(eb.sentences(extraction["recap"]), 1)]
    for i, ent in enumerate(extraction["entities"]):
        out += [
            (f"e{i}.{k}", f"entity:{i}", s, ent.get("name", ""))
            for k, s in enumerate(eb.sentences(ent.get("note", "")), 1)
        ]
    return out


def inventory_prompt(extraction: dict) -> str:
    lines = [
        f"{sid}: {s}" if label is None else f"{sid} [{label}]: {s}" for sid, _, s, label in sentence_ids(extraction)
    ]
    return PROMPTS["inventory"] + "\n\nSENTENCES\n" + "\n".join(lines)


def inventory_from_reply(extraction: dict, text: str, header: dict) -> dict:
    # Python splits the sentences, the model only labels kind and group. That keeps the
    # inventory verbatim by construction instead of hoping the model copies spans exactly.
    reply = _parse_reply(text).get("sentences") or {}
    ids = sentence_ids(extraction)
    missing = [sid for sid, *_ in ids if sid not in reply]
    if missing:
        raise BenchError(f"inventory reply misses {len(missing)} sentence id(s), e.g. {missing[0]}")
    claims: list[dict] = []

    def add(loc, span, group, kind) -> None:
        claims.append({"id": f"C{len(claims) + 1:03d}", "loc": loc, "span": span, "group": group, "kind": kind})

    for sid, loc, sentence, _ in ids:
        entry = reply[sid] if isinstance(reply[sid], dict) else {}
        if entry.get("kind") != "claim":
            add(loc, sentence, None, "not_claim")
            continue
        parts = entry.get("parts") or []
        exact = [p for p in parts if isinstance(p, dict) and str(p.get("span", "")).strip() and p["span"] in sentence]
        if parts and len(exact) == len(parts):
            for part in exact:
                add(loc, part["span"], part.get("group"), "claim")
        else:
            # A part that is not verbatim falls back to the whole sentence: a near miss must not waste the call.
            add(loc, sentence, entry.get("group") or (exact[0].get("group") if exact else None), "claim")
    for claim in claims:
        if claim["kind"] == "claim" and not claim["group"]:
            claim["group"] = f"u{claim['id']}"  # ungrouped claim: a group of its own
    inventory = {"output_sha256": eb.hash_obj(extraction), "config": header, "claims": claims}
    errors = eb.validate_inventory(inventory, extraction)
    if errors:
        raise BenchError("inventory invalid: " + "; ".join(errors[:3]))
    return inventory


def _window(entity: dict, segments, width: int) -> str:
    from pnp_okf.context import _parse_ts

    seconds = _parse_ts(str(entity.get("citation_ts") or ""))
    if seconds is None:
        return "none"
    i = eb.segment_at(segments, seconds)
    return f"S{max(0, i - width):03d}-S{min(len(segments) - 1, i + width):03d}"


def packet_prompt(
    packet: str, extraction: dict, inventory: dict | None, gold: dict | None, segments, rubric: dict
) -> str:
    parts = [PROMPTS["judge_a" if packet == "A" else "judge_b"], "TRANSCRIPT\n" + transcript_lines(segments)]
    if packet == "B":
        reference = {k: gold[k] for k in ("entities", "facts", "notes", "critical")}
        parts.append("GOLD REFERENCE\n" + json.dumps(reference, ensure_ascii=False, indent=1))
    parts.append("EXTRACTION RECAP\n" + extraction["recap"])
    records = []
    for i, ent in enumerate(extraction["entities"]):
        record = {"index": i, **{k: ent.get(k, "") for k in ("name", "type", "subtype", "citation_ts")}}
        if packet == "A":
            record["window"] = _window(ent, segments, rubric["g_window_segments"])
        record["note"] = ent.get("note", "")
        records.append(record)
    parts.append("EXTRACTION RECORDS\n" + json.dumps(records, ensure_ascii=False, indent=1))
    if packet == "A":
        claims = [
            {"id": c["id"], "loc": c["loc"], "group": c["group"], "claim": c["span"]}
            for c in inventory["claims"]
            if c["kind"] == "claim"
        ]
        parts.append(
            "CLAIMS (loc: recap, or entity:<record index>)\n" + json.dumps(claims, ensure_ascii=False, indent=1)
        )
    return "\n\n".join(parts)


def repair_prompt(raw: str, errors: list[str]) -> str:
    return PROMPTS["repair"] + "\n\nVALIDATOR ERROR\n" + "\n".join(errors) + "\n\nREPLY\n" + raw


# --- grading --------------------------------------------------------------------------------


def _keep_private(run_dir: Path, folder: Path, name: str, text: str, res: dict, s: _Session, why: str) -> None:
    # A rejected reply is still evidence and still cost: text goes to private/, usage stays in
    # the grading folder (usage.*.json is summed into grading cost; the name matches no judgment).
    raw_dir = run_dir / "private" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{folder.name}.{name}.txt").write_text(text, encoding="utf-8")
    eb.write_once(_next_free(folder, f"usage.{name}.rejected", ".json"), eb._pretty(_usage_doc(res)))
    s.fail(f"{folder.name} {name}: {why}")


def _move_aside(folder: Path, name: str) -> None:
    # Stale judgments are kept (renamed so no loader matches them): their cost was real.
    target = _next_free(folder, f"{name}.stale", ".json")
    n = target.name[len(name) + len(".stale") : -len(".json")]
    (folder / f"{name}.json").rename(target)
    for old, new in (
        (f"usage.{name}.json", f"usage.{name}.stale{n}.json"),
        (f"{name}.x.json", f"{name}.x.stale{n}.json"),
    ):
        if (folder / old).is_file():
            (folder / old).rename(folder / new)


def _inventory(s: _Session, run_dir: Path, folder: Path, extraction: dict, worker: dict) -> None:
    header = _header(worker, "inventory")
    res = s.ask(f"{folder.name} inventory", worker, inventory_prompt(extraction))
    if res is None:
        return
    try:
        inventory = inventory_from_reply(extraction, res["text"], header)
    except (BenchError, ValueError, KeyError, TypeError, AttributeError) as exc:
        _keep_private(run_dir, folder, "inventory", res["text"], res, s, str(exc))
        return
    eb.write_once(folder / "inventory.json", eb._pretty(inventory))
    eb.write_once(folder / "usage.inventory.json", eb._pretty(_usage_doc(res)))


def _judgment(s: _Session, run_dir: Path, case_dir: Path, folder: Path, packet: str, judge: dict, build) -> None:
    name = f"{packet}.{judge['id']}"
    path = folder / f"{name}.json"
    header = _header(judge, "judge_a" if packet == "A" else "judge_b")
    expected = eb.expected_binds(packet, folder, case_dir)
    if path.is_file():
        doc = eb.read_json(path)
        if doc.get("judge") == header and not eb.stale_reasons(packet, doc, expected):
            return
        _move_aside(folder, name)
    res = s.ask(f"{folder.name} {name}", judge, build())
    if res is None:
        return
    try:
        reply = _parse_reply(res["text"])
        # Python writes binds and judge header; a model never copies a hash.
        doc = {"binds": expected, "judge": header, **{k: reply.get(k) or {} for k in eb._SECTIONS[packet]}}
        eb._check_judgment_file(path, packet, doc)
    except (BenchError, ValueError, AttributeError) as exc:
        _keep_private(run_dir, folder, name, res["text"], res, s, str(exc))
        return
    eb.write_once(path, eb._pretty(doc))
    eb.write_once(folder / f"usage.{name}.json", eb._pretty(_usage_doc(res)))


def grade(root: Path, run: str, case: str, config: dict, packets=("A", "B"), *, environ=None, session=None) -> int:
    load_config_dict(config)
    s = session or _Session(root, os.environ if environ is None else environ)
    run_dir, case_dir = eb._run_dir(root, run), eb._case_dir(root, case)
    if not (run_dir / "attempts").is_dir():
        raise BenchError(f"run {run} has no attempts under {run_dir}")
    eb.validate_run(run_dir, case_dir)
    eb.prepare_grading(run_dir, case_dir)
    segments = eb.load_segments(case_dir / "source.json")
    rubric = eb.read_json(eb._rubric_path(case_dir))
    gold = eb._gold_for_scoring(case_dir)[0] if "B" in packets else None
    for folder in eb._graded_folders(run_dir):
        extraction = eb.read_json(folder / "output.json")
        if not (folder / "inventory.json").is_file():
            _inventory(s, run_dir, folder, extraction, config["inventory"])
        for judge in config["judges"]:
            if "B" in packets:
                _judgment(
                    s,
                    run_dir,
                    case_dir,
                    folder,
                    "B",
                    judge,
                    partial(packet_prompt, "B", extraction, None, gold, segments, rubric),
                )
            if "A" in packets and (folder / "inventory.json").is_file():
                inventory = eb.read_json(folder / "inventory.json")
                _judgment(
                    s,
                    run_dir,
                    case_dir,
                    folder,
                    "A",
                    judge,
                    partial(packet_prompt, "A", extraction, inventory, None, segments, rubric),
                )
    eb.score_run(run_dir, case_dir, config.get("prices"))
    return s.code()


# --- generation -----------------------------------------------------------------------------


def generate(root: Path, run: str, case: str, config: dict, arms=None, *, environ=None, session=None) -> int:
    load_config_dict(config)
    s = session or _Session(root, os.environ if environ is None else environ)
    known = [a["label"] for a in config["arms"]]
    unknown = [a for a in (arms or []) if a not in known]
    if unknown:
        raise BenchError(f"unknown arm(s): {', '.join(unknown)}; known: {', '.join(known)}")
    selected = [a for a in config["arms"] if not arms or a["label"] in arms]
    run_dir, case_dir = eb._run_dir(root, run), eb._case_dir(root, case)
    eb.prepare_run(run_dir, case_dir, {"arms": selected})
    prompt = (case_dir / "prompt.txt").read_text(encoding="utf-8")
    segments = eb.load_segments(case_dir / "source.json")
    labels = {a["label"] for a in selected}
    for attempt in sorted(p for p in (run_dir / "attempts").iterdir() if p.is_dir()):
        meta = eb.read_json(attempt / "attempt.json")
        if meta["kind"] != "new" or meta["label"] not in labels:
            continue
        state = eb.attempt_state(attempt, segments)
        if state["state"] == "pending":
            res = s.ask(f"generate {attempt.name}", meta, prompt)
            if res is None:
                continue
            eb.write_once(attempt / "raw.txt", res["text"].encode("utf-8"))
            eb.write_once(attempt / "usage.json", eb._pretty(_usage_doc(res)))
            execution = {
                "host": res["host"],
                "requested_model": meta["model"],
                "reported_model": res["reported_model"],
                "requested_effort": meta["effort"],
                "cli_version": res["cli"],
                "login": "subscription (no API key in the environment)",
                "started": res["started"],
                "finished": res["finished"],
                "seconds": res["seconds"],
                "argv": res["argv"],
            }
            eb.write_once(attempt / "execution.json", eb._pretty(execution))
            state = eb.attempt_state(attempt, segments)
        # One format repair at most, same model: attempt_cost prices every turn with one model.
        if state["state"] == "failed" and not (attempt / "repair.raw.txt").exists():
            raw = (attempt / "raw.txt").read_text(encoding="utf-8")
            res = s.ask(f"repair {attempt.name}", meta, repair_prompt(raw, state["errors"]))
            if res is not None:
                eb.write_once(attempt / "repair.raw.txt", res["text"].encode("utf-8"))
                eb.write_once(attempt / "repair.usage.json", eb._pretty(_usage_doc(res)))
    return s.code()


def auto_run_id(day: datetime.date) -> str:
    # One run per ISO week: a daily trigger resumes the week's run and costs nothing once done.
    year, week, _ = day.isocalendar()
    return f"auto-{year}-W{week:02d}"


def run(root: Path, run_id: str, case: str, config: dict, arms=None, *, environ=None) -> int:
    s = _Session(root, os.environ if environ is None else environ)
    generate(root, run_id, case, config, arms, session=s)
    grade(root, run_id, case, config, session=s)
    for line in eb.regressions(eb.read_history(root), run_id):
        print("REGRESSION: " + line)
    return s.code()


# --- E3: synthesis claims (B3 sample) judged by the same two judges -------------------------
# The committed claim file (scrubbed windows) is the input; per judge, one committed file of
# verdicts only. Reasons and usage stay private under <root>/claims/. Human labels go into the
# claim file's own "verdict" field, so the human never sees a judge verdict while labelling.

CLAIMS_PROMPT = """TASK: judge sentences from a campaign knowledge base against the transcript passage each one cites.

Each item below has an id, a CLAIM (one sentence written by a summarising system) and a WINDOW
(the transcript lines around the timestamp the claim cites; speakers are shown as "Spieler (<character>)").
Judge each claim against its own window only. Do not use what you may know about this campaign.
You have no tools. Do not call other models or APIs.

Give each claim id one verdict:
- "supported": the window states the claim or clearly implies it.
- "misattributed": the window has the event, but the claim gives it to the wrong person, place or thing.
- "claimed_not_observed": in the window a character only says, believes or retells it, and the claim
  states it as fact.
- "unsupported": the window does not support the claim. It may be true elsewhere; judge the window only.
- "unclear": the window is too fragmentary or garbled to decide.

Reply with one JSON object only, no commentary, no code fence:
{"verdicts": {"c001": {"verdict": "supported", "why": "<at most 12 words>"}}}
Every claim id must appear exactly once."""

PROMPTS["claims"] = CLAIMS_PROMPT


def _claim_rows(path: Path) -> list[dict]:
    import yaml

    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("claims") or []


def _claims_hash(rows: list[dict]) -> str:
    # Over what the judge saw, not the file bytes: filling in human verdicts must not stale it.
    return eb.hash_obj([[r["id"], r["claim"], r["window"]] for r in rows])


def judge_claims(path: Path, config: dict, *, root: Path | None = None, environ=None) -> int:
    from pnp_okf.claims import VERDICTS

    load_config_dict(config)
    s = _Session(root or eb.bench_root(), os.environ if environ is None else environ)
    rows = _claim_rows(path)
    claims_hash = _claims_hash(rows)
    items = "\n\n".join(f"### {r['id']}\nCLAIM: {r['claim']}\nWINDOW:\n{r['window']}" for r in rows)
    prompt = PROMPTS["claims"] + "\n\nCLAIMS\n\n" + items
    private = s.root / "claims"
    for judge in config["judges"]:
        out = path.with_name(f"{path.stem}.{judge['id']}.json")
        header = _header(judge, "claims")
        if out.is_file():
            doc = eb.read_json(out)
            if doc.get("claims_hash") == claims_hash and doc.get("judge") == header:
                continue
        res = s.ask(f"claims {path.stem} {judge['id']}", judge, prompt)
        if res is None:
            continue
        private.mkdir(parents=True, exist_ok=True)
        (private / f"{path.stem}.{judge['id']}.reply.txt").write_text(res["text"], encoding="utf-8")
        eb.write_json(private / f"{path.stem}.{judge['id']}.usage.json", _usage_doc(res))
        try:
            reply = _parse_reply(res["text"]).get("verdicts") or {}
            verdicts = {r["id"]: (reply.get(r["id"]) or {}).get("verdict") for r in rows}
            bad = [cid for cid, v in verdicts.items() if v not in VERDICTS]
            if bad:
                raise BenchError(f"{len(bad)} claim(s) without a valid verdict, e.g. {bad[0]}")
        except (BenchError, ValueError, AttributeError) as exc:
            s.fail(f"claims {path.stem} {judge['id']}: {exc}")
            continue
        doc = {"judge": header, "claims_hash": claims_hash, "verdicts": verdicts}
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return s.code()


def _pct(value) -> str:
    return "n/a" if value is None else f"{100 * value:.1f} %"


def _kappa(value) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _shown(path: Path) -> str:
    # The report is committed to a public repo: never print an absolute local path.
    try:
        return path.resolve().relative_to(Path(__file__).resolve().parent).as_posix()
    except ValueError:
        return path.name


def claims_report(paths: list[Path]) -> str:
    from pnp_okf.claims import VERDICTS, agreement, score

    lines = [
        "# Synthesis faithfulness: claim-level judge results",
        "",
        "Each claim is one sentence of the synthesized knowledge base, judged against the transcript",
        "window (±90 s) around the timestamp it cites. Two judges of different model families label",
        "every claim; a human labels a subset blind (before reading any judge file).",
    ]
    for path in paths:
        rows = _claim_rows(path)
        human = {r["id"]: str(r.get("verdict") or "").strip() for r in rows if str(r.get("verdict") or "").strip()}
        judges = {}
        for judge_file in sorted(path.parent.glob(f"{path.stem}.*.json")):
            judge_id = judge_file.name[len(path.stem) + 1 : -len(".json")]
            if _ID.fullmatch(judge_id):
                doc = eb.read_json(judge_file)
                if doc.get("claims_hash") == _claims_hash(rows):
                    judges[judge_id] = doc["verdicts"]
        lines += ["", f"## {path.name} ({len(rows)} claims, {len(human)} labelled by a human)", ""]
        lines += ["| Labeller | n (without unclear) | Supported rate |", "|---|---|---|"]
        for name, verdicts in [*judges.items(), *([("human", human)] if human else [])]:
            result = score([{**r, "verdict": verdicts.get(r["id"], "")} for r in rows])
            lines.append(f"| {name} | {result['n']} | {_pct(result['supported_rate'])} |")
        lines += ["", "| Pair | n | Agreement | Cohen's kappa |", "|---|---|---|---|"]
        names = list(judges)
        pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]] + [(a, "human") for a in names]
        labelled = {**judges, "human": human}
        for a, b in pairs:
            result = agreement(labelled[a], labelled[b])
            lines.append(f"| {a} vs {b} | {result['n']} | {_pct(result['rate'])} | {_kappa(result['kappa'])} |")
        if human:
            margin = 196 * (0.25 / len(human)) ** 0.5
            lines.append("")
            lines.append(f"Judge vs human rests on {len(human)} labels: worst-case 95 % margin ±{margin:.0f} pp.")
        lines += [
            "",
            f"Reproduce: `bench_launch.py judge-claims --claims {_shown(path)}` (judges; files are reused while "
            f"claims are unchanged), then `bench_launch.py claims-report --claims {_shown(path)}`.",
        ]
    lines += ["", "## Verdicts", ""] + [f"- `{v}`" for v in VERDICTS]
    lines += [
        "",
        "## Limits",
        "",
        "- The window is ±90 s around one cited timestamp. A synthesized sentence can draw on several",
        "  sessions, so `unsupported` means 'not supported in the cited window', not 'false'.",
        "- One sample of the bundle at one point in time; claims within one concept are correlated.",
        "- Kappa is shown because `supported` dominates and inflates raw agreement.",
    ]
    return "\n".join(lines) + "\n"


# --- CLI ------------------------------------------------------------------------------------


def _cmd_grade(args) -> int:
    packets = tuple(p.strip() for p in args.packets.split(","))
    if not set(packets) <= {"A", "B"}:
        raise BenchError("--packets takes A, B or A,B")
    return grade(args.root or eb.bench_root(), args.run, args.case, load_config(args.config), packets)


def _arms(args):
    return [a.strip() for a in args.arms.split(",")] if args.arms else None


def _cmd_generate(args) -> int:
    return generate(args.root or eb.bench_root(), args.run, args.case, load_config(args.config), _arms(args))


def _cmd_run(args) -> int:
    run_id = args.run or auto_run_id(datetime.date.today())
    print(f"run {run_id}")
    return run(args.root or eb.bench_root(), run_id, args.case, load_config(args.config), _arms(args))


def _cmd_judge_claims(args) -> int:
    return judge_claims(args.claims, load_config(args.config), root=args.root)


def _cmd_claims_report(args) -> int:
    text = claims_report(args.claims)
    if args.out is None:
        sys.stdout.buffer.write(text.encode("utf-8"))
    else:
        args.out.write_text(text, encoding="utf-8")
        print(args.out)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench_launch", description="Launch benchmark tasks on Claude Code / Codex subscriptions."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=None, help="benchmark root (default: PNP_BENCH_DIR or .cache)")
    common.add_argument("--case", default=eb.DEFAULT_CASE)
    common.add_argument("--config", type=Path, default=Path(__file__).resolve().parent / "bench_config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "grade", parents=[common], help="inventory + judge packets for every output of a run, then score"
    )
    p.add_argument("--run", required=True)
    p.add_argument("--packets", default="A,B", help="A (no gold needed), B, or A,B")
    p.set_defaults(func=_cmd_grade)

    p = sub.add_parser("generate", parents=[common], help="generate pending attempts of the configured arms")
    p.add_argument("--run", required=True)
    p.add_argument("--arms", default=None, help="comma-separated arm labels (default: all)")
    p.set_defaults(func=_cmd_generate)

    p = sub.add_parser("run", parents=[common], help="generate, then grade; the scheduled entry point")
    p.add_argument("--run", default=None, help="default: auto-<ISO year>-W<week>")
    p.add_argument("--arms", default=None, help="comma-separated arm labels (default: all)")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("judge-claims", parents=[common], help="both judges label a B3 claim file (E3)")
    p.add_argument("--claims", type=Path, required=True, help="claim YAML from claim_sampler.py")
    p.set_defaults(func=_cmd_judge_claims)

    p = sub.add_parser("claims-report", parents=[common], help="supported rates and agreement for claim files")
    p.add_argument("--claims", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(func=_cmd_claims_report)
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
