import importlib.util
import json
from pathlib import Path

import pytest

from underwriting.audit import RiskAuditError
from underwriting.products.contract import CreditFile
from underwriting.products.homeowners import HomeownersPack
from underwriting.products.homeowners.schemas import Application, Enrichment, Risk

ROOT = Path(__file__).parents[1]
INPUT_PATH = (
    ROOT
    / "src"
    / "underwriting"
    / "products"
    / "homeowners"
    / "fixtures"
    / "APP-APPROVE-risk-input.json"
)
EXPECTED_PATH = ROOT / "tests" / "expected_cases" / "APP-APPROVE.json"
SCRIPT_PATH = ROOT / "scripts" / "run_risk_agent.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_risk_agent", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _risk() -> Risk:
    return Risk(
        lines=[],
        score=0,
        assessment="no cited lines",
        credit=CreditFile(
            applicant_id="APP-APPROVE",
            file_status="found",
            bureau_score=740,
            delinquencies=0,
        ),
    )


def _install_adapter(monkeypatch, script):
    created = []

    class Adapter:
        def __init__(self):
            created.append(self)

    monkeypatch.setattr(script, "BedrockAdapter", Adapter, raising=False)
    monkeypatch.setattr("underwriting.model.BedrockAdapter", Adapter, raising=False)
    return created


def _install_agent(monkeypatch, script, result=None, error=None):
    calls = []

    def fake_agent(*args, **kwargs):
        calls.append((args, kwargs))
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(script, "risk_scoring_agent", fake_agent, raising=False)
    monkeypatch.setattr("underwriting.agents.risk_scoring_agent", fake_agent)
    return calls


def _attempt(args, kwargs):
    if "attempt" in kwargs:
        return kwargs["attempt"]
    return args[4]


def _arg(args, kwargs, name, index):
    if name in kwargs:
        return kwargs[name]
    return args[index]


def test_app_approve_risk_input_matches_the_expected_slice():
    fixture = json.loads(INPUT_PATH.read_text())
    expected = json.loads(EXPECTED_PATH.read_text())
    assert fixture == {
        "application": expected["application"],
        "enrichment": expected["enrichment"],
    }
    Application.model_validate(fixture["application"])
    Enrichment.model_validate(fixture["enrichment"])
    assert "cases" not in INPUT_PATH.parts


def test_script_prints_the_risk_json_and_exits_zero(monkeypatch, capsys, tmp_path):
    script = _load_script()
    created = _install_adapter(monkeypatch, script)
    risk = _risk()
    calls = _install_agent(monkeypatch, script, result=risk)
    monkeypatch.chdir(tmp_path)

    assert script.main() == 0

    assert json.loads(capsys.readouterr().out) == risk.model_dump()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert _attempt(args, kwargs) == 1
    assert _arg(args, kwargs, "adapter", 2) is created[0]
    assert isinstance(_arg(args, kwargs, "pack", 3), HomeownersPack)
    application = _arg(args, kwargs, "application", 0)
    enrichment = _arg(args, kwargs, "enrichment", 1)
    assert application.applicant_id == "APP-APPROVE"
    assert enrichment.status == "found"
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.parametrize(
    "error",
    [TimeoutError("credit lookup timed out"), RiskAuditError("score does not match")],
)
def test_script_prints_agent_errors_and_does_not_retry(monkeypatch, capsys, error):
    script = _load_script()
    _install_adapter(monkeypatch, script)
    calls = _install_agent(monkeypatch, script, error=error)

    assert script.main() != 0

    assert str(error) in capsys.readouterr().out
    assert len(calls) == 1


def test_script_prints_a_validation_error_and_skips_the_agent(monkeypatch, capsys, tmp_path):
    script = _load_script()
    _install_adapter(monkeypatch, script)
    calls = _install_agent(monkeypatch, script, result=_risk())
    bad_input = tmp_path / "bad.json"
    bad_input.write_text('{"application": {}, "enrichment": {}}')
    monkeypatch.setattr(script, "INPUT_PATH", bad_input)

    assert script.main() != 0

    assert "validation error" in capsys.readouterr().out.lower()
    assert calls == []
