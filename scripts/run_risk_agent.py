"""Score the prepared APP-APPROVE homeowners case and print the risk JSON.

OLLAMA_HOST is the Ollama base URL. The default is
http://host.docker.internal:11434 so a container reaches Ollama on the host.
Set OLLAMA_HOST=http://127.0.0.1:11434 when this script runs on the host
without Docker.
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from underwriting.agents import risk_scoring_agent
from underwriting.audit import RiskAuditError
from underwriting.model import OllamaAdapter
from underwriting.products.homeowners import HomeownersPack
from underwriting.products.homeowners.schemas import Application, Enrichment

INPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "underwriting"
    / "products"
    / "homeowners"
    / "fixtures"
    / "APP-APPROVE-risk-input.json"
)


def main(adapter=None) -> int:
    """Load the test input, score it once, and return a process status."""
    adapter = adapter or OllamaAdapter()
    try:
        payload = json.loads(INPUT_PATH.read_text())
        application = Application.model_validate(payload["application"])
        enrichment = Enrichment.model_validate(payload["enrichment"])
        risk = risk_scoring_agent(
            application,
            enrichment,
            adapter,
            HomeownersPack(),
            attempt=1,
        )
    except (TimeoutError, RiskAuditError, ValidationError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 1
    print(json.dumps(risk.model_dump()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
