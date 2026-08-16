import json
from collections.abc import Mapping
from typing import cast

import httpx
from pydantic import BaseModel, ValidationError

from simon.model_provider import (
    ModelProviderError,
    ModelResponseError,
    ModelRuntimeUnavailableError,
    StructuredModelResult,
)


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport

    def list_models(self) -> tuple[str, ...]:
        payload = self._request_json("GET", "/api/tags")
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise ModelResponseError("Ollama não retornou a lista de modelos esperada")

        names: list[str] = []
        for raw_model in raw_models:
            if not isinstance(raw_model, Mapping):
                raise ModelResponseError("Ollama retornou um modelo em formato inválido")
            model_data = cast(Mapping[str, object], raw_model)
            name = model_data.get("name")
            if not isinstance(name, str) or not name:
                raise ModelResponseError("Ollama retornou um modelo sem nome válido")
            names.append(name)

        return tuple(names)

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]:
        if not model.strip():
            raise ValueError("model não pode ser vazio")
        if not prompt.strip():
            raise ValueError("prompt não pode ser vazio")

        schema = response_model.model_json_schema()
        schema_text = json.dumps(
            schema,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        schema_instruction = (
            "Retorne somente um objeto JSON que respeite exatamente o JSON Schema a seguir. "
            f"JSON Schema: {schema_text}"
        )

        system_parts = [schema_instruction]
        if system is not None and system.strip():
            system_parts.insert(0, system.strip())

        messages = [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {"role": "user", "content": prompt},
        ]

        payload = self._request_json(
            "POST",
            "/api/chat",
            json_body={
                "model": model,
                "messages": messages,
                "stream": False,
                "think": False,
                "format": schema,
                "options": {"temperature": temperature},
            },
        )

        raw_message = payload.get("message")
        if not isinstance(raw_message, Mapping):
            raise ModelResponseError("Ollama não retornou uma mensagem válida")
        message = cast(Mapping[str, object], raw_message)
        content = message.get("content")
        if not isinstance(content, str):
            raise ModelResponseError("Ollama não retornou conteúdo textual")

        try:
            parsed = response_model.model_validate_json(content)
        except ValidationError as exc:
            detail = _validation_error_detail(exc)
            raise ModelResponseError(
                f"A resposta do modelo não respeitou o schema solicitado ({detail})"
            ) from exc

        return StructuredModelResult(
            model=_optional_str(payload.get("model")) or model,
            output=parsed,
            total_duration_ns=_optional_int(payload.get("total_duration")),
            prompt_eval_count=_optional_int(payload.get("prompt_eval_count")),
            eval_count=_optional_int(payload.get("eval_count")),
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
    ) -> dict[str, object]:
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
                trust_env=False,
            ) as client:
                response = client.request(method, path, json=json_body)
                response.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ModelRuntimeUnavailableError(
                f"Ollama indisponível em {self._base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = _extract_ollama_error(exc.response)
            raise ModelProviderError(
                f"Ollama recusou a requisição ({exc.response.status_code}): {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelProviderError(f"Falha de comunicação com Ollama: {exc}") from exc

        try:
            raw_payload = cast(object, response.json())
        except ValueError as exc:
            raise ModelResponseError("Ollama retornou JSON inválido") from exc
        if not isinstance(raw_payload, dict):
            raise ModelResponseError("Ollama retornou uma resposta em formato inválido")
        return cast(dict[str, object], raw_payload)


def _validation_error_detail(exc: ValidationError) -> str:
    errors = exc.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    )
    if not errors:
        return "violação de schema sem detalhes"

    first_error = errors[0]
    raw_location = first_error.get("loc", ())
    if isinstance(raw_location, tuple):
        location = ".".join(str(part) for part in raw_location) or "raiz"
    else:
        location = "raiz"

    message = first_error.get("msg")
    if not isinstance(message, str) or not message:
        message = "valor inválido"
    return f"{location}: {message}"


def _extract_ollama_error(response: httpx.Response) -> str:
    try:
        raw_payload = cast(object, response.json())
    except ValueError:
        return response.text.strip() or "erro sem detalhes"
    if isinstance(raw_payload, Mapping):
        payload = cast(Mapping[str, object], raw_payload)
        detail = payload.get("error")
        if isinstance(detail, str) and detail.strip():
            return detail
    return "erro sem detalhes"


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
