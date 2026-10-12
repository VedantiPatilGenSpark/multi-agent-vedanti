import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from underwriting.harness import PipelineStepError, run_case
from underwriting.model import FakeAdapter
from underwriting.products.homeowners import HomeownersPack

_EXPECTED_CASES = Path(__file__).parent / "expected_cases"

_TRACE_FIELDS = (
    "agent",
    "input",
    "output",
    "duration_ms",
    "input_tokens",
    "output_tokens",
)


def _pack() -> HomeownersPack:
    return HomeownersPack()


def _adapter(*payloads: dict) -> FakeAdapter:
    return FakeAdapter(replies=[(json.dumps(payload), 11, 7) for payload in payloads])


def _intake(applicant_id: str, **overrides) -> dict:
    raw = _pack().fixture(applicant_id)
    missing = [key for key, value in raw.items() if value is None]
    return {**raw, "missing": missing, **overrides}


def _success_payloads(applicant_id: str) -> list[dict]:
    return [
        _intake(applicant_id),
        {"note": "Territory note."},
        {
            "lines": [],
            "score": 0,
            "assessment": "no cited lines",
        },
        {"rationale": "Approve this case.", "outcome": "deny", "score": 99},
    ]


def _sleeper():
    calls = []

    def sleep(seconds):
        calls.append(seconds)

    return calls, sleep


def _assert_trace_fields(trace):
    assert trace.entries
    for entry in trace.entries:
        data = entry.to_dict()
        for field in _TRACE_FIELDS:
            assert field in data
        assert isinstance(data["duration_ms"], int)
        if entry.step == "credit_lookup":
            assert entry.agent == "risk_scoring_agent"
            assert entry.input_tokens == 0
            assert entry.output_tokens == 0
        else:
            assert entry.input_tokens == 11
            assert entry.output_tokens == 7


def test_app_approve_completes_with_approve():
    calls, sleep = _sleeper()
    case, trace = run_case(
        "APP-APPROVE",
        _adapter(*_success_payloads("APP-APPROVE")),
        sleeper=sleep,
    )
    assert case["status"] == "completed"
    assert case["escalation"] is None
    assert case["decision"]["outcome"] == "approve"
    assert case["decision"]["score"] == 0
    assert case["raw_application"]["roof_age"] == 8
    assert [entry.step for entry in trace.entries] == [
        "intake",
        "enrichment",
        "credit_lookup",
        "risk",
        "recommendation",
    ]
    _assert_trace_fields(trace)
    assert calls == []


def test_app_timeout_escalates_after_two_credit_attempts():
    calls, sleep = _sleeper()
    case, trace = run_case(
        "APP-TIMEOUT",
        _adapter(_intake("APP-TIMEOUT"), {"note": "Territory note."}),
        sleeper=sleep,
    )
    assert case["status"] == "escalated"
    assert case["risk"] is None
    assert case["decision"] is None
    assert case["escalation"] == {
        "reason": "credit lookup timed out after 2 attempts",
        "source": "credit_timeout",
        "attempts": 2,
    }
    assert calls == [0.2]
    credit_entries = [entry for entry in trace.entries if entry.step == "credit_lookup"]
    assert len(credit_entries) == 2
    assert [entry.input["attempt"] for entry in credit_entries] == [1, 2]
    assert "recommendation" not in [entry.step for entry in trace.entries]
    _assert_trace_fields(trace)


def test_app_retry_completes_after_one_timeout():
    calls, sleep = _sleeper()
    case, trace = run_case(
        "APP-RETRY",
        _adapter(*_success_payloads("APP-RETRY")),
        sleeper=sleep,
    )
    assert case["status"] == "completed"
    assert case["decision"]["outcome"] == "approve"
    assert calls == [0.2]
    credit_entries = [entry for entry in trace.entries if entry.step == "credit_lookup"]
    assert len(credit_entries) == 2
    assert credit_entries[0].output == "TimeoutError"
    assert credit_entries[1].output["file_status"] == "found"
    assert [entry.step for entry in trace.entries][-2:] == ["risk", "recommendation"]


def test_harness_rejects_a_guessed_null():
    guessed = _intake("APP-REFER", roof_age=8, missing=[])
    with pytest.raises(ValueError, match="roof_age"):
        run_case("APP-REFER", _adapter(guessed), sleeper=lambda seconds: None)


def test_unusable_risk_score_escalates_without_a_second_model_call():
    calls, sleep = _sleeper()
    case, trace = run_case(
        "APP-APPROVE",
        _adapter(
            _intake("APP-APPROVE"),
            {"note": "Territory note."},
            {
                "lines": [],
                "score": 99,
                "assessment": "wrong",
            },
        ),
        sleeper=sleep,
    )
    assert case["status"] == "escalated"
    assert case["risk"] is None
    assert case["decision"] is None
    assert case["escalation"] == {
        "reason": "risk score unusable",
        "source": "unusable_score",
        "attempts": 1,
    }
    assert calls == []
    assert [entry.step for entry in trace.entries] == [
        "intake",
        "enrichment",
        "credit_lookup",
        "risk",
    ]


@pytest.mark.parametrize(
    "applicant_id",
    ["APP-APPROVE", "APP-REFER", "APP-DENY", "APP-RETRY", "APP-TIMEOUT"],
)
def test_case_matches_expected_body(applicant_id):
    expected = json.loads((_EXPECTED_CASES / f"{applicant_id}.json").read_text())
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
    case, _trace = run_case(applicant_id, _adapter(*payloads), sleeper=lambda seconds: None)
    assert case == expected


def test_intake_schema_mismatch_is_traced_and_raised():
    with pytest.raises(PipelineStepError) as caught:
        run_case("APP-APPROVE", _adapter({}), sleeper=lambda seconds: None)
    assert [entry.step for entry in caught.value.trace.entries] == ["intake"]
    assert isinstance(caught.value.__cause__, ValidationError)
