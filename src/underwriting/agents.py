"""Underwriting agents. Each function calls the model once for its own slice."""

import copy
import json

from underwriting.audit import audit_risk_reply
from underwriting.products.contract import outcome_for_score


def intake_agent(raw_application: dict, adapter, pack):
    """Ask the model to normalize the raw fixture and return that application."""
    prompt = f"{pack.prompts['intake']}\n\n{json.dumps(raw_application)}"
    response = adapter.complete(prompt, pack.application_schema.model_json_schema())
    return pack.application_schema.model_validate_json(response.text)


def _schema_without(model, *field_names: str) -> dict:
    """Copy a pack JSON schema and drop fields the model must not invent."""
    schema = copy.deepcopy(model.model_json_schema())
    required = schema.get("required", [])
    for name in field_names:
        schema.get("properties", {}).pop(name, None)
        if name in required:
            required.remove(name)
    return schema


def enrichment_agent(application, adapter, pack):
    """Look up reference data, then ask the model only for the remaining fields."""
    reference = pack.enrichment_lookup(application)
    prompt = (
        f"{pack.prompts['enrichment']}\n\n"
        f"{application.model_dump_json()}\n\n"
        f"{reference.model_dump_json()}"
    )
    response = adapter.complete(
        prompt,
        _schema_without(pack.enrichment_schema, *reference.model_dump()),
    )
    note = json.loads(response.text)["note"]
    return pack.enrichment_schema.model_validate({**reference.model_dump(), "note": note})


def risk_scoring_agent(application, enrichment, adapter, pack, attempt: int = 1):
    """Look up credit first. Call the model only after a file or no_file result."""
    credit = pack.credit_lookup(application.applicant_id, attempt)
    prompt = (
        f"{pack.prompts['risk']}\n\n"
        f"{application.model_dump_json()}\n\n"
        f"{enrichment.model_dump_json()}\n\n"
        f"{credit.model_dump_json()}\n\n"
        f"{pack.rubric.model_dump_json()}"
    )
    response = adapter.complete(prompt, _schema_without(pack.risk_schema, "credit"))
    reply = json.loads(response.text)
    reply.pop("credit", None)
    audit_risk_reply(reply, pack.rubric)
    return pack.risk_schema.model_validate({**reply, "credit": credit.model_dump()})


def recommendation_agent(application, enrichment, risk, adapter, pack):
    """Choose the band outcome, then ask the model only for the rationale."""
    outcome = outcome_for_score(pack.bands, risk.score)
    prompt = (
        f"{pack.prompts['recommendation']}\n\n"
        f"outcome: {outcome}\n\n"
        f"{application.model_dump_json()}\n\n"
        f"{enrichment.model_dump_json()}\n\n"
        f"{risk.model_dump_json()}"
    )
    response = adapter.complete(
        prompt,
        _schema_without(pack.decision_schema, "outcome", "score"),
    )
    rationale = json.loads(response.text)["rationale"]
    return pack.decision_schema.model_validate(
        {"outcome": outcome, "score": risk.score, "rationale": rationale}
    )
