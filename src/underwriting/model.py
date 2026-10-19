"""Model adapters for agent reasoning calls."""

import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

_DEFAULT_HOST = "http://host.docker.internal:11434"


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
        self.model = "qwen3:8b"
        host = os.environ.get("OLLAMA_HOST", _DEFAULT_HOST).rstrip("/")
        self._url = f"{host}/api/generate"

    def complete(self, prompt: str, json_schema: dict) -> ModelResponse:
        body = self._post(
            self._url,
            {
                "model": self.model,
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


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode())
