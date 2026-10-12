"""Pipeline harness. It is the only writer of the case and the trace."""

import time
from datetime import datetime, timezone

from pydantic import ValidationError

from underwriting.agents import (
    enrichment_agent,
    intake_agent,
    recommendation_agent,
    risk_scoring_agent,
)
from underwriting.audit import RiskAuditError
from underwriting.products.homeowners import HomeownersPack
from underwriting.trace import Trace, TraceEntry

_AGENTS = {
    "intake": "intake_agent",
    "enrichment": "enrichment_agent",
    "credit_lookup": "risk_scoring_agent",
    "risk": "risk_scoring_agent",
    "recommendation": "recommendation_agent",
}


class PipelineStepError(Exception):
    """A non-risk step returned a reply that failed schema validation."""

    def __init__(self, trace: Trace) -> None:
        self.trace = trace
        super().__init__("model reply failed schema validation")


def run_case(applicant_id: str, adapter, sleeper=lambda seconds: None):
    """Run one fixture and return the case dict and its trace."""
    pack = HomeownersPack()
    raw = pack.fixture(applicant_id)
    trace = Trace()
    case = {
        "raw_application": raw,
        "application": None,
        "enrichment": None,
        "risk": None,
        "decision": None,
        "status": "running",
        "escalation": None,
    }
    recorded = _RecordingAdapter(adapter)
    tracing_pack = _TracingPack(pack, trace)

    application = _call_model_step(
        "intake",
        lambda: intake_agent(raw, recorded, tracing_pack),
        recorded,
        trace,
        raw,
    )
    _require_nulls_stay_null(raw, application)
    case["application"] = application.model_dump()

    enrichment = _call_model_step(
        "enrichment",
        lambda: enrichment_agent(application, recorded, tracing_pack),
        recorded,
        trace,
        application.model_dump(),
    )
    case["enrichment"] = enrichment.model_dump()

    risk = _run_risk(case, application, enrichment, recorded, tracing_pack, trace, sleeper)
    if risk is None:
        return case, trace

    case["risk"] = risk.model_dump()
    decision = _call_model_step(
        "recommendation",
        lambda: recommendation_agent(application, enrichment, risk, recorded, tracing_pack),
        recorded,
        trace,
        {
            "application": application.model_dump(),
            "enrichment": enrichment.model_dump(),
            "risk": risk.model_dump(),
        },
    )
    case["decision"] = decision.model_dump()
    case["status"] = "completed"
    return case, trace


def _run_risk(case, application, enrichment, recorded, pack, trace, sleeper):
    for attempt in (1, 2):
        calls_before = len(recorded.calls)
        try:
            risk = risk_scoring_agent(
                application,
                enrichment,
                recorded,
                pack,
                attempt=attempt,
            )
        except TimeoutError:
            if attempt == 1:
                sleeper(0.2)
                continue
            _escalate(
                case,
                "credit lookup timed out after 2 attempts",
                "credit_timeout",
                2,
            )
            return None
        except (RiskAuditError, ValidationError):
            _trace_latest_model_call(
                "risk",
                {"applicant_id": application.applicant_id, "attempt": attempt},
                recorded,
                trace,
                calls_before,
            )
            _escalate(case, "risk score unusable", "unusable_score", 1)
            return None
        _trace_latest_model_call(
            "risk",
            {"applicant_id": application.applicant_id, "attempt": attempt},
            recorded,
            trace,
            calls_before,
            output=risk.model_dump(),
        )
        return risk
    return None


def _call_model_step(step, call, recorded, trace, model_input):
    calls_before = len(recorded.calls)
    try:
        result = call()
    except ValidationError as exc:
        _trace_latest_model_call(step, model_input, recorded, trace, calls_before)
        raise PipelineStepError(trace) from exc
    _trace_latest_model_call(
        step,
        model_input,
        recorded,
        trace,
        calls_before,
        output=result.model_dump(),
    )
    return result


def _trace_latest_model_call(step, model_input, recorded, trace, calls_before, output=None):
    if len(recorded.calls) == calls_before:
        return
    response, duration_ms = recorded.calls[-1]
    trace.add(
        _entry(
            step,
            model_input,
            response.text if output is None else output,
            duration_ms,
            response.input_tokens,
            response.output_tokens,
        )
    )


def _escalate(case, reason: str, source: str, attempts: int) -> None:
    case["risk"] = None
    case["decision"] = None
    case["status"] = "escalated"
    case["escalation"] = {
        "reason": reason,
        "source": source,
        "attempts": attempts,
    }


def _require_nulls_stay_null(raw: dict, application) -> None:
    dumped = application.model_dump()
    missing = dumped["missing"]
    for key, value in raw.items():
        if value is None and (dumped.get(key) is not None or key not in missing):
            raise ValueError(f"{key} must stay null and be listed in missing")


def _entry(step, model_input, output, duration_ms, input_tokens, output_tokens):
    return TraceEntry(
        step=step,
        agent=_AGENTS[step],
        input=model_input,
        output=output,
        duration_ms=duration_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


class _RecordingAdapter:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[tuple] = []

    def complete(self, prompt: str, json_schema: dict):
        started = time.perf_counter()
        response = self._inner.complete(prompt, json_schema)
        duration_ms = int((time.perf_counter() - started) * 1000)
        self.calls.append((response, duration_ms))
        return response


class _TracingPack:
    def __init__(self, pack, trace: Trace) -> None:
        self._pack = pack
        self._trace = trace

    def __getattr__(self, name):
        return getattr(self._pack, name)

    def credit_lookup(self, applicant_id: str, attempt: int):
        started = time.perf_counter()
        try:
            credit = self._pack.credit_lookup(applicant_id, attempt)
        except TimeoutError:
            self._trace.add(
                _entry(
                    "credit_lookup",
                    {"applicant_id": applicant_id, "attempt": attempt},
                    "TimeoutError",
                    int((time.perf_counter() - started) * 1000),
                    0,
                    0,
                )
            )
            raise
        self._trace.add(
            _entry(
                "credit_lookup",
                {"applicant_id": applicant_id, "attempt": attempt},
                credit.model_dump(),
                int((time.perf_counter() - started) * 1000),
                0,
                0,
            )
        )
        return credit
