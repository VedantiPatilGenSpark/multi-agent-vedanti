"""Underwriting agents. Each function calls the model once for its own slice."""

import json


def intake_agent(raw_application: dict, adapter, pack):
    """Ask the model to normalize the raw fixture and return that application."""
    prompt = f"{pack.prompts['intake']}\n\n{json.dumps(raw_application)}"
    response = adapter.complete(prompt, pack.application_schema.model_json_schema())
    return pack.application_schema.model_validate_json(response.text)


_NOTE_SCHEMA = {
    "type": "object",
    "properties": {"note": {"type": "string"}},
    "required": ["note"],
}


def enrichment_agent(application, adapter, pack):
    """Look up reference data, then ask the model only for a note."""
    reference = pack.enrichment_lookup(application)
    prompt = (
        f"{pack.prompts['enrichment']}\n\n"
        f"{application.model_dump_json()}\n\n"
        f"{reference.model_dump_json()}"
    )
    response = adapter.complete(prompt, _NOTE_SCHEMA)
    note = json.loads(response.text)["note"]
    return pack.enrichment_schema.model_validate({**reference.model_dump(), "note": note})


def risk_scoring_agent(*args, **kwargs):
    raise NotImplementedError


def recommendation_agent(*args, **kwargs):
    raise NotImplementedError
