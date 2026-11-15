"""Tests for the offline extraction golden benchmark (contract E1, sections 0-5).

All data here is invented. Shared helpers at the top are reused by later stages.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extraction_benchmark as eb  # noqa: E402

MODULE_PATH = Path(__file__).resolve().parents[1] / "extraction_benchmark.py"
SESSION = "2026-01-01_Test-Runde_Invented"

SEG_TEXTS = [
    "Alrik betritt die Mühle von Tannbach und sucht nach dem Müller.",
    "Brunhild wartet im Hof und erzählt von einem Brief aus der Stadt.",
    "Der Müller gibt zu, dass er nachts Fremde in der Mühle gesehen hat.",
    "Alrik untersucht die alte Mühle und findet ein verborgenes Siegel.",
    "Brunhild bittet die Gruppe, das Siegel vorerst nicht zu berühren.",
    "Am Abend beschließt die Gruppe, bei Tagesanbruch zur Mühle zurückzukehren.",
]
SPEAKERS = ["SL", "Spielerin A", "SL", "Spieler B", "Spielerin A", "SL"]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_segments() -> list[dict]:
    return [
        {"start": i * 60.0, "end": i * 60.0 + 50.0, "speaker": SPEAKERS[i], "text": SEG_TEXTS[i]} for i in range(6)
    ]


def make_extraction() -> dict:
    return {
        "recap": (
            "Alrik betritt die Mühle von Tannbach. Brunhild berichtet von einem Brief.\n\n"
            "## Szene 1\n\nDie Gruppe untersucht die Mühle und findet ein Siegel."
        ),
        "entities": [
            {
                "name": "Alrik",
                "type": "Character",
                "note": "Alrik untersucht die alte Mühle und findet ein verborgenes Siegel.",
                "citation_ts": "00:03:00",
                "subtype": "",
            },
            {
                "name": "Brunhild",
                "type": "NPC",
                "note": "Brunhild wartet im Hof und bittet die Gruppe um Vorsicht.",
                "citation_ts": "00:01:00",
                "subtype": "",
            },
            {
                "name": "Mühle von Tannbach",
                "type": "Location",
                "note": "Der Müller gibt zu, dass er nachts Fremde in der Mühle gesehen hat.",
                "citation_ts": "00:02:00",
                "subtype": "Gebäude",
            },
        ],
    }


def make_gold() -> dict:
    return {
        "version": 1,
        "entities": [
            {
                "id": "E_ALRIK",
                "label": "Alrik",
                "aliases": [],
                "required": True,
                "accepted": [{"type": "Character", "subtypes": None}],
                "evidence": ["S000"],
            },
            {
                "id": "E_BRUNHILD",
                "label": "Brunhild",
                "aliases": ["Brun"],
                "required": False,
                "accepted": [{"type": "NPC", "subtypes": None}],
                "evidence": ["S001"],
            },
            {
                "id": "E_MUEHLE",
                "label": "Mühle von Tannbach",
                "aliases": ["Mühle"],
                "required": True,
                "accepted": [{"type": "Location", "subtypes": ["Gebäude"]}],
                "evidence": ["S000"],
            },
        ],
        "facts": [
            {
                "id": "F_SIEGEL",
                "statement": "Alrik findet in der Mühle ein Siegel.",
                "scene": "Szene 1",
                "subjects": ["E_ALRIK", "E_MUEHLE"],
                "evidence": [{"segment": "S003", "quote": SEG_TEXTS[3]}],
                "qualifiers": "",
                "weight": 3,
                "placement": "any",
            },
            {
                "id": "F_BRIEF",
                "statement": "Brunhild hat einen Brief aus der Stadt erhalten.",
                "scene": "Szene 1",
                "subjects": ["E_BRUNHILD"],
                "evidence": [{"segment": "S001", "quote": SEG_TEXTS[1]}],
                "qualifiers": "",
                "weight": 1,
                "placement": "any",
            },
        ],
        "notes": [{"id": "N_SIEGEL", "fact": "F_SIEGEL", "entity": "E_ALRIK", "weight": 3}],
        "critical": [
            {
                "id": "K_SIEGEL",
                "description": "Das Siegel wird nicht gebrochen.",
                "trigger": "Alrik bricht das Siegel auf.",
                "evidence": ["S004"],
                "rationale": "Brunhild hat ausdrücklich darum gebeten.",
            }
        ],
        "questions": [{"id": "Q_MUELLER", "text": "Wer war der Müller?", "segments": ["S002"], "items": ["Name"]}],
        "excluded": [{"segments": ["S005"], "reason": "Nur Organisatorisches."}],
    }


def make_case(tmp_path: Path) -> dict:
    segments = make_segments()
    experiment = tmp_path / "experiment"
    experiment.mkdir()
    transcript = experiment / "transcript.json"
    transcript_bytes = json.dumps({"segments": segments}, ensure_ascii=False, indent=2).encode("utf-8")
    transcript.write_bytes(transcript_bytes)
    request = {
        "messages": [
            {"role": "system", "content": "Du extrahierst Fakten aus einer Sitzung. Antworte nur mit JSON."},
            {"role": "user", "content": "Transkript:\n" + eb.render_dialogue(segments) + "\n"},
        ]
    }
    request_bytes = json.dumps(request, ensure_ascii=False, indent=2).encode("utf-8")
    schema_bytes = json.dumps({"type": "object", "required": ["recap", "entities"]}).encode("utf-8")
    (experiment / "request.json").write_bytes(request_bytes)
    (experiment / "schema.json").write_bytes(schema_bytes)
    manifest = {
        "session_id": SESSION,
        "transcript_sha256": sha256_hex(transcript_bytes),
        "request_sha256": sha256_hex(request_bytes),
        "schema_sha256": sha256_hex(schema_bytes),
    }
    (experiment / "manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    return {
        "experiment": experiment,
        "transcript": transcript,
        "case_dir": tmp_path / "bench" / "cases" / SESSION,
        "segments": segments,
    }


def prepared_case(tmp_path: Path, gold: dict | None = None) -> dict:
    paths = make_case(tmp_path)
    eb.prepare(paths["experiment"], paths["transcript"], paths["case_dir"])
    (paths["case_dir"] / "gold").mkdir(parents=True, exist_ok=True)
    (paths["case_dir"] / "gold" / "draft.json").write_bytes(eb.canon(gold or make_gold()))
    paths["rubric"] = paths["case_dir"].parent.parent / "rubrics" / "v1.json"
    return paths


def expected_approval_hash(paths: dict) -> str:
    gold = eb.read_json(paths["case_dir"] / "gold" / "draft.json")
    rubric = eb.read_json(paths["rubric"])
    source = eb.read_json(paths["case_dir"] / "case_manifest.json")["source_sha256"]
    return eb.approval_hash(eb.hash_obj(gold), eb.hash_obj(rubric), source)


def approve(paths: dict, *, isatty=lambda: True, environ=None, typed=None, confirm=None) -> Path:
    full = expected_approval_hash(paths)
    return eb.approve_gold(
        paths["case_dir"],
        paths["rubric"],
        full if typed is None else typed,
        "Reviewer A",
        "test-ref",
        isatty=isatty,
        environ={} if environ is None else environ,
        confirm=confirm or (lambda: full[:12]),
    )


JUDGE_PROMPT_SHA = sha256_hex(b"invented judge prompt")
ARM = {"label": "arm-alpha", "host": "host-alpha", "model": "model-alpha", "effort": "effort-alpha", "repeats": 1}


def make_inventory(extraction: dict) -> dict:
    # One claim per sentence, each in its own group. Headings are not claims.
    claims: list[dict] = []

    def add(loc: str, span: str, kind: str) -> None:
        n = len(claims) + 1
        claims.append({"id": f"C{n:03d}", "loc": loc, "span": span, "group": f"G{n:03d}", "kind": kind})

    for sentence in eb.sentences(extraction["recap"]):
        add("recap", sentence, "not_claim" if sentence.startswith("#") else "claim")
    for i, ent in enumerate(extraction["entities"]):
        for sentence in eb.sentences(ent["note"]):
            add(f"entity:{i}", sentence, "claim")
    return {"output_sha256": eb.hash_obj(extraction), "config": {}, "claims": claims}


def judge_meta(judge: str) -> dict:
    return {"host": f"host-{judge}", "model": f"model-{judge}", "effort": "high", "prompt_sha256": JUDGE_PROMPT_SHA}


def make_judgment_a(inventory: dict, extraction: dict, judge: str = "claude") -> dict:
    claims = {
        c["id"]: {"verdict": "supported", "segments": ["S000"], "why": "invented"}
        for c in inventory["claims"]
        if c["kind"] == "claim"
    }
    locators = {
        str(i): {"verdict": "supported", "segments": ["S000"], "why": "invented"}
        for i in range(len(extraction["entities"]))
    }
    return {"binds": {}, "judge": judge_meta(judge), "claims": claims, "locators": locators}


def make_judgment_b(gold: dict, extraction: dict, judge: str = "claude") -> dict:
    gold_id_by_label = {e["label"]: e["id"] for e in gold["entities"]}
    entities = {
        str(i): {
            "match": f"gold:{gold_id_by_label[ent['name']]}",
            "type_ok": True,
            "subtype_ok": True,
            "segments": ["S000"],
        }
        for i, ent in enumerate(extraction["entities"])
    }
    index_of = {v["match"]: int(k) for k, v in entities.items()}
    return {
        "binds": {},
        "judge": judge_meta(judge),
        "facts": {
            f["id"]: {"verdict": "present", "spans": [ev["quote"] for ev in f["evidence"]], "why": "invented"}
            for f in gold["facts"]
        },
        "notes": {
            req["id"]: {
                "verdict": "present",
                "entity_index": index_of[f"gold:{req['entity']}"],
                "why": "invented",
            }
            for req in gold["notes"]
        },
        "entities": entities,
        "critical": {r["id"]: {"verdict": "not_violated", "spans": [], "why": "invented"} for r in gold["critical"]},
    }


def prepared_outputs(tmp_path: Path) -> dict:
    # make_case -> prepare -> draft gold -> one attempt with raw.txt -> validate_run -> prepare_grading.
    paths = prepared_case(tmp_path)
    run_dir = tmp_path / "bench" / "runs" / "run1"
    (attempt,) = eb.prepare_run(run_dir, paths["case_dir"], {"arms": [ARM]})
    (attempt / "raw.txt").write_text(json.dumps(make_extraction(), ensure_ascii=False), encoding="utf-8")
    eb.validate_run(run_dir, paths["case_dir"])
    anon_map = eb.prepare_grading(run_dir, paths["case_dir"], salt="invented-salt")
    anon = anon_map[attempt.name]
    return {
        **paths,
        "gold": make_gold(),
        "extraction": make_extraction(),
        "run_dir": run_dir,
        "attempt": attempt,
        "anon": anon,
        "grading": run_dir / "grading" / anon,
    }


def make_graded_run(tmp_path: Path) -> dict:
    out = prepared_outputs(tmp_path)
    inventory = make_inventory(out["extraction"])
    eb.write_json(out["grading"] / "inventory.json", inventory)
    for judge in ("claude", "codex"):
        a = make_judgment_a(inventory, out["extraction"], judge)
        a["binds"] = eb.expected_binds("A", out["grading"], out["case_dir"])
        eb.write_json(out["grading"] / f"A.{judge}.json", a)
        b = make_judgment_b(out["gold"], out["extraction"], judge)
        b["binds"] = eb.expected_binds("B", out["grading"], out["case_dir"])
        eb.write_json(out["grading"] / f"B.{judge}.json", b)
    return {**out, "inventory": inventory}


# --- 1. hashing and files / case preparation / approval state -------------------------


def test_01_source_hash_mismatch_refuses_prepare(tmp_path):
    paths = make_case(tmp_path)
    paths["transcript"].write_text(paths["transcript"].read_text("utf-8") + " ", encoding="utf-8")
    with pytest.raises(eb.BenchError):
        eb.prepare(paths["experiment"], paths["transcript"], paths["case_dir"])
    assert not paths["case_dir"].exists() or not any(paths["case_dir"].iterdir())


def test_01_dialogue_missing_from_request_refused(tmp_path):
    paths = make_case(tmp_path)
    request = {"messages": [{"role": "system", "content": "x"}, {"role": "user", "content": "kein Dialog"}]}
    request_bytes = json.dumps(request, ensure_ascii=False).encode("utf-8")
    (paths["experiment"] / "request.json").write_bytes(request_bytes)
    manifest = eb.read_json(paths["experiment"] / "manifest.json")
    manifest["request_sha256"] = sha256_hex(request_bytes)
    (paths["experiment"] / "manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    with pytest.raises(eb.BenchError):
        eb.prepare(paths["experiment"], paths["transcript"], paths["case_dir"])
    assert not paths["case_dir"].exists()


def test_01_prepare_writes_case_files_and_default_rubric(tmp_path):
    paths = make_case(tmp_path)
    manifest = eb.prepare(paths["experiment"], paths["transcript"], paths["case_dir"])
    for name in ("source.json", "baseline_request.json", "schema.json", "dialogue.txt", "prompt.txt"):
        assert (paths["case_dir"] / name).is_file(), name
    assert manifest["segments"] == 6
    assert manifest["source_sha256"] == sha256_hex(paths["transcript"].read_bytes())
    assert (paths["case_dir"] / "case_manifest.json").is_file()
    rubric_path = paths["case_dir"].parent.parent / "rubrics" / "v1.json"
    assert eb.read_json(rubric_path) == eb.DEFAULT_RUBRIC


def test_01_stale_approval_after_gold_edit(tmp_path):
    paths = prepared_case(tmp_path)
    approve(paths)
    gold, reason = eb.check_approval(paths["case_dir"], paths["rubric"])
    assert reason == "" and gold is not None
    edited = make_gold()
    edited["facts"][1]["weight"] = 3
    (paths["case_dir"] / "gold" / "v1.json").write_bytes(eb.canon(edited))
    assert eb.check_approval(paths["case_dir"], paths["rubric"]) == (None, "gold changed since approval")


def test_01_changed_rubric_makes_approval_stale(tmp_path):
    paths = prepared_case(tmp_path)
    approve(paths)
    rubric = eb.read_json(paths["rubric"])
    rubric["tolerance"] = 3.0
    paths["rubric"].write_bytes(json.dumps(rubric).encode("utf-8"))
    assert eb.check_approval(paths["case_dir"], paths["rubric"]) == (None, "rubric changed since approval")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda g: g.pop("version"),
        lambda g: g["entities"].append(copy.deepcopy(g["entities"][0])),
        lambda g: g["facts"][0]["evidence"][0].update(quote="Alrik findet ein Schwert."),
        lambda g: g["facts"][0].update(weight=2),
        lambda g: g["entities"][0].update(evidence=["S099"]),
        lambda g: g["facts"][0].update(subjects=["E_NOPE"]),
        lambda g: g["notes"][0].update(entity="E_NOPE"),
        lambda g: g["entities"][0].update(accepted=[]),
        lambda g: g["entities"][0]["accepted"][0].update(type="Dragon"),
        lambda g: g["critical"][0].update(trigger=""),
        lambda g: [e.update(required=False) for e in g["entities"]],
        lambda g: g.update(facts=[]),
    ],
)
def test_02_validate_gold_rejects_bad_gold(mutate):
    segments = make_segments()
    assert eb.validate_gold(make_gold(), segments) == []
    gold = make_gold()
    mutate(gold)
    assert eb.validate_gold(gold, segments)


# --- 2. approval refusals -------------------------------------------------------------


def test_02_approve_refused_without_tty(tmp_path):
    paths = prepared_case(tmp_path)
    with pytest.raises(eb.BenchError):
        approve(paths, isatty=lambda: False)
    assert not list((paths["case_dir"] / "gold").glob("*.approval.json"))


@pytest.mark.parametrize("env", [{"CLAUDECODE": "1"}, {"CODEX_HOME": "x"}])
def test_02_approve_refused_in_agent_environment(tmp_path, env):
    paths = prepared_case(tmp_path)
    with pytest.raises(eb.BenchError):
        approve(paths, environ=env)
    assert not list((paths["case_dir"] / "gold").glob("*.approval.json"))


def test_02_approve_refused_with_wrong_hash(tmp_path):
    paths = prepared_case(tmp_path)
    with pytest.raises(eb.BenchError):
        approve(paths, typed="0" * 64)
    with pytest.raises(eb.BenchError):
        approve(paths, typed="abc")
    assert not list((paths["case_dir"] / "gold").glob("*.approval.json"))


def test_02_approve_refused_with_wrong_confirm(tmp_path):
    paths = prepared_case(tmp_path)
    with pytest.raises(eb.BenchError):
        approve(paths, confirm=lambda: "x" * 12)
    assert not list((paths["case_dir"] / "gold").glob("*.approval.json"))


def test_02_approve_happy_path_writes_both_files(tmp_path):
    paths = prepared_case(tmp_path)
    approval_path = approve(paths)
    assert approval_path.name == "v1.approval.json"
    assert (paths["case_dir"] / "gold" / "v1.json").is_file()
    record = eb.read_json(approval_path)
    assert set(record) == {
        "approval_hash",
        "gold_hash",
        "rubric_hash",
        "source_sha256",
        "reviewer",
        "approval_ref",
        "date",
    }
    assert record["approval_hash"] == expected_approval_hash(paths)
    assert eb.check_approval(paths["case_dir"], paths["rubric"])[1] == ""


# --- 3. output validity -----------------------------------------------------------------


def test_03_correct_extraction_is_valid():
    result = eb.validate_output(json.dumps(make_extraction(), ensure_ascii=False), make_segments())
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["extraction"] is not None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "{not json",
        json.dumps({"recap": 1, "entities": "x"}),
        json.dumps({**make_extraction(), "entities": []}),
    ],
    ids=["empty", "broken-json", "schema-invalid", "zero-entities"],
)
def test_03_invalid_outputs_are_not_valid(raw):
    result = eb.validate_output(raw, make_segments())
    assert result["valid"] is False
    assert result["errors"]


# --- 5. citation timestamps and subtypes -------------------------------------------------


@pytest.mark.parametrize("ts", ["99:00:00", "abc"])
def test_07_invalid_citation_timestamp_is_invalid(ts):
    extraction = make_extraction()
    extraction["entities"][0]["citation_ts"] = ts
    result = eb.validate_output(json.dumps(extraction), make_segments())
    assert result["valid"] is False


def test_05_subtype_outside_closed_list_is_invalid():
    extraction = make_extraction()
    extraction["entities"][2]["subtype"] = "Schloss"
    assert eb.validate_output(json.dumps(extraction), make_segments())["valid"] is False


# --- 12. attempt ids and write-once ------------------------------------------------------


def test_12_attempt_id_changes_with_each_input():
    base = ("case", "prompt", "schema", "codex", "gpt-x", "high", 1)
    base_id = eb.attempt_id(*base)
    assert len(base_id) == 12
    assert int(base_id, 16) >= 0
    variants = [
        ("case", "prompt", "schema", "codex", "gpt-x", "medium", 1),
        ("case", "prompt", "schema", "codex", "gpt-x", "high", 2),
        ("case", "other", "schema", "codex", "gpt-x", "high", 1),
        ("case", "prompt", "schema", "codex", "gpt-y", "high", 1),
    ]
    ids = {eb.attempt_id(*v) for v in variants}
    assert base_id not in ids
    assert len(ids) == len(variants)


def test_12_write_once_semantics(tmp_path):
    target = tmp_path / "deep" / "file.json"
    assert eb.write_once(target, b"one") is True
    assert eb.write_once(target, b"one") is False
    with pytest.raises(eb.BenchError):
        eb.write_once(target, b"two")
    assert target.read_bytes() == b"one"


# --- 14. repair states ------------------------------------------------------------------


def _attempt_dir(root: Path, raw: str, repair: str | None = None) -> Path:
    attempt = root / "attempt"
    attempt.mkdir(parents=True)
    (attempt / "raw.txt").write_text(raw, encoding="utf-8")
    if repair is not None:
        (attempt / "repair.raw.txt").write_text(repair, encoding="utf-8")
    return attempt


@pytest.mark.parametrize("wrap", [lambda b: "```json\n" + b + "\n```", lambda b: "\n\n   " + b + "   \n"])
def test_14_repair_with_fence_only_change_is_repaired(tmp_path, wrap):
    body = json.dumps(make_extraction(), ensure_ascii=False, indent=2)
    attempt = _attempt_dir(tmp_path, "Hier:\n" + body, wrap(body))
    assert eb.attempt_state(attempt, make_segments())["state"] == "repaired"


def test_14_repair_with_rewritten_prose_fails(tmp_path):
    body = json.dumps(make_extraction(), ensure_ascii=False, indent=2)
    rewritten = make_extraction()
    rewritten["recap"] = "Völlig anderer Text über Drachen und Schiffe, die im Hafen verschwinden, ohne Grund."
    attempt = _attempt_dir(tmp_path, "Hier:\n" + body, json.dumps(rewritten, ensure_ascii=False))
    state = eb.attempt_state(attempt, make_segments())
    assert state["state"] == "failed"
    assert state["similarity"] < eb.REPAIR_MIN


def test_14_pending_and_valid_states(tmp_path):
    attempt = tmp_path / "empty-attempt"
    attempt.mkdir()
    assert eb.attempt_state(attempt, make_segments())["state"] == "pending"
    (attempt / "raw.txt").write_text(json.dumps(make_extraction(), ensure_ascii=False), encoding="utf-8")
    assert eb.attempt_state(attempt, make_segments())["state"] == "valid"


def test_14_validate_run_writes_extraction_for_valid_attempt(tmp_path):
    paths = prepared_case(tmp_path)
    run_dir = tmp_path / "runs" / "run1"
    arm = {"label": "arm-a", "host": "codex", "model": "m1", "effort": "high", "repeats": 1}
    created = eb.prepare_run(run_dir, paths["case_dir"], {"arms": [arm]})
    assert len(created) == 1
    attempt = created[0]
    assert attempt.name.startswith("arm-a-r1-")
    assert eb.read_json(attempt / "attempt.json")["kind"] == "new"
    (attempt / "raw.txt").write_text(json.dumps(make_extraction(), ensure_ascii=False), encoding="utf-8")
    states = eb.validate_run(run_dir, paths["case_dir"])
    assert states[attempt.name]["state"] == "valid"
    assert (attempt / "extraction.json").read_bytes() == eb.canon(make_extraction())


# --- 17. import discipline --------------------------------------------------------------


def test_17_no_forbidden_module_level_imports():
    forbidden = {"openai", "httpx", "requests", "anthropic", "socket", "urllib", "pnp_okf"}
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    assert not (found & forbidden), found & forbidden


# --- 5b. repeat numbering ---------------------------------------------------------------


def test_05_prepare_run_honours_first_repeat(tmp_path):
    paths = prepared_case(tmp_path)
    arm = {"label": "finalist", "host": "codex", "model": "m1", "effort": "high", "repeats": 2, "first_repeat": 2}
    created = eb.prepare_run(tmp_path / "runs" / "run1", paths["case_dir"], {"arms": [arm]})
    assert [eb.read_json(p / "attempt.json")["repeat"] for p in created] == [2, 3]


# --- 6. judgment items and sentences (inventory) ------------------------------------------


def test_10_complete_inventory_is_valid():
    extraction = make_extraction()
    assert eb.validate_inventory(make_inventory(extraction), extraction) == []


def test_10_sentences_split_per_line_and_keep_abbreviations():
    assert eb.sentences("Ja.\n\nAlrik wartet. Brunhild lacht!") == ["Ja.", "Alrik wartet.", "Brunhild lacht!"]
    assert eb.sentences("Dr. Brunhild wartet im Hof.") == ["Dr. Brunhild wartet im Hof."]


def test_10_non_verbatim_span_is_rejected():
    extraction = make_extraction()
    inventory = make_inventory(extraction)
    inventory["claims"][0]["span"] = "Alrik betritt die Mühle von Brunhild."
    assert eb.validate_inventory(inventory, extraction)


def test_10_uncovered_sentence_is_rejected():
    extraction = make_extraction()
    inventory = make_inventory(extraction)
    inventory["claims"] = [c for c in inventory["claims"] if c["loc"] != "entity:1"]
    assert eb.validate_inventory(inventory, extraction)


def test_10_two_word_sentence_still_needs_coverage():
    extraction = make_extraction()
    extraction["recap"] = "Alrik wartet. Brunhild lacht."
    inventory = make_inventory(extraction)
    assert eb.validate_inventory(inventory, extraction) == []
    inventory["claims"] = [c for c in inventory["claims"] if c["span"] != "Brunhild lacht."]
    assert eb.validate_inventory(inventory, extraction)


def test_10_inventory_for_other_output_is_rejected():
    extraction = make_extraction()
    inventory = make_inventory(extraction)
    other = make_extraction()
    other["recap"] += " Zusatz."
    inventory["output_sha256"] = eb.hash_obj(other)
    assert eb.validate_inventory(inventory, extraction)


def test_10_duplicate_id_unknown_loc_and_no_claim_are_rejected():
    extraction = make_extraction()
    duplicate = make_inventory(extraction)
    duplicate["claims"].append(dict(duplicate["claims"][0]))
    assert eb.validate_inventory(duplicate, extraction)
    unknown = make_inventory(extraction)
    unknown["claims"][0]["loc"] = "entity:9"
    assert eb.validate_inventory(unknown, extraction)
    no_claim = make_inventory(extraction)
    no_claim["claims"] = [dict(c, kind="not_claim") for c in no_claim["claims"]]
    assert eb.validate_inventory(no_claim, extraction)


# --- 9. cost ------------------------------------------------------------------------------


def _price(**over) -> dict:
    row = {
        "model": "invented-model",
        "currency": "USD",
        "input": 2.0,
        "cache_read": 0.5,
        "cache_write": 0.0,
        "output": 8.0,
        "source_url": "https://example.invalid/prices",
        "retrieved": "2026-11-15",
        "tier": "standard",
        "max_input_tokens": None,
    }
    row.update(over)
    return row


def _write_usage(root: Path, style: str, raw_turns: list[dict]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    doc = {"style": style, "model": "invented-model", "turns": raw_turns, "provenance": "test"}
    (root / "usage.json").write_text(json.dumps(doc), encoding="utf-8")
    return root


OPENAI_TURN = {
    "prompt_tokens": 1000,
    "completion_tokens": 200,
    "prompt_tokens_details": {"cached_tokens": 400},
    "completion_tokens_details": {"reasoning_tokens": 50},
}


def test_11_openai_cached_tokens_are_a_subset_of_input():
    turn = eb.normalise_usage("openai", OPENAI_TURN)
    assert turn == {"input_total": 1000, "cache_read": 400, "cache_write": 0, "output_total": 200, "reasoning": 50}
    result = eb.cost([turn], _price())
    assert result["standard"] == pytest.approx(0.0036)
    assert result["observed"] == pytest.approx(0.0030)
    assert result["unknown"] == []


def test_11_anthropic_cache_tokens_are_added_to_input():
    raw = {"input_tokens": 100, "cache_read_input_tokens": 300, "cache_creation_input_tokens": 50, "output_tokens": 200}
    turn = eb.normalise_usage("anthropic", raw)
    assert turn["input_total"] == 450
    assert turn["cache_read"] == 300
    assert turn["cache_write"] == 50
    assert turn["output_total"] == 200
    result = eb.cost([turn], _price(input=3.0, cache_read=0.3, cache_write=3.75, output=15.0))
    assert result["standard"] == pytest.approx(0.00435)
    assert result["observed"] == pytest.approx(0.0035775)


def test_11_repair_turn_is_included(tmp_path):
    attempt = _write_usage(tmp_path / "attempt", "openai", [OPENAI_TURN])
    (attempt / "repair.raw.txt").write_text("{}", encoding="utf-8")
    (attempt / "repair.usage.json").write_text(
        json.dumps({"style": "openai", "model": "invented-model", "turns": [OPENAI_TURN], "provenance": "repair"}),
        encoding="utf-8",
    )
    result = eb.attempt_cost(attempt, {"rows": [_price()]})
    assert result["standard"] == pytest.approx(0.0072)
    assert result["observed"] == pytest.approx(0.0060)


def test_11_repair_without_usage_is_unknown(tmp_path):
    attempt = _write_usage(tmp_path / "attempt", "openai", [OPENAI_TURN])
    (attempt / "repair.raw.txt").write_text("{}", encoding="utf-8")
    result = eb.attempt_cost(attempt, {"rows": [_price()]})
    assert result["standard"] is None and result["observed"] is None and result["unknown"]


def test_11_missing_usage_is_unknown_not_zero(tmp_path):
    partial = _write_usage(tmp_path / "partial", "openai", [{"prompt_tokens": 1000}])
    result = eb.attempt_cost(partial, {"rows": [_price()]})
    assert result["standard"] is None and result["observed"] is None and result["unknown"]
    empty = eb.attempt_cost(tmp_path / "no-usage", {"rows": [_price()]})
    assert empty["standard"] is None and empty["observed"] is None


def test_11_no_price_row_or_over_limit_is_unknown(tmp_path):
    attempt = _write_usage(tmp_path / "attempt", "openai", [OPENAI_TURN])
    no_row = eb.attempt_cost(attempt, {"rows": [_price(model="other-model")]})
    assert no_row["standard"] is None and no_row["observed"] is None
    over = eb.attempt_cost(attempt, {"rows": [_price(max_input_tokens=500)]})
    assert over["standard"] is None and over["observed"] is None and over["unknown"]


def test_11_grading_usage_is_not_extraction_cost(tmp_path):
    attempt = _write_usage(tmp_path / "attempt", "openai", [OPENAI_TURN])
    prices = {"rows": [_price()]}
    before = eb.attempt_cost(attempt, prices)
    grader = {
        "style": "openai",
        "model": "invented-model",
        "turns": [{"prompt_tokens": 9999999, "completion_tokens": 1}],
    }
    (attempt / "usage.claude.json").write_text(json.dumps(grader), encoding="utf-8")
    assert eb.attempt_cost(attempt, prices) == before


# --- 7. judgments and resolution ----------------------------------------------------------


def test_07_resolve_agreed_and_disputed():
    assert eb.resolve("F:C1", {"claude": "supported", "codex": "supported"}, {}) == ("supported", "agreed")
    assert eb.resolve("F:C1", {"claude": "supported", "codex": "unsupported"}, {}) == (None, "disputed")


def test_07_resolve_missing_with_one_judge():
    assert eb.resolve("F:C1", {"claude": "supported"}, {}) == (None, "missing")


def test_07_resolve_adjudication_wins_over_disagreement_and_missing():
    adjudication = {"F:C1": {"verdict": "unsupported", "by": "human", "ref": "x"}}
    disputed = {"claude": "supported", "codex": "contradicted"}
    assert eb.resolve("F:C1", disputed, adjudication) == ("unsupported", "adjudicated")
    assert eb.resolve("F:C1", {"claude": "supported"}, adjudication) == ("unsupported", "adjudicated")


def test_07_both_unresolved_is_disputed():
    both = {"claude": "unresolved", "codex": "unresolved"}
    assert eb.resolve("F:C1", both, {}) == (None, "disputed")


def test_07_entity_and_note_values_are_tuples():
    entity = {"claude": ("gold:E_ALRIK", True, True), "codex": ("gold:E_ALRIK", True, True)}
    assert eb.resolve("E:0", entity, {}) == (("gold:E_ALRIK", True, True), "agreed")
    adjudication = {"E:0": {"match": "unsupported", "type_ok": False, "subtype_ok": False, "by": "human", "ref": "x"}}
    assert eb.resolve("E:0", entity, adjudication) == (("unsupported", False, False), "adjudicated")
    notes = {"claude": ("present", 0), "codex": ("present", 1)}
    assert eb.resolve("N:N_SIEGEL", notes, {}) == (None, "disputed")


def _edit_json(path: Path, mutate) -> None:
    doc = eb.read_json(path)
    mutate(doc)
    path.write_bytes(eb.canon(doc))


def test_07_overlay_replaces_item_and_base_stays_available(tmp_path):
    out = make_graded_run(tmp_path)
    folder = out["grading"]
    claim_id = next(iter(eb.read_json(folder / "A.claude.json")["claims"]))
    overlay = {"claims": {claim_id: {"verdict": "unsupported", "segments": ["S001"], "why": "revised"}}}
    (folder / "A.claude.x.json").write_bytes(eb.canon(overlay))
    merged = eb.load_judgments(folder, "A")
    assert set(merged) == {"claude", "codex"}
    assert merged["claude"]["claims"][claim_id]["verdict"] == "unsupported"
    assert merged["claude"]["claims"][claim_id]["why"] == "revised"
    base = eb.load_judgments(folder, "A", overlay=False)
    assert base["claude"]["claims"][claim_id]["verdict"] == "supported"


def test_07_bad_claim_verdict_raises(tmp_path):
    out = make_graded_run(tmp_path)
    claim_id = next(iter(eb.read_json(out["grading"] / "A.codex.json")["claims"]))
    _edit_json(out["grading"] / "A.codex.json", lambda d: d["claims"][claim_id].update(verdict="maybe"))
    with pytest.raises(eb.BenchError, match="A.codex.json"):
        eb.load_judgments(out["grading"], "A")


def test_07_bad_entity_match_raises(tmp_path):
    out = make_graded_run(tmp_path)
    _edit_json(out["grading"] / "B.claude.json", lambda d: d["entities"]["0"].update(match="alias-guess"))
    with pytest.raises(eb.BenchError, match="B.claude.json"):
        eb.load_judgments(out["grading"], "B")


def test_07_diff_judgments_lists_disputes_and_writes_exchange(tmp_path):
    out = make_graded_run(tmp_path)
    _edit_json(out["grading"] / "B.codex.json", lambda d: d["facts"]["F_SIEGEL"].update(verdict="absent"))
    assert eb.diff_judgments(out["run_dir"], out["case_dir"]) == {"disputed": 1, "missing": 0}
    rows = eb.read_json(out["run_dir"] / "disagreements.json")
    assert [r["key"] for r in rows] == ["C:F_SIEGEL"]
    assert rows[0]["how"] == "disputed"
    assert rows[0]["verdicts"] == {"claude": "present", "codex": "absent"}
    exchange = eb.read_json(out["run_dir"] / "exchange" / f"{out['anon']}.B.claude.json")
    assert [item["key"] for item in exchange] == ["C:F_SIEGEL"]
    assert set(exchange[0]["evidence"]) == {"codex"}
    assert "verdict" not in exchange[0]["evidence"]["codex"]


# --- 12. stale judgments ------------------------------------------------------------------


def test_12_stale_reasons_flag_gold_and_inventory_changes(tmp_path):
    out = make_graded_run(tmp_path)
    folder, case_dir = out["grading"], out["case_dir"]
    judgment_a = eb.load_judgments(folder, "A")["claude"]
    judgment_b = eb.load_judgments(folder, "B")["claude"]
    assert eb.stale_reasons("A", judgment_a, eb.expected_binds("A", folder, case_dir)) == []
    assert eb.stale_reasons("B", judgment_b, eb.expected_binds("B", folder, case_dir)) == []

    _edit_json(case_dir / "gold" / "draft.json", lambda g: g["facts"][1].update(weight=3))
    gold_reasons = eb.stale_reasons("B", judgment_b, eb.expected_binds("B", folder, case_dir))
    assert gold_reasons and any("gold" in r for r in gold_reasons)

    _edit_json(folder / "inventory.json", lambda inv: inv.update(config={"changed": True}))
    inventory_reasons = eb.stale_reasons("A", judgment_a, eb.expected_binds("A", folder, case_dir))
    assert inventory_reasons and any("inventory" in r for r in inventory_reasons)


# --- 13. identity discipline --------------------------------------------------------------


def test_13_grading_folder_carries_no_attempt_identity(tmp_path):
    out = prepared_outputs(tmp_path)
    grading = out["run_dir"] / "grading"
    files = [p for p in grading.rglob("*") if p.is_file()]
    assert files
    for path in files:
        text = path.read_bytes().decode("utf-8")
        for needle in (ARM["label"], ARM["model"], ARM["effort"], ARM["host"]):
            assert needle not in text, (path, needle)
    identity = out["run_dir"] / "private" / "identity_map.json"
    assert identity.is_file()
    assert grading not in identity.parents
    assert eb.read_json(identity)["map"][out["attempt"].name] == out["anon"]


def test_13_cli_grading_subcommands_run(tmp_path, capsys):
    prepared_outputs(tmp_path)
    root = str(tmp_path / "bench")
    assert eb.main(["prepare-grading", "--root", root, "--run", "run1"]) == 0
    assert eb.main(["diff-judgments", "--root", root, "--run", "run1"]) == 0
    assert "disputed" in capsys.readouterr().out


# --- stage 3 helpers: scoring, calibration, report ----------------------------------------


def _a(out: dict) -> dict:
    return eb.load_judgments(out["grading"], "A")


def _b(out: dict) -> dict:
    return eb.load_judgments(out["grading"], "B")


def _each_judge(judgments: dict, fn) -> dict:
    for judgment in judgments.values():
        fn(judgment)
    return judgments


def _score(out: dict, *, a=None, b=None, extraction=None, gold=None, inventory=None, adjudication=None) -> dict:
    return eb.score_output(
        out["extraction"] if extraction is None else extraction,
        out["gold"] if gold is None else gold,
        eb.DEFAULT_RUBRIC,
        out["inventory"] if inventory is None else inventory,
        _a(out) if a is None else a,
        _b(out) if b is None else b,
        {} if adjudication is None else adjudication,
    )


def _e_value(out: dict, rows: dict, *, extraction=None, a=None) -> float:
    # rows: {entity index: (match, type_ok, subtype_ok)} written to every B judge.
    def set_rows(judgment):
        for index, (match, type_ok, subtype_ok) in rows.items():
            judgment["entities"][str(index)] = {
                "match": match,
                "type_ok": type_ok,
                "subtype_ok": subtype_ok,
                "segments": ["S000"],
            }

    b = _each_judge(_b(out), set_rows)
    return _score(out, a=a, b=b, extraction=extraction)["E"]["value"]


def _write_judgment(out: dict, packet: str, judge: str, fn) -> None:
    path = out["grading"] / f"{packet}.{judge}.json"
    doc = eb.read_json(path)
    fn(doc)
    eb.write_json(path, doc)


def _human_labels(out: dict) -> dict:
    # The invented "human" agrees with the claude judge, so both judges should pass.
    labels: dict[str, str] = {}
    for packet in ("A", "B"):
        judgment = eb.load_judgments(out["grading"], packet, overlay=False)["claude"]
        for key, value in eb.judgment_items(packet, judgment).items():
            labels[f"{out['anon']}|{key}"] = value[0] if isinstance(value, tuple) else value
    return labels


def _cfg(label, q, cost=1.0, *, eligible=True, q_min=None, q_max=None) -> dict:
    return {
        "label": label,
        "q_mean": q,
        "q_min": q if q_min is None else q_min,
        "q_max": q if q_max is None else q_max,
        "eligible": eligible,
        "cost_standard": cost,
    }


# --- 3. perfect scoring and zero claim groups ------------------------------------------------


def test_03_perfect_run_scores_exactly_100(tmp_path):
    out = make_graded_run(tmp_path)
    result = _score(out)
    for component in ("F", "C", "N", "E", "G", "Q"):
        assert result[component] == {"value": 100.0, "low": 100.0, "high": 100.0}, component
    assert result["counts"] == {"contradicted": 0, "unsupported": 0, "claim_groups": 6, "entities": 3}
    assert result["open_items"] == [] and result["critical"] == [] and result["ledger"] == []


def test_03_zero_claim_groups_gives_empty_f_and_invalid_status(tmp_path):
    out = make_graded_run(tmp_path)
    inventory = copy.deepcopy(out["inventory"])
    for claim in inventory["claims"]:
        claim["kind"] = "not_claim"
    assert _score(out, inventory=inventory)["F"] == {"value": None, "low": 0.0, "high": 0.0}
    eb.write_json(out["grading"] / "inventory.json", inventory)
    report = eb.score_run(out["run_dir"], out["case_dir"], None)
    (attempt,) = report["attempts"]
    assert attempt["status"] == "invalid"
    assert attempt["scores"] is None


# --- 4. C and N ---------------------------------------------------------------------------


def test_04_present_fact_gets_c_credit_without_note_credit(tmp_path):
    out = make_graded_run(tmp_path)

    def absent(judgment):
        judgment["notes"]["N_SIEGEL"] = {"verdict": "absent", "entity_index": None, "why": "invented"}

    result = _score(out, b=_each_judge(_b(out), absent))
    assert result["C"]["value"] == 100.0
    assert result["N"]["value"] == 0.0


def test_04_present_with_non_target_index_gets_no_n_credit_and_ledger(tmp_path):
    out = make_graded_run(tmp_path)

    def wrong(judgment):
        judgment["notes"]["N_SIEGEL"] = {"verdict": "present", "entity_index": 1, "why": "invented"}

    result = _score(out, b=_each_judge(_b(out), wrong))
    assert result["N"]["value"] == 0.0
    assert {"key": "N:N_SIEGEL", "problem": "wrong_entity"} in result["ledger"]


def test_04_target_entity_not_emitted_gives_n_zero_without_verdict(tmp_path):
    out = make_graded_run(tmp_path)

    def drop(judgment):
        judgment["entities"]["0"]["match"] = "unsupported"
        del judgment["notes"]["N_SIEGEL"]

    result = _score(out, b=_each_judge(_b(out), drop))
    assert result["N"] == {"value": 0.0, "low": 0.0, "high": 0.0}
    assert "N:N_SIEGEL" not in result["open_items"]


# --- 5. F groups --------------------------------------------------------------------------


def test_05_two_claims_in_one_group_count_once(tmp_path):
    out = make_graded_run(tmp_path)
    inventory = copy.deepcopy(out["inventory"])
    claims = [c for c in inventory["claims"] if c["kind"] == "claim"]
    claims[1]["group"] = claims[0]["group"]

    def contradict(judgment):
        for claim in claims[:2]:
            judgment["claims"][claim["id"]]["verdict"] = "contradicted"

    a = _each_judge(_a(out), contradict)
    result = _score(out, a=a, inventory=inventory)
    assert result["counts"]["claim_groups"] == 5
    assert result["counts"]["contradicted"] == 1
    assert result["F"] == {"value": 80.0, "low": 80.0, "high": 80.0}


def test_05_supported_and_contradicted_groups_give_f_50(tmp_path):
    out = make_graded_run(tmp_path)
    inventory = copy.deepcopy(out["inventory"])
    claims = [c for c in inventory["claims"] if c["kind"] == "claim"]
    for claim in claims[2:]:
        claim["kind"] = "not_claim"

    def contradict(judgment):
        judgment["claims"][claims[1]["id"]]["verdict"] = "contradicted"

    result = _score(out, a=_each_judge(_a(out), contradict), inventory=inventory)
    assert result["F"]["value"] == 50.0
    assert result["counts"]["claim_groups"] == 2


def test_05_mixed_group_is_open_with_ledger(tmp_path):
    out = make_graded_run(tmp_path)
    inventory = copy.deepcopy(out["inventory"])
    claims = [c for c in inventory["claims"] if c["kind"] == "claim"]
    claims[1]["group"] = claims[0]["group"]
    for claim in claims[2:]:
        claim["kind"] = "not_claim"
    adjudication = {f"F:{claims[1]['id']}": {"verdict": "contradicted", "by": "human", "ref": "x"}}
    result = _score(out, inventory=inventory, adjudication=adjudication)
    assert result["F"] == {"value": None, "low": 0.0, "high": 100.0}
    assert {"key": f"F:{claims[0]['id']}", "problem": "mixed_group"} in result["ledger"]
    assert f"F:{claims[0]['id']}" in result["open_items"]


# --- 6. E, one assertion per case ---------------------------------------------------------

ALL_MATCHED = {
    0: ("gold:E_ALRIK", True, True),
    1: ("gold:E_BRUNHILD", True, True),
    2: ("gold:E_MUEHLE", True, True),
}


def test_06_required_entity_missing_lowers_recall(tmp_path):
    out = make_graded_run(tmp_path)
    rows = {**ALL_MATCHED, 0: ("unsupported", False, False)}
    assert _e_value(out, rows) == pytest.approx(3800 / 63, rel=1e-12)


def test_06_alias_match_counts_as_gold_identity(tmp_path):
    # The judge resolves an alias to the gold id, so the row is the same as a direct match.
    out = make_graded_run(tmp_path)
    assert _e_value(out, ALL_MATCHED) == 100.0


def test_06_optional_entity_absent_keeps_classification(tmp_path):
    out = make_graded_run(tmp_path)
    rows = {**ALL_MATCHED, 1: ("unsupported", False, False)}
    assert _e_value(out, rows) == pytest.approx(1300 / 15, rel=1e-12)


def test_06_extra_supported_counts_as_identity_and_classification(tmp_path):
    out = make_graded_run(tmp_path)
    rows = {**ALL_MATCHED, 1: ("extra_supported", True, True)}
    assert _e_value(out, rows) == 100.0


def test_06_duplicate_record_is_false_positive(tmp_path):
    out = make_graded_run(tmp_path)
    rows = {**ALL_MATCHED, 1: ("duplicate_of:0", True, True)}
    assert _e_value(out, rows) == pytest.approx(1300 / 15, rel=1e-12)


def test_06_type_ok_false_lowers_classification(tmp_path):
    out = make_graded_run(tmp_path)
    rows = {**ALL_MATCHED, 0: ("gold:E_ALRIK", False, True)}
    assert _e_value(out, rows) == pytest.approx(800 / 9, rel=1e-12)


def test_06_subtype_ok_false_lowers_classification(tmp_path):
    out = make_graded_run(tmp_path)
    rows = {**ALL_MATCHED, 2: ("gold:E_MUEHLE", True, False)}
    assert _e_value(out, rows) == pytest.approx(800 / 9, rel=1e-12)


def test_06_unsupported_record_is_false_positive(tmp_path):
    out = make_graded_run(tmp_path)
    extraction = copy.deepcopy(out["extraction"])
    extraction["entities"].append(copy.deepcopy(extraction["entities"][1]))

    def add_locator(judgment):
        judgment["locators"]["3"] = {"verdict": "supported", "segments": ["S000"], "why": "invented"}

    rows = {**ALL_MATCHED, 3: ("unsupported", False, False)}
    value = _e_value(out, rows, extraction=extraction, a=_each_judge(_a(out), add_locator))
    assert value == pytest.approx(1900 / 21, rel=1e-12)


# --- 7. G ---------------------------------------------------------------------------------


def test_07_not_supported_locator_lowers_g(tmp_path):
    out = make_graded_run(tmp_path)

    def bad(judgment):
        judgment["locators"]["0"]["verdict"] = "not_supported"

    result = _score(out, a=_each_judge(_a(out), bad))
    assert result["G"]["value"] == pytest.approx(200 / 3, rel=1e-12)


def test_07_adjudication_missing_key_names_the_item():
    verdicts = {"claude": ("gold:E_ALRIK", True, True), "codex": ("gold:E_ALRIK", True, True)}
    adjudication = {"E:0": {"match": "unsupported", "type_ok": False, "by": "human", "ref": "x"}}
    with pytest.raises(eb.BenchError, match="E:0"):
        eb.resolve("E:0", verdicts, adjudication)


# --- 8. critical rules --------------------------------------------------------------------


def test_08_critical_violation_is_listed_and_leaves_q_unchanged(tmp_path):
    out = make_graded_run(tmp_path)
    clean = _score(out)

    def violate(judgment):
        judgment["critical"]["K_SIEGEL"] = {"verdict": "violated", "spans": ["Alrik bricht"], "why": "invented"}

    dirty = _score(out, b=_each_judge(_b(out), violate))
    assert dirty["critical"] == ["K_SIEGEL"]
    assert dirty["Q"] == clean["Q"]

    for judge in ("claude", "codex"):
        _write_judgment(out, "B", judge, violate)
    report = eb.score_run(out["run_dir"], out["case_dir"], None)
    (config,) = report["configurations"]
    assert config["eligible"] is False
    assert any("critical" in reason for reason in config["why_not"])


# --- 9. judge disagreement and single judge -----------------------------------------------


def test_09_disagreement_is_open_with_bounds_and_provisional(tmp_path):
    out = make_graded_run(tmp_path)
    b = _b(out)
    b["codex"]["facts"]["F_SIEGEL"]["verdict"] = "absent"
    result = _score(out, b=b)
    assert result["C"]["value"] is None
    assert result["C"]["low"] == 25.0 and result["C"]["high"] == 100.0
    assert result["Q"]["value"] is None
    assert "C:F_SIEGEL" in result["open_items"]

    _write_judgment(out, "B", "codex", lambda doc: doc["facts"]["F_SIEGEL"].update(verdict="absent"))
    report = eb.score_run(out["run_dir"], out["case_dir"], None)
    (attempt,) = report["attempts"]
    assert attempt["status"] == "provisional"
    assert "(open)" in eb.render_report(report)


def test_09_single_judge_is_provisional(tmp_path):
    out = make_graded_run(tmp_path)
    (out["grading"] / "A.codex.json").unlink()
    (out["grading"] / "B.codex.json").unlink()
    report = eb.score_run(out["run_dir"], out["case_dir"], None)
    (attempt,) = report["attempts"]
    assert attempt["status"] == "provisional"
    assert "fewer than 2 judges" in attempt["reasons"]


def test_09_select_without_eligible_config_has_no_winner():
    selection = eb.select([_cfg("a", 100.0, eligible=False)], 2.0)
    assert selection["best_quality"] is None and selection["best_value"] is None
    assert selection["provisional"] == ["no eligible configuration"]


# --- 15. selection ------------------------------------------------------------------------


def test_15_tolerance_edge_is_inclusive_at_2_0_and_exclusive_at_2_01():
    configs = [_cfg("a", 100.0, 3.0), _cfg("b", 98.0, 2.0), _cfg("c", 97.99, 1.0)]
    selection = eb.select(configs, 2.0)
    assert selection["within_tolerance"] == ["a", "b"]
    assert selection["best_quality"] == "a"
    assert selection["best_value"] == "b"


def test_15_unknown_cost_within_tolerance_gives_no_best_value():
    selection = eb.select([_cfg("a", 100.0, None), _cfg("b", 99.0, 1.0)], 2.0)
    assert selection["best_value"] is None
    assert "cost unknown: a" in selection["provisional"]


def test_15_rank_flip_gives_reason_and_no_best_value():
    configs = [_cfg("a", 100.0, 3.0, q_min=99.5), _cfg("b", 97.0, 1.0, q_max=99.6)]
    selection = eb.select(configs, 2.0)
    assert "rank flip: b" in selection["provisional"]
    assert selection["best_value"] is None


def test_15_tie_is_listed_and_breaks_by_label_then_cost():
    selection = eb.select([_cfg("b", 100.0, 1.0), _cfg("a", 100.0, 2.0)], 2.0)
    assert selection["best_quality"] == "a"
    assert "tie: a, b" in selection["provisional"]
    assert selection["best_value"] == "b"


def test_15_best_value_ties_break_by_higher_quality():
    selection = eb.select([_cfg("a", 99.0, 1.0), _cfg("b", 100.0, 1.0)], 2.0)
    assert selection["best_value"] == "b"


# --- 16. report and unrounded scores ------------------------------------------------------


def test_16_render_is_stable_after_json_round_trip(tmp_path):
    out = make_graded_run(tmp_path)
    report = eb.score_run(out["run_dir"], out["case_dir"], None)
    markdown = eb.render_report(report)
    assert eb.render_report(json.loads(json.dumps(report))) == markdown
    assert "per dollar" not in markdown and "points/$" not in markdown
    for heading in ("## Configurations", "## Selection", "## Outputs", "## Error ledger", "## Open items", "## Limits"):
        assert heading in markdown
    assert (out["run_dir"] / "report.md").is_file() is True


def test_16_scores_are_unrounded(tmp_path):
    out = make_graded_run(tmp_path)
    gold = copy.deepcopy(out["gold"])
    gold["facts"][0]["weight"] = 2

    def absent(judgment):
        judgment["facts"]["F_SIEGEL"]["verdict"] = "absent"

    result = _score(out, gold=gold, b=_each_judge(_b(out), absent))
    assert result["C"]["value"] == 100 * 1 / 3


# --- 10. calibration ----------------------------------------------------------------------


def test_10_calibration_sample_is_deterministic_and_keeps_k_items(tmp_path):
    out = make_graded_run(tmp_path)
    first = eb.calibration_sample(out["run_dir"], out["case_dir"], seed=7, n=60, holdout=5)
    second = eb.calibration_sample(out["run_dir"], out["case_dir"], seed=7, n=60, holdout=5)
    assert first == second
    assert len(first) == 16
    assert set(first[0]) == {"item", "kind", "set", "text"}
    assert [r["item"] for r in first if r["kind"] == "K"] == [f"{out['anon']}|K:K_SIEGEL"]
    assert [r["text"] for r in first if r["kind"] == "K"] == ["Das Siegel wird nicht gebrochen."]
    assert sum(r["set"] == "holdout" for r in first) == 5


def test_10_calibrate_passes_then_fails_on_critical_miss(tmp_path):
    out = make_graded_run(tmp_path)
    eb.calibration_sample(out["run_dir"], out["case_dir"], seed=7, n=60, holdout=5)
    labels = _human_labels(out)
    passed = eb.calibrate(out["run_dir"], out["case_dir"], labels, eb.DEFAULT_RUBRIC)
    assert passed and all(result["pass"] for result in passed.values())

    labels[f"{out['anon']}|K:K_SIEGEL"] = "violated"
    failed = eb.calibrate(out["run_dir"], out["case_dir"], labels, eb.DEFAULT_RUBRIC)
    assert sum(result["critical_misses"] for result in failed.values()) == 2
    assert any(not result["pass"] for result in failed.values())


def test_10_calibrate_pools_every_graded_output(tmp_path):
    # Regression: the rating once covered only the last graded folder per judge.
    out = make_graded_run(tmp_path)
    eb.calibration_sample(out["run_dir"], out["case_dir"], seed=7, n=60, holdout=5)
    labels = _human_labels(out)
    twin = out["grading"].parent / "zzzzzzzz"
    twin.mkdir()
    for path in out["grading"].iterdir():
        (twin / path.name).write_bytes(path.read_bytes())
    wrong = next(item for item in sorted(labels) if "|F:" in item)
    labels[wrong] = "contradicted"
    results = eb.calibrate(out["run_dir"], out["case_dir"], labels, eb.DEFAULT_RUBRIC)
    assert all(wrong in result["misses"] for result in results.values())


# --- status and CLI -----------------------------------------------------------------------


def test_status_on_empty_root_does_not_raise(tmp_path):
    assert eb.status(tmp_path / "missing") == "no cases, no runs"
    assert eb.status(tmp_path) == "no cases, no runs"


def test_status_lists_the_run(tmp_path):
    make_graded_run(tmp_path)
    text = eb.status(tmp_path / "bench")
    assert "run run1" in text
    assert "open items: not scored" in text


def test_cli_score_prints_report_path(tmp_path, capsys):
    make_graded_run(tmp_path)
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({"rows": [_price()]}), encoding="utf-8")
    root = str(tmp_path / "bench")
    args = ["score", "--root", root, "--case", SESSION, "--run", "run1", "--prices", str(prices)]
    code = eb.main([*args, "--baseline", "arm-alpha"])
    assert code == 0
    printed = Path(capsys.readouterr().out.strip())
    assert printed.name == "report.md" and printed.is_file()


def test_17_full_pass_makes_no_socket_call(tmp_path, monkeypatch):
    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("network used")

    monkeypatch.setattr(socket, "socket", refuse)
    out = make_graded_run(tmp_path)
    approve(out)
    eb.calibration_sample(out["run_dir"], out["case_dir"], seed=7, n=60, holdout=5)
    eb.calibrate(out["run_dir"], out["case_dir"], _human_labels(out), eb.DEFAULT_RUBRIC)
    report = eb.score_run(out["run_dir"], out["case_dir"], None)
    (attempt,) = report["attempts"]
    assert attempt["status"] == "official", attempt["reasons"]
    assert attempt["scores"]["Q"]["value"] == 100.0
