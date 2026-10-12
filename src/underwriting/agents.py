"""Underwriting agents. Each function calls the model once for its own slice."""

import json


def intake_agent(raw_application: dict, adapter, pack):
    """Ask the model to normalize the raw fixture and return that application."""
    prompt = f"{pack.prompts['intake']}\n\n{json.dumps(raw_application)}"
    response = adapter.complete(prompt, pack.application_schema.model_json_schema())
    return pack.application_schema.model_validate_json(response.text)


def enrichment_agent(*args, **kwargs):
    raise NotImplementedError


def risk_scoring_agent(*args, **kwargs):
    raise NotImplementedError


def recommendation_agent(*args, **kwargs):
    raise NotImplementedError
