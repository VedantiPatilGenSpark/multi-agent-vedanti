"""Score the prepared APP-APPROVE homeowners case and print the risk JSON.

OLLAMA_HOST is the Ollama base URL. The default is
http://host.docker.internal:11434 so a container reaches Ollama on the host.
Set OLLAMA_HOST=http://127.0.0.1:11434 when this script runs on the host
without Docker.

A direct run writes deploy/metrics.log beside this repo. Stdout stays the
risk JSON. The metrics file records the model, token counts, model-call
latency, and an invoiced cost of 0. Ollama does not bill.
"""

import json
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from underwriting.agents import risk_scoring_agent
from underwriting.audit import RiskAuditError
from underwriting.model import OllamaAdapter
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
        "invoiced_cost_usd: 0\n"
    )


def main(adapter=None, metrics_path: Path | None = None) -> int:
    """Load the test input, score it once, and return a process status."""
    recorder = _RecordingAdapter(adapter or OllamaAdapter())
    try:
        payload = json.loads(INPUT_PATH.read_text())
        application = Application.model_validate(payload["application"])
        enrichment = Enrichment.model_validate(payload["enrichment"])
        risk = risk_scoring_agent(
            application,
            enrichment,
            recorder,
            HomeownersPack(),
            attempt=1,
        )
    except (TimeoutError, RiskAuditError, ValidationError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 1
    if metrics_path is not None:
        _write_metrics(metrics_path, recorder)
    print(json.dumps(risk.model_dump()))
    return 0


if __name__ == "__main__":
    sys.exit(main(metrics_path=METRICS_PATH))
