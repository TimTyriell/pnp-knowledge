"""Tests for the subscription launcher (docs/plans/E2-subscription-launcher.md).

No model is ever started: `bench_launch._spawn` is replaced by a fake host that answers
from the invented data in test_extraction_benchmark. The fake's reply envelopes copy the
shape of real Claude Code / Codex outputs recorded on 2026-11-15, text removed.
"""

from __future__ import annotations

import ast
import datetime
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared invented data lives in the E1 tests

import bench_launch as bl  # noqa: E402
import extraction_benchmark as eb  # noqa: E402
from test_extraction_benchmark import (  # noqa: E402
    ARM,
    SESSION,
    make_extraction,
    make_gold,
    make_judgment_b,
    prepared_case,
    prepared_outputs,
)

MODULE_PATH = Path(__file__).resolve().parents[1] / "bench_launch.py"

CONFIG = {
    "judges": [
        {"id": "opus", "host": "claude-code", "model": "claude-opus-5-5", "effort": "high"},
        {"id": "sol", "host": "codex", "model": "gpt-6.1-sol", "effort": "high"},
    ],
    "inventory": {"host": "claude-code", "model": "claude-opus-5-5", "effort": "high"},
    "arms": [
        {"label": "arm-claude", "host": "claude-code", "model": "claude-sonnet-5-5", "effort": "medium", "repeats": 1},
        {"label": "arm-codex", "host": "codex", "model": "gpt-6.1-terra", "effort": "high", "repeats": 1},
    ],
    "prices": {"rows": []},
}

CLAUDE_QUOTA = {
    "type": "result",
    "subtype": "success",
    "is_error": True,
    "api_error_status": 429,
    "api_error": "usage_limit_reached",
    "result": "You've hit your 5-hour limit - resets 12:50am (Europe/Berlin)",
    "modelUsage": {},
    "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0},
}
CODEX_QUOTA = {
    "type": "turn.failed",
    "error": {"message": "You've hit your usage limit. Try again at Nov 16th, 2026 12:52 AM."},
}


# --- fake host -----------------------------------------------------------------------------


def _section(prompt: str, title: str) -> str:
    start = prompt.index("\n" + title) + len(title) + 1
    rest = prompt[start:]
    nxt = re.search(r"\n\n[A-Z][A-Z ]+(?:\(|\n)", rest)
    return rest[: nxt.start()] if nxt else rest


def answer(prompt: str) -> str:
    """What a perfect worker replies to each kind of task."""
    if "SENTENCES\n" in prompt:
        ids = re.findall(r"^(r\d+|e\d+\.\d+)(?: \[[^\]]*\])?: ", prompt, flags=re.M)
        return json.dumps({"sentences": {sid: {"kind": "claim", "group": f"g{n}"} for n, sid in enumerate(ids)}})
    if "\nCLAIMS (loc:" in prompt:
        claims = json.loads(_section(prompt, "CLAIMS (loc: recap, or entity:<record index>)").strip())
        records = json.loads(_section(prompt, "EXTRACTION RECORDS").strip())
        why = {"verdict": "supported", "segments": ["S000"], "why": "invented"}
        return json.dumps(
            {"claims": {c["id"]: why for c in claims}, "locators": {str(r["index"]): why for r in records}}
        )
    if "\nGOLD REFERENCE\n" in prompt:
        b = make_judgment_b(make_gold(), make_extraction())
        return json.dumps({k: b[k] for k in ("facts", "notes", "entities", "critical")})
    if "\n### c" in prompt:
        return json.dumps(
            {
                "verdicts": {
                    cid: {"verdict": "supported", "why": "x"} for cid in re.findall(r"^### (c\d+)", prompt, flags=re.M)
                }
            }
        )
    return json.dumps(make_extraction(), ensure_ascii=False)


class FakeHosts:
    def __init__(self, quota: set[str] | None = None, reply=answer):
        self.calls: list[dict] = []
        self.quota = quota or set()
        self.reply = reply

    def __call__(self, argv, stdin_text, cwd, env, timeout):
        if argv[-1] == "--version":
            return 0, f"{argv[0]} 9.9.9", ""
        host = "codex" if argv[1] == "exec" else "claude-code"
        self.calls.append({"host": host, "argv": argv, "prompt": stdin_text, "env": env})
        if host == "claude-code":
            if host in self.quota:
                return 0, json.dumps(CLAUDE_QUOTA), ""
            model = argv[argv.index("--model") + 1]
            usage = {
                "input_tokens": 10,
                "cache_creation_input_tokens": 5,
                "cache_read_input_tokens": 0,
                "output_tokens": 7,
            }
            doc = {
                "type": "result",
                "is_error": False,
                "result": self.reply(stdin_text),
                "usage": usage,
                "modelUsage": {model: {"inputTokens": 10, "outputTokens": 7}},
            }
            return 0, json.dumps(doc), ""
        if host in self.quota:
            return 1, json.dumps(CODEX_QUOTA) + "\n", ""
        Path(argv[argv.index("-o") + 1]).write_text(self.reply(stdin_text), encoding="utf-8")
        events = [
            {"type": "thread.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "..."}},
            {"type": "turn.completed", "usage": {"input_tokens": 20, "cached_input_tokens": 4, "output_tokens": 9}},
        ]
        return 0, "\n".join(json.dumps(e) for e in events) + "\n", ""


@pytest.fixture
def hosts(monkeypatch):
    fake = FakeHosts()
    monkeypatch.setattr(bl, "_spawn", fake)
    monkeypatch.setattr(bl, "_exe", lambda name: name)
    return fake


def _grade(out: dict, **kw) -> int:
    return bl.grade(out["run_dir"].parent.parent, out["run_dir"].name, SESSION, CONFIG, environ={}, **kw)


# --- argv, environment, parsing --------------------------------------------------------------


def test_claude_argv_carries_the_probed_flags():
    argv = bl.argv_for("claude-code", "claude-opus-5-5", "high", None)
    joined = " | ".join(argv)
    assert "--model | claude-opus-5-5" in joined and "--effort | high" in joined
    assert "--tools |  |" in joined and "--setting-sources |  |" in joined
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in argv
    assert argv[-2:] == ["--output-format", "json"]


def test_codex_argv_carries_the_probed_flags(tmp_path):
    out = tmp_path / "last.txt"
    argv = bl.argv_for("codex", "gpt-6.1-sol", "high", out)
    assert argv[1:4] == ["exec", "-m", "gpt-6.1-sol"]
    assert "model_reasoning_effort=high" in argv
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--json"):
        assert flag in argv
    assert argv[argv.index("-s") + 1] == "read-only" and argv[argv.index("-o") + 1] == str(out)
    assert argv[-1] == "-"


@pytest.mark.parametrize("env", [{"ANTHROPIC_API_KEY": "x"}, {"OPENAI_API_KEY": "x"}, {"DEEPSEEK_API_KEY": "x"}])
def test_an_api_key_in_the_environment_aborts(env):
    with pytest.raises(eb.BenchError, match="API key"):
        bl.check_env(env)


@pytest.mark.parametrize("env", [{"CLAUDECODE": "1"}, {"CODEX_THREAD_ID": "x"}])
def test_an_agent_session_aborts(env):
    with pytest.raises(eb.BenchError, match="agent session"):
        bl.check_env(env)


def test_child_env_drops_parent_claude_session_variables():
    env = bl.child_env({"PATH": "p", "CLAUDE_CODE_ENTRYPOINT": "x", "CLAUDECODE": "1", "CLAUDE_CONFIG_DIR": "c"})
    assert env == {"PATH": "p", "CLAUDE_CONFIG_DIR": "c"}


def test_claude_usage_limit_is_a_quota_stop():
    result = bl.parse_claude(json.dumps(CLAUDE_QUOTA), "claude-opus-5-5")
    assert not result["ok"] and result["quota"] and "5-hour limit" in result["error"]


def test_claude_silent_model_fallback_is_rejected():
    doc = {"is_error": False, "result": "{}", "usage": {}, "modelUsage": {"claude-sonnet-5-5": {}}}
    result = bl.parse_claude(json.dumps(doc), "claude-opus-5-5")
    assert not result["ok"] and not result["quota"] and "fallback" in result["error"]


def test_codex_usage_limit_is_a_quota_stop():
    result = bl.parse_codex(json.dumps(CODEX_QUOTA) + "\n", "")
    assert not result["ok"] and result["quota"] and "usage limit" in result["error"]


@pytest.mark.parametrize("item", ["command_execution", "file_change", "mcp_tool_call", "web_search"])
def test_codex_tool_use_breaks_blinding_and_is_rejected(item):
    events = [{"type": "item.completed", "item": {"type": item}}, {"type": "turn.completed", "usage": {}}]
    result = bl.parse_codex("\n".join(json.dumps(e) for e in events), "{}")
    assert not result["ok"] and "tool use" in result["error"]


def test_codex_answer_and_usage_are_read():
    events = [{"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}}]
    result = bl.parse_codex(json.dumps(events[0]), '{"a": 1}')
    assert result["ok"] and result["text"] == '{"a": 1}' and result["usage"]["input_tokens"] == 3


# --- grading -------------------------------------------------------------------------------


def test_grade_writes_inventory_both_packets_report_and_history(tmp_path, hosts):
    out = prepared_outputs(tmp_path)
    assert _grade(out) == 0
    g = out["grading"]
    for name in (
        "inventory.json",
        "A.opus.json",
        "A.sol.json",
        "B.opus.json",
        "B.sol.json",
        "usage.inventory.json",
        "usage.A.sol.json",
        "usage.B.opus.json",
    ):
        assert (g / name).is_file(), name
    a = eb.read_json(g / "A.sol.json")
    assert a["binds"] == eb.expected_binds("A", g, out["case_dir"])
    assert a["judge"] == {
        "host": "codex",
        "model": "gpt-6.1-sol",
        "effort": "high",
        "prompt_sha256": bl.prompt_sha("judge_a"),
    }
    assert eb.read_json(g / "usage.A.sol.json")["style"] == "openai"
    assert eb.read_json(g / "usage.B.opus.json")["style"] == "anthropic"
    (attempt,) = eb.read_json(out["run_dir"] / "report.json")["attempts"]
    assert attempt["scores"]["F"]["value"] == 100.0
    assert (out["run_dir"].parent.parent / "history.jsonl").is_file()
    assert (out["run_dir"].parent.parent / "launch.log.jsonl").is_file()


def test_a_second_grade_launches_nothing(tmp_path, hosts):
    out = prepared_outputs(tmp_path)
    _grade(out)
    before = len(hosts.calls)
    assert _grade(out) == 0
    assert len(hosts.calls) == before


def test_packets_a_only_needs_no_gold_call(tmp_path, hosts):
    out = prepared_outputs(tmp_path)
    assert _grade(out, packets=("A",)) == 0
    assert not list(out["grading"].glob("B.*.json"))
    assert not any("GOLD REFERENCE" in c["prompt"] for c in hosts.calls)


def test_quota_on_one_host_lets_the_other_host_continue(tmp_path, monkeypatch):
    fake = FakeHosts(quota={"claude-code"})
    monkeypatch.setattr(bl, "_spawn", fake)
    monkeypatch.setattr(bl, "_exe", lambda name: name)
    out = prepared_outputs(tmp_path)
    assert _grade(out) == bl.QUOTA
    assert (out["grading"] / "B.sol.json").is_file()
    assert not (out["grading"] / "B.opus.json").exists()
    # Claude is asked once, then skipped for the rest of the run.
    assert sum(c["host"] == "claude-code" for c in fake.calls) == 1


def test_a_stale_judgment_is_moved_aside_and_redone(tmp_path, hosts):
    out = prepared_outputs(tmp_path)
    _grade(out)
    path = out["grading"] / "B.opus.json"
    doc = eb.read_json(path)
    doc["binds"]["gold_sha256"] = "0" * 64
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert _grade(out) == 0
    assert (out["grading"] / "B.opus.stale1.json").is_file()
    assert (out["grading"] / "usage.B.opus.stale1.json").is_file()
    assert eb.read_json(path)["binds"] == eb.expected_binds("B", out["grading"], out["case_dir"])


def test_judge_prompts_never_name_the_generating_configuration(tmp_path, hosts):
    out = prepared_outputs(tmp_path)
    _grade(out)
    assert hosts.calls
    for call in hosts.calls:
        for secret in (ARM["label"], ARM["model"], ARM["effort"], ARM["host"]):
            assert secret not in call["prompt"]


def test_an_invalid_judgment_is_kept_private_and_not_written(tmp_path, monkeypatch):
    def broken(prompt):
        if "\nGOLD REFERENCE\n" in prompt:
            b = make_judgment_b(make_gold(), make_extraction())
            b["entities"]["0"].pop("type_ok")
            return json.dumps({k: b[k] for k in ("facts", "notes", "entities", "critical")})
        return answer(prompt)

    monkeypatch.setattr(bl, "_spawn", FakeHosts(reply=broken))
    monkeypatch.setattr(bl, "_exe", lambda name: name)
    out = prepared_outputs(tmp_path)
    assert _grade(out) == 1
    assert not list(out["grading"].glob("B.*.json"))
    assert list((out["run_dir"] / "private" / "raw").glob("*.B.opus.txt"))


# --- generation and run --------------------------------------------------------------------


def _new_run(tmp_path) -> dict:
    paths = prepared_case(tmp_path)
    return {**paths, "root": tmp_path / "bench"}


def test_generate_writes_raw_usage_and_execution(tmp_path, hosts):
    case = _new_run(tmp_path)
    assert bl.generate(case["root"], "g1", SESSION, CONFIG, environ={}) == 0
    attempts = sorted((case["root"] / "runs" / "g1" / "attempts").iterdir())
    assert len(attempts) == 2
    for attempt in attempts:
        execution = eb.read_json(attempt / "execution.json")
        meta = eb.read_json(attempt / "attempt.json")
        assert (attempt / "raw.txt").is_file()
        assert execution["requested_model"] == meta["model"] and execution["login"].startswith("subscription")
        assert eb.read_json(attempt / "usage.json")["model"] == meta["model"]
    assert hosts.calls[0]["prompt"] == (case["case_dir"] / "prompt.txt").read_text(encoding="utf-8")


def test_an_invalid_output_gets_exactly_one_repair(tmp_path, monkeypatch):
    fake = FakeHosts(reply=lambda prompt: "not json")
    monkeypatch.setattr(bl, "_spawn", fake)
    monkeypatch.setattr(bl, "_exe", lambda name: name)
    case = _new_run(tmp_path)
    bl.generate(case["root"], "g1", SESSION, CONFIG, arms=["arm-claude"], environ={})
    assert len(fake.calls) == 2 and "VALIDATOR ERROR" in fake.calls[1]["prompt"]
    bl.generate(case["root"], "g1", SESSION, CONFIG, arms=["arm-claude"], environ={})
    assert len(fake.calls) == 2


def test_arms_filter_and_unknown_arm(tmp_path, hosts):
    case = _new_run(tmp_path)
    bl.generate(case["root"], "g1", SESSION, CONFIG, arms=["arm-codex"], environ={})
    assert {c["host"] for c in hosts.calls} == {"codex"}
    with pytest.raises(eb.BenchError, match="unknown arm"):
        bl.generate(case["root"], "g1", SESSION, CONFIG, arms=["nope"], environ={})


def test_run_generates_then_grades(tmp_path, hosts):
    case = _new_run(tmp_path)
    assert bl.run(case["root"], "w1", SESSION, CONFIG, arms=["arm-claude"], environ={}) == 0
    rows = eb.read_history(case["root"])
    assert [r["label"] for r in rows] == ["arm-claude"] and rows[0]["F"] == [100.0, 100.0]


def test_auto_run_id_is_the_iso_week():
    assert bl.auto_run_id(datetime.date(2026, 11, 18)) == "auto-2026-W47"
    assert bl.auto_run_id(datetime.date(2027, 1, 1)) == "auto-2026-W53"


def test_launcher_imports_no_provider_sdk():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not names & {"openai", "anthropic", "httpx", "requests", "urllib", "socket"}


def test_config_ids_are_checked():
    bad = {**CONFIG, "judges": [{**CONFIG["judges"][0], "id": "Opus-1"}]}
    with pytest.raises(eb.BenchError, match="judge id"):
        bl.load_config_dict(bad)
    with pytest.raises(eb.BenchError, match="host"):
        bl.load_config_dict({**CONFIG, "inventory": {**CONFIG["inventory"], "host": "api"}})


def test_committed_config_is_valid():
    bl.load_config(MODULE_PATH.parent / "bench_config.json")


# --- E3: synthesis claims judged by the same two judges --------------------------------------


def _claims_file(tmp_path: Path) -> Path:
    import yaml

    rows = [
        {"id": f"c00{i}", "concept": "npcs/alrik", "type": "NPC", "tier": "brief",
         "claim": f"Alrik tut Ding Nummer {i} in der Mühle.", "session": "s", "at": "00:00:01",
         "window": "[00:00:01] Spieler (SL): Alrik tut Dinge.", "verdict": "", "note": ""}
        for i in range(1, 4)
    ]  # fmt: skip
    path = tmp_path / "claims" / "2026-01-01-7.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump({"seed": 7, "claims": rows}, allow_unicode=True), encoding="utf-8")
    return path


def test_judge_claims_writes_one_verdict_file_per_judge(tmp_path, hosts):
    path = _claims_file(tmp_path)
    assert bl.judge_claims(path, CONFIG, root=tmp_path / "bench", environ={}) == 0
    assert len(hosts.calls) == 2
    for judge in ("opus", "sol"):
        doc = eb.read_json(path.with_name(f"{path.stem}.{judge}.json"))
        assert doc["verdicts"] == {"c001": "supported", "c002": "supported", "c003": "supported"}
        assert doc["judge"]["prompt_sha256"] == bl.prompt_sha("claims")
        assert "why" not in json.dumps(doc)  # reasons stay private


def test_human_labels_do_not_make_the_judge_files_stale(tmp_path, hosts):
    import yaml

    path = _claims_file(tmp_path)
    bl.judge_claims(path, CONFIG, root=tmp_path / "bench", environ={})
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["claims"][0]["verdict"] = "unsupported"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    bl.judge_claims(path, CONFIG, root=tmp_path / "bench", environ={})
    assert len(hosts.calls) == 2


def test_judge_claims_refuses_a_reply_with_unknown_or_missing_verdicts(tmp_path, monkeypatch):
    fake = FakeHosts(reply=lambda prompt: json.dumps({"verdicts": {"c001": {"verdict": "true"}}}))
    monkeypatch.setattr(bl, "_spawn", fake)
    monkeypatch.setattr(bl, "_exe", lambda name: name)
    path = _claims_file(tmp_path)
    assert bl.judge_claims(path, CONFIG, root=tmp_path / "bench", environ={}) == 1
    assert not list(path.parent.glob("*.json"))


def test_claims_report_states_rates_agreement_and_sample_size(tmp_path, hosts):
    import yaml

    path = _claims_file(tmp_path)
    bl.judge_claims(path, CONFIG, root=tmp_path / "bench", environ={})
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["claims"][0]["verdict"] = "supported"
    data["claims"][1]["verdict"] = "unsupported"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    text = bl.claims_report([path])
    assert "| opus | 3 | 100.0 % |" in text  # judge supported rate over all 3 claims
    assert "opus vs human | 2 | 50.0 %" in text  # one of two human labels agrees
    assert "opus vs sol | 3 | 100.0 %" in text
    assert "claims_report" not in text and "bench_launch.py claims-report" in text
