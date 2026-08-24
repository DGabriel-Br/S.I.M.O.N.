from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from simon.executive import ExecutiveDecision, decide_next
from simon.operation_proposal import (
    CognitionAnalysisRetryProposal,
    FilePatchProposal,
    FilePatchRetryProposal,
    ProcessRetryProposal,
    ProcessRunProposal,
    find_current_cognition_analysis_retry_proposal,
    find_current_file_patch_proposal,
    find_current_file_patch_retry_proposal,
    find_current_process_retry_proposal,
    find_current_process_run_proposal,
)

OperationGatePresentationStatus = Literal[
    "NOT_OPERATION_GATE",
    "PROPOSAL_REQUIRED",
    "READY_FOR_AUTHORIZATION",
    "UNSUPPORTED_GATE",
]


@dataclass(frozen=True, slots=True)
class OperationGateField:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class OperationGatePresentation:
    status: OperationGatePresentationStatus
    decision: ExecutiveDecision
    proposal_type: str | None = None
    proposal_event_id: str | None = None
    required_inputs: tuple[str, ...] = ()
    materialization_command: str | None = None
    materialization_examples: tuple[str, ...] = ()
    details: tuple[OperationGateField, ...] = ()
    authorization_examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "READY_FOR_AUTHORIZATION":
            if self.proposal_type is None or self.proposal_event_id is None:
                raise ValueError("READY_FOR_AUTHORIZATION exige proposta concreta")
            if self.required_inputs:
                raise ValueError("proposta pronta não pode declarar inputs faltantes")
        if self.status == "PROPOSAL_REQUIRED":
            if self.proposal_event_id is not None:
                raise ValueError("PROPOSAL_REQUIRED não pode apontar proposta atual")
            if not self.required_inputs or self.materialization_command is None:
                raise ValueError(
                    "PROPOSAL_REQUIRED exige inputs faltantes e comando de materialização"
                )
        if (
            self.status in {"NOT_OPERATION_GATE", "UNSUPPORTED_GATE"}
            and (self.proposal_event_id is not None or self.authorization_examples)
        ):
            raise ValueError(f"{self.status} não pode declarar aprovação disponível")


def describe_current_operation_gate(
    database_path: Path,
    *,
    goal_id: str | None = None,
) -> OperationGatePresentation:
    """Reconstrói o gate operacional atual e descreve o que falta sem mutar o estado."""
    decision = decide_next(database_path, goal_id=goal_id)
    return describe_operation_gate(database_path, decision)


def describe_operation_gate(
    database_path: Path,
    decision: ExecutiveDecision,
) -> OperationGatePresentation:
    """Descreve uma decisão de autorização e a proposta concreta correspondente, se existir."""
    if decision.outcome != "NEEDS_OPERATION_AUTHORIZATION":
        return OperationGatePresentation(status="NOT_OPERATION_GATE", decision=decision)

    if decision.operation == "plan.run" and decision.capability == "process.run":
        process_run_proposal = find_current_process_run_proposal(database_path, decision)
        return (
            _ready_process_run(decision, process_run_proposal)
            if process_run_proposal is not None
            else _proposal_required(
                decision,
                proposal_type="process.run",
                required_inputs=("executable", "arguments", "working_directory", "timeout_seconds"),
                command=_process_run_command(decision),
                materialization_examples=(
                    'Rode <executável> [args...] neste projeto',
                    'Execute <executável> [args...] neste projeto',
                ),
            )
        )

    if decision.operation == "plan.patch" and decision.capability == "file.patch":
        file_patch_proposal = find_current_file_patch_proposal(database_path, decision)
        return (
            _ready_file_patch(decision, file_patch_proposal)
            if file_patch_proposal is not None
            else _proposal_required(
                decision,
                proposal_type="file.patch",
                required_inputs=(
                    "workspace",
                    "relative_path",
                    "expected_text",
                    "replacement_text",
                ),
                command=_file_patch_command(decision),
                materialization_examples=(
                    (
                        "No arquivo <caminho>, substitua `<trecho atual>` por `<novo trecho>` "
                        "neste projeto"
                    ),
                ),
            )
        )

    if decision.operation == "process.retry":
        process_retry_proposal = find_current_process_retry_proposal(database_path, decision)
        return (
            _ready_process_retry(decision, process_retry_proposal)
            if process_retry_proposal is not None
            else _proposal_required(
                decision,
                proposal_type="process.retry",
                required_inputs=("executable", "arguments", "working_directory", "timeout_seconds"),
                command=_process_retry_command(decision),
                materialization_examples=(
                    'Rode <executável> [args...] neste projeto',
                    'Execute <executável> [args...] neste projeto',
                ),
            )
        )

    if decision.operation == "file.retry":
        file_retry_proposal = find_current_file_patch_retry_proposal(database_path, decision)
        return (
            _ready_file_retry(decision, file_retry_proposal)
            if file_retry_proposal is not None
            else _proposal_required(
                decision,
                proposal_type="file.retry",
                required_inputs=(
                    "workspace",
                    "relative_path",
                    "expected_text",
                    "replacement_text",
                ),
                command=_file_retry_command(decision),
                materialization_examples=(
                    (
                        "No arquivo <caminho>, substitua `<trecho atual>` por `<novo trecho>` "
                        "neste projeto"
                    ),
                ),
            )
        )

    if decision.operation == "analysis.retry":
        analysis_retry_proposal = find_current_cognition_analysis_retry_proposal(
            database_path,
            decision,
        )
        return (
            _ready_analysis_retry(decision, analysis_retry_proposal)
            if analysis_retry_proposal is not None
            else _proposal_required(
                decision,
                proposal_type="analysis.retry",
                required_inputs=("model",),
                command=_analysis_retry_command(decision),
                materialization_examples=(
                    "Refaça a análise com o modelo <modelo>",
                    "Tente novamente a análise com o modelo <modelo>",
                ),
            )
        )

    return OperationGatePresentation(status="UNSUPPORTED_GATE", decision=decision)


def _proposal_required(
    decision: ExecutiveDecision,
    *,
    proposal_type: str,
    required_inputs: tuple[str, ...],
    command: str,
    materialization_examples: tuple[str, ...] = (),
) -> OperationGatePresentation:
    details = _gate_context_fields(decision)
    return OperationGatePresentation(
        status="PROPOSAL_REQUIRED",
        decision=decision,
        proposal_type=proposal_type,
        required_inputs=required_inputs,
        materialization_command=command,
        materialization_examples=materialization_examples,
        details=details,
    )


def _ready_process_run(
    decision: ExecutiveDecision,
    proposal: ProcessRunProposal,
) -> OperationGatePresentation:
    return _ready(
        decision,
        proposal_type="process.run",
        proposal_event_id=proposal.event.id,
        details=(
            OperationGateField("Verificação esperada", proposal.verification),
            OperationGateField("Executável", proposal.request.executable),
            OperationGateField("argv", _format_argv(proposal.request.argv())),
            OperationGateField("Diretório", proposal.request.working_directory),
            OperationGateField("Timeout", f"{proposal.request.timeout_seconds:.3f}s"),
        ),
        authorization_examples=("sim", "autorizo", "pode executar"),
    )


def _ready_file_patch(
    decision: ExecutiveDecision,
    proposal: FilePatchProposal,
) -> OperationGatePresentation:
    return _ready(
        decision,
        proposal_type="file.patch",
        proposal_event_id=proposal.event.id,
        details=(
            OperationGateField("Capability detail", proposal.capability_detail),
            OperationGateField("Verificação esperada", proposal.verification),
            OperationGateField("Workspace", proposal.request.workspace),
            OperationGateField("Arquivo", proposal.request.relative_path),
            OperationGateField("Trecho esperado", proposal.request.expected_text),
            OperationGateField("Substituição", proposal.request.replacement_text),
        ),
        authorization_examples=("sim", "autorizo", "pode aplicar", "pode alterar"),
    )


def _ready_process_retry(
    decision: ExecutiveDecision,
    proposal: ProcessRetryProposal,
) -> OperationGatePresentation:
    return _ready(
        decision,
        proposal_type="process.retry",
        proposal_event_id=proposal.event.id,
        details=(
            OperationGateField(
                "Action anterior",
                f"{proposal.retry_of_action_id} ({proposal.previous_status})",
            ),
            OperationGateField("Verificação esperada", proposal.verification),
            OperationGateField("Executável", proposal.request.executable),
            OperationGateField("argv", _format_argv(proposal.request.argv())),
            OperationGateField("Diretório", proposal.request.working_directory),
            OperationGateField("Timeout", f"{proposal.request.timeout_seconds:.3f}s"),
        ),
        authorization_examples=("sim", "autorizo", "pode executar"),
    )


def _ready_file_retry(
    decision: ExecutiveDecision,
    proposal: FilePatchRetryProposal,
) -> OperationGatePresentation:
    return _ready(
        decision,
        proposal_type="file.retry",
        proposal_event_id=proposal.event.id,
        details=(
            OperationGateField(
                "Action anterior",
                f"{proposal.retry_of_action_id} ({proposal.previous_status})",
            ),
            OperationGateField("Capability detail", proposal.capability_detail),
            OperationGateField("Verificação esperada", proposal.verification),
            OperationGateField("Workspace", proposal.request.workspace),
            OperationGateField("Arquivo", proposal.request.relative_path),
            OperationGateField("Trecho esperado", proposal.request.expected_text),
            OperationGateField("Substituição", proposal.request.replacement_text),
        ),
        authorization_examples=("sim", "autorizo", "pode aplicar", "pode alterar"),
    )


def _ready_analysis_retry(
    decision: ExecutiveDecision,
    proposal: CognitionAnalysisRetryProposal,
) -> OperationGatePresentation:
    evidence = ", ".join(proposal.evidence_event_ids) if proposal.evidence_event_ids else "nenhuma"
    return _ready(
        decision,
        proposal_type="analysis.retry",
        proposal_event_id=proposal.event.id,
        details=(
            OperationGateField(
                "Action anterior",
                f"{proposal.retry_of_action_id} ({proposal.previous_status})",
            ),
            OperationGateField("Verificação esperada", proposal.verification),
            OperationGateField("Modelo", proposal.model),
            OperationGateField("Evidências verificadas", evidence),
        ),
        authorization_examples=("sim", "autorizo"),
    )


def _ready(
    decision: ExecutiveDecision,
    *,
    proposal_type: str,
    proposal_event_id: str,
    details: tuple[OperationGateField, ...],
    authorization_examples: tuple[str, ...],
) -> OperationGatePresentation:
    return OperationGatePresentation(
        status="READY_FOR_AUTHORIZATION",
        decision=decision,
        proposal_type=proposal_type,
        proposal_event_id=proposal_event_id,
        details=_gate_context_fields(decision) + details,
        authorization_examples=authorization_examples,
    )


def _gate_context_fields(decision: ExecutiveDecision) -> tuple[OperationGateField, ...]:
    fields = [
        OperationGateField("Motivo", decision.reason),
        OperationGateField("Goal", decision.goal_id or "nenhum"),
        OperationGateField("Plan", decision.plan_id or "nenhum"),
        OperationGateField("Step", decision.step_id or "nenhum"),
    ]
    if decision.action_id is not None:
        fields.append(OperationGateField("Action", decision.action_id))
    if decision.capability is not None:
        fields.append(OperationGateField("Capability", decision.capability))
    return tuple(fields)


def _process_run_command(decision: ExecutiveDecision) -> str:
    goal_id = decision.goal_id or "<goal_id>"
    return (
        f"uv run simon process-propose {goal_id} --cwd <diretorio> "
        "[--process-timeout <segundos>] <executavel> [args...]"
    )


def _file_patch_command(decision: ExecutiveDecision) -> str:
    goal_id = decision.goal_id or "<goal_id>"
    return (
        f"uv run simon file-propose {goal_id} --workspace <workspace> --file <arquivo> "
        '--old "<trecho atual>" --new "<substituicao>"'
    )


def _process_retry_command(decision: ExecutiveDecision) -> str:
    action_id = decision.action_id or "<action_id>"
    return (
        f"uv run simon process-retry-propose {action_id} --cwd <diretorio> "
        "[--process-timeout <segundos>] <executavel> [args...]"
    )


def _file_retry_command(decision: ExecutiveDecision) -> str:
    action_id = decision.action_id or "<action_id>"
    return (
        f"uv run simon file-retry-propose {action_id} --workspace <workspace> --file <arquivo> "
        '--old "<trecho atual>" --new "<substituicao>"'
    )


def _analysis_retry_command(decision: ExecutiveDecision) -> str:
    action_id = decision.action_id or "<action_id>"
    return f"uv run simon analysis-retry-propose --model <modelo> {action_id}"


def _format_argv(argv: tuple[str, ...]) -> str:
    return " ".join(argv)
