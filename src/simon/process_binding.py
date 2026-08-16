from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from simon.plans import Plan

ExecutableText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
]
ArgumentText = Annotated[str, StringConstraints(max_length=4096)]
WorkingDirectoryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
]


class ProcessRunRequest(BaseModel):
    """Entrada concreta para uma futura execução local sem interpretar texto do Plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    executable: ExecutableText = Field(
        description="Executável que deverá ser iniciado diretamente, sem shell implícito."
    )
    arguments: tuple[ArgumentText, ...] = Field(
        default_factory=tuple,
        max_length=64,
        description="Argumentos separados que serão entregues ao executável na mesma ordem.",
    )
    working_directory: WorkingDirectoryText = Field(
        description="Diretório de trabalho explícito da execução."
    )
    timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        description="Tempo máximo permitido para a futura execução, em segundos.",
    )

    def argv(self) -> tuple[str, ...]:
        return (self.executable, *self.arguments)


@dataclass(frozen=True, slots=True)
class ProcessRunBinding:
    goal_id: str
    plan_id: str
    plan_revision: int
    step_id: str
    capability: Literal["process.run"]
    verification: str
    request: ProcessRunRequest


def bind_process_run_step(
    plan: Plan,
    *,
    step_id: str,
    request: ProcessRunRequest,
) -> ProcessRunBinding:
    """Liga parâmetros explícitos a um step process.run sem inferi-los da descrição humana."""
    if plan.status != "ACTIVE":
        raise ValueError(f"binding process.run exige plan ACTIVE: {plan.id}")

    step = next((candidate for candidate in plan.steps if candidate.get("id") == step_id), None)
    if step is None:
        raise ValueError(f"passo não encontrado no plan: {step_id}")

    capability = step.get("capability")
    if capability != "process.run":
        raise ValueError(
            f"binding process.run exige capability process.run no passo {step_id}: {capability}"
        )

    kind = step.get("kind")
    if kind != "WORLD":
        raise ValueError(f"binding process.run exige passo WORLD: {step_id}")

    verification = step.get("verification")
    if not isinstance(verification, str) or not verification.strip():
        raise ValueError(f"passo process.run precisa de critério de verificação: {step_id}")

    return ProcessRunBinding(
        goal_id=plan.goal_id,
        plan_id=plan.id,
        plan_revision=plan.revision,
        step_id=step_id,
        capability="process.run",
        verification=verification.strip(),
        request=request,
    )
