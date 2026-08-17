from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CapabilityId = Literal[
    "user.ask",
    "user.perform",
    "file.read",
    "file.patch",
    "process.run",
    "logs.read",
    "cognition.analyze",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    id: CapabilityId
    description: str
    available: bool


CAPABILITY_CATALOG: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        id="user.ask",
        description=(
            "Solicitar ao usuário uma informação, confirmação ou dado ausente e aguardar resposta."
        ),
        available=True,
    ),
    CapabilitySpec(
        id="user.perform",
        description=(
            "Solicitar explicitamente ao usuário que realize uma ação externa, como executar, "
            "modificar, instalar ou testar algo, e depois reporte o resultado. Não use user.ask "
            "para delegar esse tipo de ação."
        ),
        available=False,
    ),
    CapabilitySpec(
        id="file.read",
        description="Ler conteúdo de um arquivo local já identificado e autorizado.",
        available=False,
    ),
    CapabilitySpec(
        id="file.patch",
        description=(
            "Aplicar uma substituição textual localizada em arquivo UTF-8 dentro de um workspace "
            "explicitamente autorizado."
        ),
        available=True,
    ),
    CapabilitySpec(
        id="process.run",
        description="Executar um processo ou comando controlado no ambiente local.",
        available=True,
    ),
    CapabilitySpec(
        id="logs.read",
        description="Consultar registros de execução ou logs já acessíveis ao sistema.",
        available=False,
    ),
    CapabilitySpec(
        id="cognition.analyze",
        description="Analisar cognitivamente evidências já verificadas e persistidas pelo SIMON.",
        available=True,
    ),
    CapabilitySpec(
        id="unknown",
        description=(
            "Capability necessária não representada pelo catálogo atual. Use capability_detail para "
            "descrever a necessidade sem inventar uma Tool."
        ),
        available=False,
    ),
)


def available_capability_ids() -> frozenset[str]:
    return frozenset(spec.id for spec in CAPABILITY_CATALOG if spec.available)


def capability_catalog_for_model() -> list[dict[str, object]]:
    return [
        {
            "id": spec.id,
            "description": spec.description,
            "available_now": spec.available,
        }
        for spec in CAPABILITY_CATALOG
    ]
