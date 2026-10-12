import pytest

from underwriting.trace import (
    Trace,
    TraceEntry,
    format_trace_summary,
    latency_ms,
    simulated_cost,
)


def _entry(**overrides) -> TraceEntry:
    fields = {
        "step": "intake",
        "agent": "intake_agent",
        "input": {"applicant_id": "APP-APPROVE"},
        "output": {"missing": []},
        "duration_ms": 10,
        "input_tokens": 1000,
        "output_tokens": 500,
        "timestamp": "2026-10-11T18:00:00Z",
    }
    fields.update(overrides)
    return TraceEntry(**fields)


def _sample_entries() -> list[TraceEntry]:
    return [
        _entry(),
        _entry(
            step="credit_lookup",
            agent="risk_scoring_agent",
            input={"applicant_id": "APP-RETRY", "attempt": 1},
            output="TimeoutError",
            duration_ms=20,
            input_tokens=0,
            output_tokens=0,
        ),
        _entry(
            step="risk",
            agent="risk_scoring_agent",
            input={"applicant_id": "APP-RETRY"},
            output={"score": 10},
            duration_ms=30,
            input_tokens=2000,
            output_tokens=250,
        ),
    ]


def test_trace_appends_entries():
    trace = Trace()
    entry = _entry()
    trace.add(entry)
    assert trace.entries == [entry]


def test_trace_entry_exports_the_required_fields():
    assert set(_entry().to_dict()) == {
        "step",
        "agent",
        "input",
        "output",
        "duration_ms",
        "input_tokens",
        "output_tokens",
        "timestamp",
    }


def test_trace_entry_rejects_an_unknown_step():
    with pytest.raises(ValueError, match="step"):
        _entry(step="billing")


def test_trace_entry_rejects_an_agent_that_does_not_match_the_step():
    with pytest.raises(ValueError, match="agent"):
        _entry(step="intake", agent="risk_scoring_agent")


def test_credit_lookup_entry_uses_zero_tokens():
    entry = _entry(
        step="credit_lookup",
        agent="risk_scoring_agent",
        input={"applicant_id": "APP-TIMEOUT", "attempt": 2},
        output="TimeoutError",
        input_tokens=0,
        output_tokens=0,
    )
    assert entry.to_dict()["input_tokens"] == 0
    assert entry.to_dict()["output_tokens"] == 0


def test_credit_lookup_rejects_nonzero_tokens():
    with pytest.raises(ValueError, match="token"):
        _entry(
            step="credit_lookup",
            agent="risk_scoring_agent",
            input_tokens=1,
            output_tokens=0,
        )


@pytest.mark.parametrize(
    "timestamp",
    ["2026-10-11T18:00:00", "2026-10-11T18:00:00+05:00"],
)
def test_trace_entry_requires_a_utc_timestamp(timestamp):
    with pytest.raises(ValueError, match="timestamp"):
        _entry(timestamp=timestamp)


def test_utc_offset_timestamp_is_accepted():
    entry = _entry(timestamp="2026-10-11T18:00:00+00:00")
    assert entry.timestamp == "2026-10-11T18:00:00+00:00"


def test_simulated_cost_uses_the_lab_rates():
    assert simulated_cost(_sample_entries()) == pytest.approx(0.0006)


def test_latency_sums_duration_ms_including_a_failed_credit_attempt():
    assert latency_ms(_sample_entries()) == 60


def test_summary_labels_cost_simulated_for_the_case_and_each_step():
    assert format_trace_summary("APP-RETRY", _sample_entries()).splitlines() == [
        "case APP-RETRY",
        "input tokens: 3000",
        "output tokens: 750",
        "simulated cost: 0.000600",
        "latency ms: 60",
        "step intake input tokens: 1000 output tokens: 500 simulated cost: 0.000300 latency ms: 10",
        "step credit_lookup input tokens: 0 output tokens: 0 simulated cost: 0.000000 latency ms: 20",
        "step risk input tokens: 2000 output tokens: 250 simulated cost: 0.000300 latency ms: 30",
    ]
