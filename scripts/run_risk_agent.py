"""Score one prepared homeowners case and exit."""

import json
from pathlib import Path

from pydantic import ValidationError

from underwriting.agents import risk_scoring_agent
from underwriting.audit import RiskAuditError
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


def main() -> int:
    try:
        payload = json.loads(INPUT_PATH.read_text())
        application = Application.model_validate(payload["application"])
        enrichment = Enrichment.model_validate(payload["enrichment"])
        from underwriting.model import BedrockAdapter

        pack = HomeownersPack()
        risk = risk_scoring_agent(
            application,
            enrichment,
            BedrockAdapter(),
            pack,
            attempt=1,
        )
    except (TimeoutError, RiskAuditError, ValidationError) as error:
        print(error)
        return 1
    print(json.dumps(risk.model_dump()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
