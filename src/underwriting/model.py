"""Model adapters for agent reasoning calls."""

import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import boto3

_DEFAULT_HOST = "http://host.docker.internal:11434"
_QWEN_MODEL_ID = "qwen.qwen3-32b-v1:0"


@dataclass(frozen=True)
class ModelResponse:
    text: str
    input_tokens: int
    output_tokens: int


class ModelAdapter(Protocol):
    def complete(self, prompt: str, json_schema: dict) -> ModelResponse: ...


class FakeAdapter:
    """Returns canned replies. Does not open a network connection."""

    def __init__(
        self,
        text: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        replies: list[tuple[str, int, int]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        if replies is None:
            self._replies = None
            self._response = ModelResponse(
                text=text or "",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        else:
            self._replies = list(replies)
            self._response = None

    def complete(self, prompt: str, json_schema: dict) -> ModelResponse:
        self.calls.append((prompt, json_schema))
        if self._replies is None:
            return self._response
        reply_text, reply_input_tokens, reply_output_tokens = self._replies.pop(0)
        return ModelResponse(
            text=reply_text,
            input_tokens=reply_input_tokens,
            output_tokens=reply_output_tokens,
        )


class OllamaAdapter:
    """Calls local Ollama with qwen3:8b and thinking off."""

    def __init__(self, post: Callable[[str, dict], dict] | None = None) -> None:
        self._post = post or _post_json
        host = os.environ.get("OLLAMA_HOST", _DEFAULT_HOST).rstrip("/")
        self._url = f"{host}/api/generate"

    def complete(self, prompt: str, json_schema: dict) -> ModelResponse:
        body = self._post(
            self._url,
            {
                "model": "qwen3:8b",
                "prompt": prompt,
                "stream": False,
                "think": False,
                "format": json_schema,
            },
        )
        return ModelResponse(
            text=body["response"],
            input_tokens=body["prompt_eval_count"],
            output_tokens=body["eval_count"],
        )


class BedrockAdapter:
    """Calls Bedrock InvokeModel for Qwen3 32B. Does not invent a score."""

    def __init__(self, client=None) -> None:
        self._client = client or boto3.client("bedrock-runtime", region_name="us-east-1")

    def complete(self, prompt: str, json_schema: dict) -> ModelResponse:
        response = self._client.invoke_model(
            modelId=_QWEN_MODEL_ID,
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "risk_reply", "schema": json_schema},
                    },
                }
            ),
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(response["body"].read())
        usage = payload.get("usage") or {}
        return ModelResponse(
            text=payload["choices"][0]["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode())
