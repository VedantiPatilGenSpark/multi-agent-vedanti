"""Run trace, simulated cost, and latency."""

from dataclasses import dataclass
from datetime import datetime, timedelta

# Dollars per 1,000,000 tokens. Change these to reprice every simulated figure.
SIMULATED_INPUT_COST_PER_MILLION = 0.10
SIMULATED_OUTPUT_COST_PER_MILLION = 0.40

_STEP_AGENTS = {
    "intake": "intake_agent",
    "enrichment": "enrichment_agent",
    "credit_lookup": "risk_scoring_agent",
    "risk": "risk_scoring_agent",
    "recommendation": "recommendation_agent",
}


@dataclass(frozen=True)
class TraceEntry:
    step: str
    agent: str
    input: object
    output: object
    duration_ms: int
    input_tokens: int
    output_tokens: int
    timestamp: str

    def __post_init__(self) -> None:
        if self.step not in _STEP_AGENTS:
            raise ValueError(f"unknown step: {self.step}")
        if self.agent != _STEP_AGENTS[self.step]:
            raise ValueError(f"agent {self.agent} does not match step {self.step}")
        if self.step == "credit_lookup" and (
            self.input_tokens != 0 or self.output_tokens != 0
        ):
            raise ValueError("credit lookup token counts must be 0")
        _require_utc_timestamp(self.timestamp)

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "agent": self.agent,
            "input": self.input,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "timestamp": self.timestamp,
        }


class Trace:
    def __init__(self) -> None:
        self.entries: list[TraceEntry] = []

    def add(self, entry: TraceEntry) -> None:
        self.entries.append(entry)


def simulated_cost(entries: list[TraceEntry]) -> float:
    input_tokens = sum(entry.input_tokens for entry in entries)
    output_tokens = sum(entry.output_tokens for entry in entries)
    return (
        (input_tokens / 1_000_000) * SIMULATED_INPUT_COST_PER_MILLION
        + (output_tokens / 1_000_000) * SIMULATED_OUTPUT_COST_PER_MILLION
    )


def latency_ms(entries: list[TraceEntry]) -> int:
    return sum(entry.duration_ms for entry in entries)


def format_trace_summary(applicant_id: str, entries: list[TraceEntry]) -> str:
    lines = [
        f"case {applicant_id}",
        f"input tokens: {_token_total(entries, 'input_tokens')}",
        f"output tokens: {_token_total(entries, 'output_tokens')}",
        f"simulated cost: {simulated_cost(entries):.6f}",
        f"latency ms: {latency_ms(entries)}",
    ]
    for step, group in _groups(entries):
        lines.append(
            f"step {step} "
            f"input tokens: {_token_total(group, 'input_tokens')} "
            f"output tokens: {_token_total(group, 'output_tokens')} "
            f"simulated cost: {simulated_cost(group):.6f} "
            f"latency ms: {latency_ms(group)}"
        )
    return "\n".join(lines)


def _groups(entries: list[TraceEntry]) -> list[tuple[str, list[TraceEntry]]]:
    order: list[str] = []
    grouped: dict[str, list[TraceEntry]] = {}
    for entry in entries:
        if entry.step not in grouped:
            order.append(entry.step)
            grouped[entry.step] = []
        grouped[entry.step].append(entry)
    return [(step, grouped[step]) for step in order]


def _token_total(entries: list[TraceEntry], field: str) -> int:
    return sum(getattr(entry, field) for entry in entries)


def _require_utc_timestamp(timestamp: str) -> None:
    text = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"timestamp must be ISO-8601 UTC: {timestamp}") from exc
    offset = parsed.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ValueError(f"timestamp must be UTC: {timestamp}")
