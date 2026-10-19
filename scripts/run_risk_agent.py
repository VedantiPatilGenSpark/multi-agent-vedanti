"""Score one prepared homeowners case and exit.

A direct run writes deploy/metrics.log. Stdout stays the risk JSON. The
metrics file records the model, token counts, InvokeModel latency, and the
us-east-1 on-demand list price for qwen.qwen3-32b-v1:0: $0.15 per million
input tokens and $0.60 per million output tokens.
"""

import json
import time
from pathlib import Path

from pydantic import ValidationError

from underwriting.agents import risk_scoring_agent
from underwriting.audit import RiskAuditError
from underwriting.products.homeowners import HomeownersPack
from underwriting.products.homeowners.schemas import Application, Enrichment

_REPO = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    _REPO
    / "src"
    / "underwriting"
    / "products"
    / "homeowners"
    / "fixtures"
    / "APP-APPROVE-risk-input.json"
)
METRICS_PATH = _REPO / "deploy" / "metrics.log"
_INPUT_CENTS_PER_MILLION = 15
_OUTPUT_CENTS_PER_MILLION = 60


class _RecordingAdapter:
    """Remember the last model response and how long that call took."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.response = None
        self.latency_ms = None

    def complete(self, prompt: str, json_schema: dict):
        started = time.perf_counter()
        self.response = self._inner.complete(prompt, json_schema)
        self.latency_ms = int((time.perf_counter() - started) * 1000)
        return self.response


def _invoiced_cost(input_tokens: int, output_tokens: int) -> str:
    cents = (
        input_tokens * _INPUT_CENTS_PER_MILLION
        + output_tokens * _OUTPUT_CENTS_PER_MILLION
    )
    return f"{cents / 100_000_000:.8f}"


def _write_metrics(path: Path, recorder: _RecordingAdapter) -> None:
    response = recorder.response
    if response is None:
        return
    model = getattr(recorder._inner, "model", "unspecified")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"model: {model}\n"
        f"input_tokens: {response.input_tokens}\n"
        f"output_tokens: {response.output_tokens}\n"
        f"latency_ms: {recorder.latency_ms}\n"
        f"invoiced_cost_usd: {_invoiced_cost(response.input_tokens, response.output_tokens)}\n"
    )


def main(adapter=None, metrics_path: Path | None = None) -> int:
    from underwriting.model import BedrockAdapter

    recorder = _RecordingAdapter(adapter or BedrockAdapter())
    try:
        payload = json.loads(INPUT_PATH.read_text())
        application = Application.model_validate(payload["application"])
        enrichment = Enrichment.model_validate(payload["enrichment"])
        pack = HomeownersPack()
        risk = risk_scoring_agent(
            application,
            enrichment,
            recorder,
            pack,
            attempt=1,
        )
    except (TimeoutError, RiskAuditError, ValidationError) as error:
        print(error)
        return 1
    if metrics_path is not None:
        _write_metrics(metrics_path, recorder)
    print(json.dumps(risk.model_dump()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(metrics_path=METRICS_PATH))
