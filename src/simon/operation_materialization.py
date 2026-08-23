from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from simon.process_binding import ProcessRunRequest

_PROCESS_TURN_PATTERN = re.compile(
    r"^\s*(?:rode|execute)\s+(?P<command>.+?)\s+(?:neste|nesse)\s+projeto[.!]?\s*$",
    re.IGNORECASE,
)
_UNSUPPORTED_COMMAND_TOKENS = {"&&", "||", "|", ";", "<", ">", ">>", "&"}


@dataclass(frozen=True, slots=True)
class ProcessCommandMaterialization:
    request: ProcessRunRequest
    command_text: str


class OperationMaterializationInputError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def parse_process_command_turn(
    text: str,
    *,
    working_directory: Path | None,
    timeout_seconds: float = 120.0,
) -> ProcessCommandMaterialization | None:
    """Converte somente a gramática foreground suportada em um ProcessRunRequest explícito."""
    match = _PROCESS_TURN_PATTERN.fullmatch(text)
    if match is None:
        return None
    if working_directory is None:
        raise OperationMaterializationInputError(
            "foreground_working_directory_required",
            "'neste projeto' exige um diretório foreground explícito",
        )

    command_text = match.group("command").strip()
    if not command_text:
        raise OperationMaterializationInputError(
            "process_command_required",
            "o turno reconhecido não contém um comando",
        )
    if "\n" in command_text or "\r" in command_text:
        raise OperationMaterializationInputError(
            "unsupported_process_command_syntax",
            "a materialização conversacional não aceita múltiplas linhas",
        )
    if '"' in command_text or "'" in command_text:
        raise OperationMaterializationInputError(
            "unsupported_process_command_syntax",
            "argumentos com aspas ainda exigem o comando técnico de proposta",
        )

    argv = tuple(command_text.split())
    if not argv:
        raise OperationMaterializationInputError(
            "process_command_required",
            "o turno reconhecido não contém argv materializável",
        )
    if any(token in _UNSUPPORTED_COMMAND_TOKENS for token in argv):
        raise OperationMaterializationInputError(
            "unsupported_process_command_syntax",
            "operadores de shell não são suportados porque process.run executa sem shell",
        )

    request = ProcessRunRequest(
        executable=argv[0],
        arguments=argv[1:],
        working_directory=str(working_directory.resolve()),
        timeout_seconds=timeout_seconds,
    )
    return ProcessCommandMaterialization(request=request, command_text=command_text)
