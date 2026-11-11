"""pnp agent status (D1 phase 4): validate the agent queue without spending anything."""

from __future__ import annotations

import json
from pathlib import Path

import pnp_okf.cli as cli
import pytest

LABEL = "agent:claude:claude-opus-5-5"
MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
PID = "ab" * 8
EXTRACTION = {
    "recap": "Eine Sitzung.",
    "entities": [
        {"name": "Lindo Laut", "type": "Character", "note": "Ein Barde.",
         "citation_ts": "00:12:34", "subtype": ""}
    ],
}
JSON_STEPS = ("extract", "state", "dedup")
MD_STEPS = ("deep", "standard")


@pytest.fixture(autouse=True)
def _queue(tmp_path, monkeypatch):
    monkeypatch.setenv("PNP_AGENT_DIR", str(tmp_path / "agent"))
    # No key: status must not need one. Deleting it proves the command never reads it.
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    return tmp_path / "agent"


def _request(queue: Path, step: str, *, kind: str = "json", pid: str = PID,
             model: str = LABEL) -> Path:
    base = queue / step
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{pid}.request.json"
    path.write_text(json.dumps({
        "id": pid, "step": step, "model": model,
        "response_kind": "json" if kind == "json" else "markdown",
        "temperature": 0.2, "messages": MESSAGES, "created": "2026-11-12T00:00:00Z",
    }), encoding="utf-8")
    return path


def _respond(queue: Path, step: str, text: str, *, kind: str = "json", pid: str = PID) -> Path:
    path = queue / step / f"{pid}.response.{'json' if kind == 'json' else 'md'}"
    path.write_text(text, encoding="utf-8")
    return path


def _run(capsys, *args: str) -> tuple[int, dict]:
    rc = cli.main(["agent", "status", "--json", *args])
    return rc, json.loads(capsys.readouterr().out)


def _only(report: dict) -> dict:
    assert len(report["packets"]) == 1
    return report["packets"][0]


# --- per-step contracts -----------------------------------------------------

VALID = {
    "extract": (json.dumps(EXTRACTION), "json"),
    "state": ("{}", "json"),
    "dedup": ('{"groups": []}', "json"),
    "deep": ("## Szene\n\nEin Absatz.", "md"),
    "standard": ("Ein Absatz.", "md"),
}
INVALID = {
    "extract": ("not json", "json"),
    "state": ('{"threads": "nope"}', "json"),
    "dedup": ("[]", "json"),
    "deep": ("   \n", "md"),
    "standard": ("", "md"),
}


@pytest.mark.parametrize("step", JSON_STEPS + MD_STEPS)
def test_a_request_without_a_response_is_pending(capsys, _queue, step):
    kind = "json" if step in JSON_STEPS else "md"
    req = _request(_queue, step, kind=kind)
    rc, report = _run(capsys)
    packet = _only(report)
    assert rc == 0
    assert packet["status"] == "pending"
    assert packet["response"] is None
    assert packet["request"] == str(req)
    assert report["counts"] == {"pending": 1, "answered": 0, "rejected": 0, "unreadable": 0}


@pytest.mark.parametrize("step", JSON_STEPS + MD_STEPS)
def test_a_valid_response_is_answered(capsys, _queue, step):
    text, kind = VALID[step]
    _request(_queue, step, kind=kind)
    resp = _respond(_queue, step, text, kind=kind)
    rc, report = _run(capsys)
    packet = _only(report)
    assert rc == 0
    assert packet["status"] == "answered"
    assert packet["response"] == str(resp)
    assert "error" not in packet
    assert resp.exists()


@pytest.mark.parametrize("step", JSON_STEPS + MD_STEPS)
def test_an_invalid_response_is_rejected_and_requeued(capsys, _queue, step):
    text, kind = INVALID[step]
    _request(_queue, step, kind=kind)
    _respond(_queue, step, text, kind=kind)
    rc, report = _run(capsys)
    packet = _only(report)
    assert rc == 1
    assert packet["status"] == "rejected"
    assert packet["error"]
    rejected = _queue / step / "rejected"
    assert (rejected / f"{PID}.response.{'json' if kind == 'json' else 'md'}").read_text(
        encoding="utf-8") == text
    assert (rejected / f"{PID}.error.txt").read_text(encoding="utf-8").strip() == packet["error"].strip()
    # Moved aside: the packet is open again for the worker.
    assert not (_queue / step / f"{PID}.response.{'json' if kind == 'json' else 'md'}").exists()
    assert report["counts"] == {"pending": 0, "answered": 0, "rejected": 1, "unreadable": 0}


# --- extraction specifics ---------------------------------------------------


def test_a_fenced_json_extraction_is_accepted(capsys, _queue):
    _request(_queue, "extract")
    _respond(_queue, "extract", f"Hier:\n```json\n{json.dumps(EXTRACTION)}\n```\n")
    rc, report = _run(capsys)
    assert rc == 0
    assert _only(report)["status"] == "answered"


def test_a_recap_with_zero_entities_is_rejected(capsys, _queue):
    _request(_queue, "extract")
    _respond(_queue, "extract", json.dumps({"recap": "Viel Text.", "entities": []}))
    rc, report = _run(capsys)
    packet = _only(report)
    assert rc == 1
    assert packet["status"] == "rejected"
    assert "zero entities" in packet["error"]


def test_an_empty_recap_with_zero_entities_is_answered(capsys, _queue):
    _request(_queue, "extract")
    _respond(_queue, "extract", json.dumps({"recap": "", "entities": []}))
    rc, report = _run(capsys)
    assert rc == 0
    assert _only(report)["status"] == "answered"


def test_state_is_parsed_raw_like_its_code_path_so_a_fence_is_rejected(capsys, _queue):
    # The real state path does not strip fences, so a fenced answer would fail
    # the run; status must reject it now, not let it pass here.
    _request(_queue, "state")
    _respond(_queue, "state", "```json\n{}\n```")
    rc, report = _run(capsys)
    assert rc == 1
    assert _only(report)["status"] == "rejected"


# --- meta -------------------------------------------------------------------


def test_a_meta_model_mismatch_warns_but_does_not_reject(capsys, _queue):
    _request(_queue, "deep", kind="md")
    _respond(_queue, "deep", "Ein Absatz.", kind="md")
    (_queue / "deep" / f"{PID}.meta.json").write_text(
        json.dumps({"host": "codex", "model": "gpt-6.1-terra"}), encoding="utf-8")
    rc, report = _run(capsys)
    packet = _only(report)
    assert rc == 0
    assert packet["status"] == "answered"
    assert "gpt-6.1-terra" in packet["warning"]


def test_a_matching_meta_model_is_silent(capsys, _queue):
    _request(_queue, "deep", kind="md")
    (_queue / "deep" / f"{PID}.meta.json").write_text(
        json.dumps({"host": "claude", "model": "claude-opus-5-5"}), encoding="utf-8")
    _, report = _run(capsys)
    assert "warning" not in _only(report)


def test_the_human_output_shows_the_meta_warning(capsys, _queue):
    _request(_queue, "deep", kind="md")
    (_queue / "deep" / f"{PID}.meta.json").write_text(
        json.dumps({"host": "codex", "model": "gpt-6.1-terra"}), encoding="utf-8")
    assert cli.main(["agent", "status"]) == 0
    assert "gpt-6.1-terra" in capsys.readouterr().out


# --- output, exit codes, grouping -------------------------------------------


def test_json_shape(capsys, _queue):
    _request(_queue, "extract")
    _respond(_queue, "extract", "not json")
    _request(_queue, "standard", kind="md", pid="cd" * 8)
    rc, report = _run(capsys)
    assert rc == 1
    assert set(report) == {"dir", "packets", "counts"}
    assert report["dir"] == str(_queue)
    assert {p["step"] for p in report["packets"]} == {"extract", "standard"}
    for packet in report["packets"]:
        assert {"id", "step", "model", "status", "request", "response"} <= set(packet)
    assert report["counts"] == {"pending": 1, "answered": 0, "rejected": 1, "unreadable": 0}


def test_packets_are_grouped_by_step_and_model_in_text(capsys, _queue):
    _request(_queue, "extract")
    _request(_queue, "dedup", pid="cd" * 8, model="agent:codex:gpt-6.1-terra")
    assert cli.main(["agent", "status"]) == 0
    out = capsys.readouterr().out
    assert "extract" in out and LABEL in out
    assert "dedup" in out and "agent:codex:gpt-6.1-terra" in out


def test_an_empty_queue_is_fine_and_needs_no_api_key(capsys, _queue):
    rc, report = _run(capsys)
    assert rc == 0
    assert report["packets"] == []
    assert report["counts"] == {"pending": 0, "answered": 0, "rejected": 0, "unreadable": 0}


def test_a_rejected_then_fixed_packet_is_answered_on_the_next_call(capsys, _queue):
    _request(_queue, "dedup")
    _respond(_queue, "dedup", "[]")
    assert _run(capsys)[0] == 1
    _respond(_queue, "dedup", '{"groups": []}')
    rc, report = _run(capsys)
    assert rc == 0
    assert _only(report)["status"] == "answered"
