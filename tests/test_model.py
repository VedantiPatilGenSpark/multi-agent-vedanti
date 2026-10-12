import socket

import pytest

from underwriting.model import FakeAdapter, ModelResponse, OllamaAdapter


def test_fake_adapter_returns_the_canned_section_and_token_counts():
    adapter = FakeAdapter(text='{"score": 10}', input_tokens=11, output_tokens=7)
    schema = {"type": "object"}
    result = adapter.complete("risk prompt", schema)
    assert result == ModelResponse(
        text='{"score": 10}',
        input_tokens=11,
        output_tokens=7,
    )
    assert adapter.calls == [("risk prompt", schema)]


def test_fake_adapter_does_not_open_a_connection(monkeypatch):
    def fail_connect(self, address):
        raise AssertionError(address)

    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    result = FakeAdapter(text="{}", input_tokens=2, output_tokens=3).complete(
        "prompt",
        {"type": "object"},
    )
    assert result.text == "{}"
    assert result.input_tokens == 2
    assert result.output_tokens == 3


def test_ollama_adapter_calls_qwen_with_thinking_off(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama.test:11434")
    captured = {}
    schema = {"type": "object", "properties": {"outcome": {"type": "string"}}}

    def post(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {
            "response": '{"outcome": "approve"}',
            "prompt_eval_count": 20,
            "eval_count": 6,
        }

    result = OllamaAdapter(post=post).complete("decide", schema)
    assert captured["url"] == "http://ollama.test:11434/api/generate"
    assert captured["payload"]["model"] == "qwen3:8b"
    assert captured["payload"]["prompt"] == "decide"
    assert captured["payload"]["think"] is False
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"] is schema
    assert result == ModelResponse(
        text='{"outcome": "approve"}',
        input_tokens=20,
        output_tokens=6,
    )


def test_ollama_adapter_defaults_the_host(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    captured = {}

    def post(url, payload):
        captured["url"] = url
        return {"response": "{}", "prompt_eval_count": 1, "eval_count": 1}

    OllamaAdapter(post=post).complete("prompt", {"type": "object"})
    assert captured["url"] == "http://host.docker.internal:11434/api/generate"
