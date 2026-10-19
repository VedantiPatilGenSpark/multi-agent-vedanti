"""Risk-scoring agent. It looks up credit, then calls the model once."""

import copy
import json

from underwriting.audit import audit_risk_reply


def _schema_without(model, *field_names: str) -> dict:
    """Copy a pack JSON schema and drop fields the model must not invent."""
    schema = copy.deepcopy(model.model_json_schema())
    required = schema.get("required", [])
    for name in field_names:
        schema.get("properties", {}).pop(name, None)
        if name in required:
            required.remove(name)
    return schema


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
