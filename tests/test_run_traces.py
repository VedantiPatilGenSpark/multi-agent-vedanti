import importlib.util
import json
from pathlib import Path

from underwriting.model import FakeAdapter

_EXPECTED = Path(__file__).parent / "expected_cases"


def _script():
    path = Path(__file__).parents[1] / "scripts" / "run_traces.py"
    spec = importlib.util.spec_from_file_location("run_traces", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected(applicant_id: str) -> dict:
    return json.loads((_EXPECTED / f"{applicant_id}.json").read_text())


def _replies(expected: dict) -> list[tuple[str, int, int]]:
    if expected["risk"] is None:
        payloads = [expected["application"], {"note": expected["enrichment"]["note"]}]
    else:
        risk_reply = {key: value for key, value in expected["risk"].items() if key != "credit"}
        payloads = [
            expected["application"],
            {"note": expected["enrichment"]["note"]},
            risk_reply,
            {
                "rationale": expected["decision"]["rationale"],
                "outcome": "deny",
                "score": 99,
            },
        ]
    return [(json.dumps(payload), 11, 7) for payload in payloads]


def test_script_help_documents_ollama_host():
    module = _script()
    assert "OLLAMA_HOST" in module.__doc__
    assert "http://host.docker.internal:11434" in module.__doc__


def test_run_all_writes_cases_and_traces(tmp_path, capsys):
    module = _script()
    sleeps = []
    replies = []
    for applicant_id in module.FIXTURES:
        replies.extend(_replies(_expected(applicant_id)))
    code = module.run_all(
        FakeAdapter(replies=replies),
        lambda seconds: sleeps.append(seconds),
        tmp_path,
        _EXPECTED,
    )
    assert code == 0
    assert sleeps == [0.2, 0.2]
    for applicant_id in module.FIXTURES:
        case = json.loads((tmp_path / "cases" / f"{applicant_id}.json").read_text())
        trace = json.loads((tmp_path / "traces" / f"{applicant_id}.json").read_text())
        assert case == _expected(applicant_id)
        assert trace["applicant_id"] == applicant_id
        assert trace["entries"]
        entry_fields = {
            "step",
            "agent",
            "input",
            "output",
            "duration_ms",
            "input_tokens",
            "output_tokens",
        }
        assert entry_fields <= set(trace["entries"][0])
    output = capsys.readouterr().out
    assert "simulated cost:" in output
    assert "latency ms:" in output
    assert "stable check APP-TIMEOUT: pass" in output


def test_stable_mismatch_is_reported_and_still_written(tmp_path, capsys):
    module = _script()
    expected = _expected("APP-APPROVE")
    application = {**expected["application"], "name": "Someone Else"}
    replies = _replies(expected)
    replies[0] = (json.dumps(application), 11, 7)
    code = module.run_all(
        FakeAdapter(replies=replies),
        lambda seconds: None,
        tmp_path,
        _EXPECTED,
        ["APP-APPROVE"],
    )
    assert code == 1
    case = json.loads((tmp_path / "cases" / "APP-APPROVE.json").read_text())
    assert case["application"]["name"] == "Someone Else"
    assert "stable check APP-APPROVE: mismatch" in capsys.readouterr().out


def test_schema_mismatch_writes_the_trace_without_a_case(tmp_path, capsys):
    module = _script()
    code = module.run_all(
        FakeAdapter(replies=[(json.dumps({}), 11, 7)]),
        lambda seconds: None,
        tmp_path,
        _EXPECTED,
        ["APP-APPROVE"],
    )
    assert code == 1
    trace = json.loads((tmp_path / "traces" / "APP-APPROVE.json").read_text())
    assert [entry["step"] for entry in trace["entries"]] == ["intake"]
    assert not (tmp_path / "cases" / "APP-APPROVE.json").exists()
    assert "schema validation" in capsys.readouterr().out
