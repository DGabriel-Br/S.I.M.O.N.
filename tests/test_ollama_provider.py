import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from simon.model_provider import ModelResponseError, ModelRuntimeUnavailableError
from simon.ollama_provider import OllamaProvider


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


def test_list_models_reads_names_from_ollama() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "model-a:latest"},
                    {"name": "model-b:q4"},
                ]
            },
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    assert provider.list_models() == ("model-a:latest", "model-b:q4")


def test_generate_structured_sends_json_schema_and_validates_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "model-a"
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["format"] == ExampleOutput.model_json_schema()
        assert payload["options"] == {"temperature": 0.0}
        assert payload["messages"][1] == {"role": "user", "content": "question"}

        system_message = payload["messages"][0]
        assert system_message["role"] == "system"
        assert system_message["content"].startswith("system\n\n")
        assert "JSON Schema:" in system_message["content"]
        assert '"answer"' in system_message["content"]

        return httpx.Response(
            200,
            json={
                "model": "model-a",
                "message": {"role": "assistant", "content": '{"answer":"ok"}'},
                "total_duration": 100,
                "prompt_eval_count": 8,
                "eval_count": 3,
            },
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))
    result = provider.generate_structured(
        model="model-a",
        system="system",
        prompt="question",
        response_model=ExampleOutput,
    )

    assert result.model == "model-a"
    assert result.output.answer == "ok"
    assert result.total_duration_ns == 100
    assert result.prompt_eval_count == 8
    assert result.eval_count == 3


def test_generate_structured_adds_schema_instruction_without_custom_system() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        messages = payload["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "JSON Schema:" in messages[0]["content"]
        return httpx.Response(
            200,
            json={"model": "model-a", "message": {"content": '{"answer":"ok"}'}},
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    result = provider.generate_structured(
        model="model-a",
        prompt="question",
        response_model=ExampleOutput,
    )

    assert result.output.answer == "ok"


def test_generate_structured_rejects_invalid_model_output_with_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "model-a", "message": {"content": '{"answer":[]}'}},
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    with pytest.raises(ModelResponseError, match=r"schema solicitado \(answer:"):
        provider.generate_structured(
            model="model-a",
            prompt="question",
            response_model=ExampleOutput,
        )


def test_provider_reports_unavailable_runtime() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    with pytest.raises(ModelRuntimeUnavailableError, match="indisponível"):
        provider.list_models()
