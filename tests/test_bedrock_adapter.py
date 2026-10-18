import json
import socket

import pytest

from underwriting.model import BedrockAdapter, ModelResponse

_MODEL_ID = "amazon.nova-lite-v1:0"


class _Body:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload


class _Client:
    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[dict] = []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"body": _Body(self.payload or {})}


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def fail_connect(self, address):
        raise AssertionError(address)

    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.delenv(name, raising=False)


def _reply(score: int = 14, usage: dict | None = None) -> dict:
    payload = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-1",
                            "name": "json_reply",
                            "input": {"score": score},
                        }
                    }
                ],
            }
        }
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


def _body(call: dict) -> dict:
    raw = call["body"]
    if isinstance(raw, bytes):
        raw = raw.decode()
    return json.loads(raw)


def test_bedrock_adapter_invokes_nova_lite_and_returns_the_json_object():
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    client = _Client(
        _reply(usage={"inputTokens": 11, "outputTokens": 7, "totalTokens": 18})
    )
    result = BedrockAdapter(client=client).complete("risk prompt", schema)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["modelId"] == _MODEL_ID
    body = _body(call)
    assert body["schemaVersion"] == "messages-v1"
    assert body["messages"] == [
        {"role": "user", "content": [{"text": "risk prompt"}]}
    ]
    assert body["toolConfig"]["tools"] == [
        {
            "toolSpec": {
                "name": "json_reply",
                "description": "Return a JSON object matching the schema.",
                "inputSchema": {"json": schema},
            }
        }
    ]
    assert body["toolConfig"]["toolChoice"] == {"tool": {"name": "json_reply"}}
    assert result == ModelResponse(text='{"score": 14}', input_tokens=11, output_tokens=7)


def test_bedrock_adapter_uses_zero_when_token_counts_are_missing():
    client = _Client(_reply())
    result = BedrockAdapter(client=client).complete("risk prompt", {"type": "object"})
    assert result == ModelResponse(text='{"score": 14}', input_tokens=0, output_tokens=0)


def test_bedrock_adapter_raises_the_client_error():
    client = _Client(error=RuntimeError("AccessDeniedException"))
    with pytest.raises(RuntimeError, match="AccessDeniedException"):
        BedrockAdapter(client=client).complete("risk prompt", {"type": "object"})


def test_bedrock_adapter_defaults_to_bedrock_runtime_in_us_east_1(monkeypatch):
    import underwriting.model as model

    created = []

    def client(service_name, **kwargs):
        created.append((service_name, kwargs))
        return _Client(_reply(usage={"inputTokens": 1, "outputTokens": 2}))

    monkeypatch.setattr(model.boto3, "client", client)
    result = BedrockAdapter().complete("risk prompt", {"type": "object"})
    assert created == [("bedrock-runtime", {"region_name": "us-east-1"})]
    assert result.input_tokens == 1
    assert result.output_tokens == 2
