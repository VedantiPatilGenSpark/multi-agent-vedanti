import importlib.util
import json
from pathlib import Path

from underwriting.model import FakeAdapter

_INPUT = (
    Path(__file__).parents[1]
    / "src"
    / "underwriting"
    / "products"
    / "homeowners"
    / "fixtures"
    / "APP-APPROVE-risk-input.json"
)


def _load():
    path = Path(__file__).parents[1] / "scripts" / "run_risk_agent.py"
    spec = importlib.util.spec_from_file_location("run_risk_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_risk_reply() -> str:
    return json.dumps(
        {
            "lines": [],
            "score": 0,
            "assessment": "no cited lines",
            "credit": {
                "applicant_id": "APP-APPROVE",
                "file_status": "no_file",
                "bureau_score": None,
                "delinquencies": None,
            },
        }
    )


def _adapter(text: str) -> FakeAdapter:
    return FakeAdapter(text=text, input_tokens=4, output_tokens=5)


def test_script_documents_the_host_without_docker():
    module = _load()
    assert "OLLAMA_HOST" in module.__doc__
    assert "http://127.0.0.1:11434" in module.__doc__


def test_prints_the_lookup_credit_and_exits_zero(capsys):
    module = _load()
    adapter = _adapter(_valid_risk_reply())
    assert module.main(adapter) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["lines"] == []
    assert printed["score"] == 0
    assert printed["assessment"] == "no cited lines"
    assert printed["credit"] == {
        "applicant_id": "APP-APPROVE",
        "file_status": "found",
        "bureau_score": 740,
        "delinquencies": 0,
    }
    assert len(adapter.calls) == 1


def test_calls_the_agent_once_with_attempt_1(monkeypatch, capsys):
    module = _load()
    calls = []
    real = module.risk_scoring_agent

    def spy(application, enrichment, adapter, pack, attempt=1):
        calls.append(attempt)
        return real(application, enrichment, adapter, pack, attempt)

    monkeypatch.setattr(module, "risk_scoring_agent", spy)
    assert module.main(_adapter(_valid_risk_reply())) == 0
    assert calls == [1]


def test_default_adapter_is_ollama(monkeypatch, capsys):
    module = _load()
    constructed = []

    class Stub:
        def __init__(self):
            constructed.append(True)

        def complete(self, prompt, json_schema):
            return _adapter(_valid_risk_reply()).complete(prompt, json_schema)

    monkeypatch.setattr(module, "OllamaAdapter", Stub)
    assert module.main() == 0
    assert constructed == [True]


def test_audit_error_prints_and_exits_nonzero_without_retry(capsys):
    module = _load()
    adapter = _adapter(
        json.dumps({"lines": [], "score": 99, "assessment": "wrong"})
    )
    assert module.main(adapter) != 0
    assert "RiskAuditError" in capsys.readouterr().out
    assert len(adapter.calls) == 1


def test_validation_error_prints_and_exits_nonzero_without_retry(capsys):
    module = _load()
    adapter = _adapter(json.dumps({"lines": [], "score": 0}))
    assert module.main(adapter) != 0
    assert "ValidationError" in capsys.readouterr().out
    assert len(adapter.calls) == 1


def test_invalid_input_prints_and_does_not_call_the_model(tmp_path, monkeypatch, capsys):
    module = _load()
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "application": {"applicant_id": "APP-APPROVE"},
                "enrichment": json.loads(_INPUT.read_text())["enrichment"],
            }
        )
    )
    monkeypatch.setattr(module, "INPUT_PATH", bad)
    adapter = _adapter(_valid_risk_reply())
    assert module.main(adapter) != 0
    assert "ValidationError" in capsys.readouterr().out
    assert adapter.calls == []


def test_timeout_prints_and_exits_nonzero_without_calling_the_model(monkeypatch, capsys):
    module = _load()
    adapter = _adapter(_valid_risk_reply())

    def time_out(self, applicant_id, attempt):
        raise TimeoutError("credit lookup timed out")

    monkeypatch.setattr(module.HomeownersPack, "credit_lookup", time_out)
    assert module.main(adapter) != 0
    assert "TimeoutError" in capsys.readouterr().out
    assert adapter.calls == []


def test_success_does_not_write_a_case_file(tmp_path, monkeypatch, capsys):
    module = _load()
    monkeypatch.chdir(tmp_path)
    assert module.main(_adapter(_valid_risk_reply())) == 0
    assert list(tmp_path.iterdir()) == []
