from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class ModelProviderError(RuntimeError):
    """Erro ao conversar com um runtime de modelo."""


class ModelRuntimeUnavailableError(ModelProviderError):
    """O runtime configurado não pôde ser alcançado."""


class ModelResponseError(ModelProviderError):
    """O runtime respondeu, mas a resposta não respeitou o contrato esperado."""


@dataclass(frozen=True, slots=True)
class StructuredModelResult[OutputT: BaseModel]:
    model: str
    output: OutputT
    total_duration_ns: int | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    repair_count: int = 0


class ModelProvider(Protocol):
    def list_models(self) -> tuple[str, ...]: ...

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]: ...
