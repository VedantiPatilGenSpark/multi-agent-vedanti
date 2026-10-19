import json

import pytest

from underwriting.agents import risk_scoring_agent
from underwriting.audit import RiskAuditError
from underwriting.model import FakeAdapter
from underwriting.products.homeowners import HomeownersPack
from underwriting.products.homeowners.schemas import (
    Application,
    CreditFile,
    Enrichment,
)


def _pack() -> HomeownersPack:
    return HomeownersPack()


def _application(applicant_id: str, state: str | None, roof_age: int | None) -> Application:
    missing = [
        name
        for name, value in (("state", state), ("roof_age", roof_age))
        if value is None
    ]
    return Application(
        applicant_id=applicant_id,
        name="Unit Tester",
        state=state,
        year_built=2000,
        roof_age=roof_age,
        construction="frame",
        coverage_amount=100000,
        prior_claims=[],
        missing=missing,
    )


def _enrichment() -> Enrichment:
    return Enrichment(
        status="unknown",
        wind_hail_band=None,
        wildfire_band=None,
        note="note",
    )


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


def test_risk_returns_a_valid_reply_unchanged_and_attaches_the_credit_file():
    pack = _pack()
    application = _application("APP-APPROVE", state="WI", roof_age=8)
    adapter = FakeAdapter(text=_valid_risk_reply(), input_tokens=4, output_tokens=5)
    risk = risk_scoring_agent(application, _enrichment(), adapter, pack, attempt=1)
    assert risk.lines == []
    assert risk.score == 0
    assert risk.assessment == "no cited lines"
    assert risk.credit == CreditFile(
        applicant_id="APP-APPROVE",
        file_status="found",
        bureau_score=740,
        delinquencies=0,
    )
    assert len(adapter.calls) == 1


def test_risk_still_calls_the_model_when_the_credit_file_is_missing():
    pack = _pack()
    application = _application("APP-DENY", state="CO", roof_age=28)
    adapter = FakeAdapter(text=_valid_risk_reply(), input_tokens=4, output_tokens=5)
    risk = risk_scoring_agent(application, _enrichment(), adapter, pack, attempt=1)
    assert risk.credit.file_status == "no_file"
    assert risk.credit.bureau_score is None
    assert risk.credit.delinquencies is None
    assert len(adapter.calls) == 1


def test_risk_unusable_arithmetic_returns_no_section_and_calls_the_model_once():
    pack = _pack()
    application = _application("APP-APPROVE", state="WI", roof_age=8)
    adapter = FakeAdapter(
        text=json.dumps(
            {
                "lines": [],
                "score": 99,
                "assessment": "wrong",
            }
        ),
        input_tokens=4,
        output_tokens=5,
    )
    with pytest.raises(RiskAuditError):
        risk_scoring_agent(application, _enrichment(), adapter, pack, attempt=1)
    assert len(adapter.calls) == 1


def test_risk_does_not_call_the_model_when_credit_lookup_times_out():
    pack = _pack()
    application = _application("APP-TIMEOUT", state="WI", roof_age=5)
    adapter = FakeAdapter(text=_valid_risk_reply(), input_tokens=4, output_tokens=5)
    with pytest.raises(TimeoutError):
        risk_scoring_agent(application, _enrichment(), adapter, pack, attempt=1)
    assert adapter.calls == []
