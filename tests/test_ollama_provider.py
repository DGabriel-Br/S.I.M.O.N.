import json
from typing import Self

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, model_validator

from simon.model_provider import ModelResponseError, ModelRuntimeUnavailableError
from simon.ollama_provider import OllamaProvider


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


class SemanticOutput(BaseModel):
    answer: str

    @model_validator(mode="after")
    def reject_bad_answer(self) -> Self:
        if self.answer == "bad":
            raise ValueError("answer semanticamente inválida")
        return self


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


def test_generate_structured_repairs_invalid_model_output_once() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "model": "model-a",
                    "message": {"content": '{"answer":[]}'},
                    "total_duration": 100,
                    "prompt_eval_count": 8,
                    "eval_count": 3,
                },
            )
        return httpx.Response(
            200,
            json={
                "model": "model-a",
                "message": {"content": '{"answer":"ok"}'},
                "total_duration": 200,
                "prompt_eval_count": 10,
                "eval_count": 4,
            },
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))
    result = provider.generate_structured(
        model="model-a",
        system="system",
        prompt="question",
        response_model=ExampleOutput,
        temperature=0.7,
    )

    assert len(requests) == 2
    assert result.output.answer == "ok"
    assert result.repair_count == 1
    assert result.total_duration_ns == 300
    assert result.prompt_eval_count == 18
    assert result.eval_count == 7
    assert requests[0]["options"] == {"temperature": 0.7}
    assert requests[1]["options"] == {"temperature": 0.0}
    repair_messages = requests[1]["messages"]
    assert isinstance(repair_messages, list)
    assert len(repair_messages) == 3
    assert repair_messages[0]["role"] == "system"
    assert repair_messages[0]["content"].startswith("system\n\n")
    assert "JSON Schema:" not in repair_messages[0]["content"]
    assert "não priorize uma mudança mínima quando o erro exigir alteração estrutural" in repair_messages[0]["content"]
    assert "adicione ou reordene itens" in repair_messages[0]["content"]
    assert repair_messages[1] == {"role": "assistant", "content": '{"answer":[]}'}
    assert repair_messages[2]["role"] == "user"
    assert "Erro de validação: answer:" in repair_messages[2]["content"]
    assert "question" not in repair_messages[2]["content"]


def test_generate_structured_repairs_root_model_validation_error() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = '{"answer":"bad"}' if len(requests) == 1 else '{"answer":"good"}'
        return httpx.Response(
            200,
            json={"model": "model-a", "message": {"content": content}},
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))
    result = provider.generate_structured(
        model="model-a",
        prompt="question",
        response_model=SemanticOutput,
    )

    assert result.output.answer == "good"
    assert result.repair_count == 1
    repair_messages = requests[1]["messages"]
    assert isinstance(repair_messages, list)
    assert "raiz: Value error, answer semanticamente inválida" in repair_messages[2]["content"]



def test_generate_structured_repair_does_not_repeat_large_original_prompt() -> None:
    requests: list[dict[str, object]] = []
    original_prompt = "context-marker-" + ("x" * 20000)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = '{"answer":[]}' if len(requests) == 1 else '{"answer":"ok"}'
        return httpx.Response(
            200,
            json={"model": "model-a", "message": {"content": content}},
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))
    result = provider.generate_structured(
        model="model-a",
        system="short-system",
        prompt=original_prompt,
        response_model=ExampleOutput,
    )

    assert result.output.answer == "ok"
    assert result.repair_count == 1
    repair_messages = requests[1]["messages"]
    assert isinstance(repair_messages, list)
    serialized_repair = json.dumps(repair_messages)
    assert "context-marker-" not in serialized_repair
    assert len(serialized_repair) < len(original_prompt)


def test_generate_structured_rejects_invalid_output_after_single_repair() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={"model": "model-a", "message": {"content": '{"answer":[]}'}},
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    with pytest.raises(
        ModelResponseError,
        match=r"após 1 tentativa de reparo .*answer:",
    ):
        provider.generate_structured(
            model="model-a",
            prompt="question",
            response_model=ExampleOutput,
        )

    assert request_count == 2


def test_provider_reports_unavailable_runtime() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    with pytest.raises(ModelRuntimeUnavailableError, match="indisponível"):
        provider.list_models()
