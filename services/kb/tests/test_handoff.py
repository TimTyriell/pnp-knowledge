"""Agent mode (D1 phase 1): per-step model labels, the handoff client, exit 4."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pnp_okf.cli as cli
import pnp_okf.dedup as dedup_mod
import pnp_okf.extract as extract_mod
import pytest
from pnp_okf.config import ConfigError, DeepSeekConfig, is_agent
from pnp_okf.extract import _cache_key, extract_session
from pnp_okf.handoff import (
    AGENT_CALLS,
    AgentPending,
    AgentResponseInvalid,
    AgentWorkPending,
    HandoffClient,
    agent_dir,
    packet_id,
)
from pnp_okf.llm_client import CountingClient, build_client
from pnp_okf.models import CanonicalEntity, EntityType, MentionRef, Segment, SessionTranscript
from pnp_okf.state import run_state, write_glossary
from pnp_okf.synthesize import synthesize_entity_body

LABEL = "agent:claude:claude-opus-5-5"
STEPS = ("extract", "deep", "standard", "state", "dedup")
ALL_AGENT = [arg for s in STEPS for arg in ("--model", f"{s}={LABEL}")]
MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
EXTRACTION = {
    "recap": "Eine Sitzung.",
    "entities": [
        {"name": "Lindo Laut", "type": "Character", "note": "Ein Barde.",
         "citation_ts": "00:12:34", "subtype": ""}
    ],
}
GLOSS = [{"type": "NPC", "name": "Xenia", "aliases": []}]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    # setenv-then-delenv records the original value, so every var a test (or
    # main()) sets is restored on teardown, including the PNP_MODEL_* ones.
    for var in [f"PNP_MODEL_{s.upper()}" for s in STEPS] + [
        "DEEPSEEK_MODEL", "DEEPSEEK_LIGHT_MODEL", "DEEPSEEK_EXTRACT_MODEL",
        "DEEPSEEK_STATE_MODEL", "PNP_STRICT_MODEL", "PNP_AGENT_DIR",
    ]:
        monkeypatch.setenv(var, "placeholder")
        monkeypatch.delenv(var)
    monkeypatch.setenv("PNP_AGENT_DIR", str(tmp_path / "agent"))
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    AGENT_CALLS.clear()
    extract_mod._NO_STRUCTURED_OUTPUTS.clear()
    extract_mod._PROBED.clear()
    yield
    AGENT_CALLS.clear()
    extract_mod._NO_STRUCTURED_OUTPUTS.clear()
    extract_mod._PROBED.clear()


def _cfg(step: str = "extract") -> DeepSeekConfig:
    return DeepSeekConfig(api_key="", model=LABEL, base_url="https://example.invalid", step=step)


def _answer(packet: AgentPending, text: str, kind: str = "json") -> None:
    """Play the worker: write the response next to the request it answers."""
    packet.path.with_name(f"{packet.packet_id}.response.{kind}").write_text(text, encoding="utf-8")


def _transcript() -> SessionTranscript:
    segs = [Segment(start=i, end=i + 1, speaker="GM", text=f"Satz {i}") for i in range(3)]
    return SessionTranscript(session_id="2026-01-01_a", date="2026-01-01",
                             url="https://example.invalid/a", segments=segs)


def _transcripts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "transcripts"
    d.mkdir()
    (d / "2026-01-01_a.json").write_text(json.dumps({
        "video_date": "2026-01-01", "video_url": "https://youtu.be/x",
        "segments": [{"start": 1.0, "end": 2.0, "speaker": "GM", "text": "Hallo Welt"}],
    }), encoding="utf-8")
    return d


# --- config -----------------------------------------------------------------


def test_per_step_env_vars_take_precedence_over_the_old_ones(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "old-deep")
    monkeypatch.setenv("PNP_MODEL_DEEP", "new-deep")
    monkeypatch.setenv("DEEPSEEK_EXTRACT_MODEL", "old-extract")
    monkeypatch.setenv("PNP_MODEL_STANDARD", LABEL)
    monkeypatch.setenv("PNP_MODEL_DEDUP", "dedup-model")
    assert DeepSeekConfig.from_env().step_models() == {
        "extract": "old-extract",
        "deep": "new-deep",
        "standard": LABEL,
        "state": "new-deep",
        "dedup": "dedup-model",
    }


def test_api_key_is_required_only_when_some_step_uses_the_api(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    for s in STEPS:
        monkeypatch.setenv(f"PNP_MODEL_{s.upper()}", LABEL)
    assert DeepSeekConfig.from_env().api_key == ""
    monkeypatch.setenv("PNP_MODEL_DEDUP", "deepseek-v4-flash")
    with pytest.raises(ConfigError):
        DeepSeekConfig.from_env()


def test_for_tier_sets_the_step_and_dedup_uses_its_own_model(monkeypatch):
    monkeypatch.setenv("PNP_MODEL_DEDUP", LABEL)
    cfg = DeepSeekConfig.from_env()
    assert cfg.for_tier("dedup").model == LABEL
    assert cfg.for_tier("dedup").step == "dedup"
    assert cfg.for_tier("deep").step == "deep"
    assert cfg.for_tier("standard").step == "standard"
    assert cfg.for_tier("standard").model == "deepseek-v4-flash"


@pytest.mark.parametrize("model, expected", [
    ("agent:claude:claude-opus-5-5", True),
    ("agent:codex:gpt-6.1-terra", True),
    ("deepseek-v4-pro", False),
])
def test_is_agent(model, expected):
    assert is_agent(model) is expected


def test_agent_dir_defaults_under_the_state_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("PNP_AGENT_DIR")
    monkeypatch.setenv("PNP_STATE_DIR", str(tmp_path / "st"))
    assert agent_dir() == tmp_path / "st" / "agent"


def test_build_client_routes_agent_labels_to_the_handoff_client():
    assert isinstance(build_client(_cfg()), HandoffClient)
    api = replace(_cfg(), model="deepseek-v4-flash", api_key="x")
    assert isinstance(build_client(api), CountingClient)


# --- handoff client ---------------------------------------------------------


def test_a_miss_writes_the_request_and_pends(tmp_path):
    kw = dict(model=LABEL, messages=MESSAGES, temperature=0.2,
              response_format={"type": "json_object"})
    with pytest.raises(AgentPending) as info:
        HandoffClient(_cfg()).chat.completions.create(**kw)
    pid = packet_id(LABEL, MESSAGES)
    assert info.value.packet_id == pid
    assert info.value.step == "extract"
    assert info.value.model == LABEL
    assert info.value.path == tmp_path / "agent" / "extract" / f"{pid}.request.json"
    req = json.loads(info.value.path.read_text(encoding="utf-8"))
    assert req["id"] == pid and req["step"] == "extract" and req["model"] == LABEL
    assert req["response_kind"] == "json"
    assert req["temperature"] == 0.2
    assert req["messages"] == MESSAGES
    assert req["created"].endswith("Z")


def test_an_answered_packet_is_served_and_counted(tmp_path):
    pid = packet_id(LABEL, MESSAGES)
    resp = tmp_path / "agent" / "extract" / f"{pid}.response.md"
    resp.parent.mkdir(parents=True)
    resp.write_text("Hallo", encoding="utf-8")
    out = HandoffClient(_cfg()).chat.completions.create(model=LABEL, messages=MESSAGES)
    assert out.choices[0].message.content == "Hallo"
    assert out.choices[0].message.parsed is None
    assert AGENT_CALLS[("extract", LABEL)] == 1


def test_a_second_request_for_the_same_packet_is_rejected(tmp_path):
    kw = dict(model=LABEL, messages=MESSAGES, response_format={"type": "json_object"})
    pid = packet_id(LABEL, MESSAGES)
    resp = tmp_path / "agent" / "extract" / f"{pid}.response.json"
    resp.parent.mkdir(parents=True)
    resp.write_text("{nicht json", encoding="utf-8")
    client = HandoffClient(_cfg())
    client.chat.completions.create(**kw)  # served; the caller's validation fails
    with pytest.raises(AgentResponseInvalid, match="pnp agent status"):
        client.chat.completions.create(**kw)
    assert not resp.exists()
    assert (resp.parent / "rejected" / resp.name).exists()


def test_the_structured_outputs_probe_is_refused():
    with pytest.raises(NotImplementedError, match="JSON"):
        HandoffClient(_cfg()).beta.chat.completions.parse(model=LABEL, messages=MESSAGES)


# --- end to end through the real steps --------------------------------------


def test_extraction_is_answered_and_cached_under_the_agent_key(tmp_path):
    cfg = _cfg("extract")
    cache = tmp_path / "cache"
    with pytest.raises(AgentPending) as info:
        extract_session(_transcript(), cfg, cache)
    _answer(info.value, json.dumps(EXTRACTION))

    ex = extract_session(_transcript(), cfg, cache)
    assert ex.entities[0].name == "Lindo Laut"
    cached = list((cache / "extract" / "2026-01-01_a").glob("*.json"))
    assert [p.stem for p in cached] == [_cache_key(_transcript(), cfg)]


def test_an_invalid_extraction_fails_without_a_second_attempt(tmp_path, monkeypatch):
    # Tenacity's retry waits ~2s before the second try; that try is the one
    # that must raise, so skip the wait rather than sleep through it.
    monkeypatch.setattr(extract_mod._call_llm_json_prompt.retry, "sleep", lambda _s: None)
    cfg = _cfg("extract")
    with pytest.raises(AgentPending) as info:
        extract_session(_transcript(), cfg, tmp_path / "cache")
    _answer(info.value, "kein JSON")
    with pytest.raises(AgentResponseInvalid):
        extract_session(_transcript(), cfg, tmp_path / "cache")
    assert (info.value.path.parent / "rejected" / f"{info.value.packet_id}.response.json").exists()


def test_synthesis_is_answered_by_markdown(tmp_path):
    entity = CanonicalEntity(
        concept_id="characters/lindo_laut", type=EntityType.CHARACTER,
        canonical_name="Lindo Laut",
        mentions=[MentionRef(session_id="s1", date="2026-01-01", url="https://example.invalid/a",
                             citation_ts="00:01:00", note="Ein Barde.")],
    )
    cfg = _cfg("deep")
    with pytest.raises(AgentPending) as info:
        synthesize_entity_body(entity, cfg, tmp_path / "cache")
    assert info.value.path.name.endswith(".request.json")
    _answer(info.value, "# Überblick\n\nEin Barde.", kind="md")
    assert synthesize_entity_body(entity, cfg, tmp_path / "cache") == "# Überblick\n\nEin Barde."


def test_state_pass_is_answered_by_json(tmp_path):
    cfg = _cfg("state")
    with pytest.raises(AgentPending) as info:
        run_state([_transcript()], cfg, tmp_path / "cache", GLOSS)
    _answer(info.value, json.dumps({"threads": [], "status_changes": [], "attitudes": []}))
    run = run_state([_transcript()], cfg, tmp_path / "cache", GLOSS)
    assert run.called == 1


def test_dedup_collects_pending_packets_per_identity_space():
    entities = [
        CanonicalEntity(concept_id="characters/a", type=EntityType.CHARACTER, canonical_name="A"),
        CanonicalEntity(concept_id="characters/b", type=EntityType.CHARACTER, canonical_name="B"),
        CanonicalEntity(concept_id="locations/x", type=EntityType.LOCATION, canonical_name="X"),
        CanonicalEntity(concept_id="locations/y", type=EntityType.LOCATION, canonical_name="Y"),
    ]
    with pytest.raises(AgentWorkPending) as info:
        dedup_mod.llm_candidates(entities, _cfg("dedup"))
    assert sorted(p.step for p in info.value.pending) == ["dedup", "dedup"]
    assert len(info.value.pending) == 2


# --- cli --------------------------------------------------------------------


def test_run_with_pending_extraction_exits_4_and_writes_no_bundle(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")  # all steps are agents: no key needed
    bundle = tmp_path / "knowledge" / "bundle" / "campaign"
    rc = cli.main(["run", "--no-api", *ALL_AGENT, "--transcripts", str(_transcripts_dir(tmp_path)),
                   "--bundle", str(bundle), "--cache", str(tmp_path / "cache")])
    assert rc == 4
    assert not bundle.exists()
    assert len(list((tmp_path / "agent" / "extract").glob("*.request.json"))) == 1


def test_state_with_a_pending_session_exits_4(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    write_glossary(knowledge, GLOSS)
    rc = cli.main(["state", "--no-api", *ALL_AGENT,
                   "--transcripts", str(_transcripts_dir(tmp_path)),
                   "--bundle", str(knowledge / "bundle" / "campaign"),
                   "--cache", str(tmp_path / "cache")])
    assert rc == 4
    assert len(list((tmp_path / "agent" / "state").glob("*.request.json"))) == 1


def test_an_unknown_model_step_is_a_usage_error(tmp_path):
    rc = cli.main(["extract", "--model", "bogus=x", "--cache", str(tmp_path / "c")])
    assert rc == 2


def test_no_api_refuses_a_step_still_on_deepseek(tmp_path):
    rc = cli.main(["extract", "--no-api", "--model", f"extract={LABEL}",
                   "--transcripts", str(_transcripts_dir(tmp_path)),
                   "--cache", str(tmp_path / "c")])
    assert rc == 2


def test_strict_model_flag_sets_the_env_switch(tmp_path):
    cli.main(["extract", "--strict-model", "--no-api", "--cache", str(tmp_path / "c")])
    assert os.environ.get("PNP_STRICT_MODEL") == "1"
