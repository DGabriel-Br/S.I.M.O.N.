from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from simon import __version__
from simon.actions import interrupt_running_actions
from simon.assessment_confirmation import confirm_action_assessment
from simon.claims import set_current_claim
from simon.cognition import (
    UserInputInterpretation,
    interpret_user_input,
    propose_goal,
)
from simon.cognition_analysis import (
    execute_next_cognition_analysis,
    retry_cognition_analysis,
)
from simon.cognition_analysis_verification import assess_cognition_analysis
from simon.context import CognitiveContext, build_cognitive_context
from simon.entities import SIMON_ENTITY_ID, get_or_create_entity
from simon.events import Event, append_event
from simon.executive import ExecutiveDecision, decide_next
from simon.executive_runner import (
    ExecutiveContinueReceipt,
    ExecutiveRunReceipt,
    run_executive_once,
    run_executive_until_gate,
)
from simon.experience_memory import promote_experience_to_memory
from simon.experiences import suspend_active_experiences
from simon.file_patch import FilePatchRequest, execute_next_file_patch, retry_file_patch
from simon.file_patch_verification import verify_file_patch_state
from simon.goal_completion import complete_goal_from_assessment
from simon.goal_intake import accept_goal_proposal
from simon.goal_verification import assess_goal_outcome
from simon.goals import get_goal
from simon.memories import Memory
from simon.model_provider import ModelProvider, ModelProviderError, StructuredModelResult
from simon.ollama_provider import OllamaProvider
from simon.plan_completion import complete_verified_plan
from simon.plan_intake import materialize_plan_proposal
from simon.plan_proposal import (
    PlanProposalGateError,
    ensure_plan_proposal_allowed,
    propose_plan_for_goal,
)
from simon.process_binding import ProcessRunRequest
from simon.process_execution import execute_next_process_run, retry_process_run
from simon.process_verification import verify_process_run_execution
from simon.resume import reconstruct_resume_state
from simon.runtime_lock import RuntimeAlreadyActiveError, RuntimeLock
from simon.step_readiness import PlanReadiness, evaluate_active_plan
from simon.storage import initialize_storage
from simon.user_ask import answer_user_ask, dispatch_next_user_ask, retry_user_ask
from simon.user_ask_verification import assess_user_ask_response
from simon.user_turn import UserTurnReceipt, handle_user_turn


class ModelDiagnosticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    message: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simon",
        description="S.I.M.O.N. - Simples Inteligência, Mais Ou Menos Normal",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".simon"),
        help="diretório local usado pelo SIMON para persistência",
    )
    parser.add_argument("--version", action="version", version=f"S.I.M.O.N. {__version__}")

    commands = parser.add_subparsers(dest="command")

    resume = commands.add_parser(
        "resume",
        help="reconstrói o estado semântico persistido após reinício",
    )
    resume.add_argument(
        "goal_id",
        nargs="?",
        help="Goal a detalhar; se houver apenas um Goal aberto, ele é selecionado automaticamente",
    )

    executive_next = commands.add_parser(
        "executive-next",
        help="decide deterministicamente a próxima operação legítima sem executá-la",
    )
    executive_next.add_argument(
        "goal_id",
        nargs="?",
        help="Goal foreground; se houver somente um Goal aberto, ele é selecionado automaticamente",
    )

    executive_step = commands.add_parser(
        "executive-step",
        help="executa no máximo uma decisão PROCEED segura e para para reavaliar o estado",
    )
    executive_step.add_argument(
        "--model",
        help="modelo local usado somente quando a próxima decisão exigir cognição",
    )
    executive_step.add_argument(
        "goal_id",
        nargs="?",
        help="Goal foreground; se houver somente um Goal aberto, ele é selecionado automaticamente",
    )
    _add_ollama_arguments(executive_step)

    executive_continue = commands.add_parser(
        "executive-continue",
        help="avança por operações PROCEED seguras até o primeiro gate ou limite",
    )
    executive_continue.add_argument(
        "--model",
        help="modelo local reutilizado enquanto decisões cognitivas PROCEED forem encontradas",
    )
    executive_continue.add_argument(
        "--max-transitions",
        type=int,
        default=32,
        help="limite de transições seguras executadas em uma única chamada (padrão: 32)",
    )
    executive_continue.add_argument(
        "goal_id",
        nargs="?",
        help="Goal foreground; se houver somente um Goal aberto, ele é selecionado automaticamente",
    )
    _add_ollama_arguments(executive_continue)

    user_turn = commands.add_parser(
        "user-turn",
        help="registra um turno humano e roteia intents naturais explicitamente suportados",
    )
    user_turn.add_argument(
        "--goal-id",
        help="Goal foreground explícito; se omitido, o Executive aplica sua regra normal de foco",
    )
    user_turn.add_argument(
        "--model",
        help="modelo local usado somente por operações cognitivas seguras do Executive",
    )
    user_turn.add_argument(
        "--max-transitions",
        type=int,
        default=32,
        help="limite de transições seguras executadas pelo turno (padrão: 32)",
    )
    user_turn.add_argument(
        "text",
        nargs="+",
        help="texto literal do turno humano, por exemplo: continue esse Goal",
    )
    _add_ollama_arguments(user_turn)

    model_check = commands.add_parser(
        "model-check",
        help="verifica o runtime Ollama e lista modelos locais instalados",
    )
    _add_ollama_arguments(model_check)

    model_test = commands.add_parser(
        "model-test",
        help="executa uma chamada estruturada de diagnóstico em um modelo local",
    )
    model_test.add_argument("--model", required=True, help="nome do modelo já instalado no Ollama")
    _add_ollama_arguments(model_test)

    interpret = commands.add_parser(
        "interpret",
        help="interpreta uma entrada do usuário usando structured output",
    )
    interpret.add_argument("--model", required=True, help="nome do modelo já instalado no Ollama")
    interpret.add_argument("text", nargs="+", help="texto que será interpretado")
    _add_ollama_arguments(interpret)

    goal_propose = commands.add_parser(
        "goal-propose",
        help="formula uma proposta de Goal a partir de uma solicitação sem persistir o Goal",
    )
    goal_propose.add_argument(
        "--model",
        required=True,
        help="nome do modelo já instalado no Ollama",
    )
    goal_propose.add_argument("text", nargs="+", help="solicitação usada para formular o Goal")
    _add_ollama_arguments(goal_propose)

    goal_accept = commands.add_parser(
        "goal-accept",
        help="aceita explicitamente uma proposta registrada e persiste um Goal USER",
    )
    goal_accept.add_argument(
        "proposal_event_id",
        help="ID do Event cognition.goal_proposal.completed que será aceito",
    )

    goal_assess = commands.add_parser(
        "goal-assess",
        help="avalia semanticamente se as evidências de um Plan concluído satisfazem o Goal",
    )
    goal_assess.add_argument(
        "--model",
        required=True,
        help="nome do modelo já instalado no Ollama",
    )
    goal_assess.add_argument("goal_id", help="ID do Goal ACTIVE que será avaliado")
    _add_ollama_arguments(goal_assess)

    goal_complete = commands.add_parser(
        "goal-complete",
        help="confirma um assessment SATISFIED e conclui o Goal",
    )
    goal_complete.add_argument(
        "assessment_verification_id",
        help="ID da Verification goal.semantic ASSESSED que será confirmada",
    )

    experience_remember = commands.add_parser(
        "experience-remember",
        help="promove explicitamente significado de uma Experience CLOSED para Memory",
    )
    experience_remember.add_argument(
        "experience_id",
        help="ID da Experience CLOSED usada como proveniência",
    )
    experience_remember.add_argument(
        "--kind",
        required=True,
        choices=("EPISODIC", "SEMANTIC", "PROCEDURAL", "META"),
        help="tipo explícito da Memory",
    )
    experience_remember.add_argument(
        "--scope",
        required=True,
        choices=("GLOBAL", "PROJECT", "WORKSPACE", "SESSION", "PRIVATE", "SYSTEM", "LAB"),
        help="escopo explícito da Memory",
    )
    experience_remember.add_argument(
        "--entity-id",
        action="append",
        default=[],
        help="Entity relacionada; pode ser repetido",
    )
    experience_remember.add_argument(
        "--claim-id",
        action="append",
        default=[],
        help="Claim de origem adicional; pode ser repetido",
    )
    experience_remember.add_argument(
        "content",
        nargs="+",
        help="significado que o usuário decidiu preservar",
    )

    plan_propose = commands.add_parser(
        "plan-propose",
        help="formula uma proposta cognitiva de Plan para um Goal autorizado",
    )
    plan_propose.add_argument(
        "--model",
        required=True,
        help="nome do modelo já instalado no Ollama",
    )
    plan_propose.add_argument("goal_id", help="ID do Goal autorizado que será planejado")
    _add_ollama_arguments(plan_propose)

    plan_materialize = commands.add_parser(
        "plan-materialize",
        help="materializa uma proposta registrada como revisão persistente de Plan",
    )
    plan_materialize.add_argument(
        "proposal_event_id",
        help="ID do Event cognition.plan_proposal.completed que será materializado",
    )

    plan_next = commands.add_parser(
        "plan-next",
        help="avalia deterministicamente o próximo step executável de um Plan ativo",
    )
    plan_next.add_argument(
        "goal_id",
        help="ID do Goal cujo Plan ativo será avaliado",
    )

    plan_complete = commands.add_parser(
        "plan-complete",
        help="conclui um Plan somente quando todos os seus steps estão VERIFIED",
    )
    plan_complete.add_argument(
        "goal_id",
        help="ID do Goal cujo Plan ativo será concluído",
    )

    plan_ask = commands.add_parser(
        "plan-ask",
        help="cria a próxima Action user.ask e aguarda uma resposta do usuário",
    )
    plan_ask.add_argument(
        "goal_id",
        help="ID do Goal cujo próximo step user.ask será iniciado",
    )

    plan_run = commands.add_parser(
        "plan-run",
        help="executa o próximo step process.run READY do Plan ativo",
    )
    plan_run.add_argument(
        "goal_id",
        help="ID do Goal cujo próximo step process.run será executado",
    )
    plan_run.add_argument(
        "--cwd",
        required=True,
        help="diretório de trabalho explícito da execução",
    )
    plan_run.add_argument(
        "--process-timeout",
        type=float,
        default=120.0,
        help="timeout do processo em segundos",
    )
    plan_run.add_argument(
        "executable",
        help="executável iniciado diretamente, sem shell implícito",
    )
    plan_run.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        help="argumentos entregues diretamente ao executável",
    )

    process_retry = commands.add_parser(
        "process-retry",
        help="autoriza nova tentativa process.run após falha ou interrupção operacional",
    )
    process_retry.add_argument(
        "action_id",
        help="ID da tentativa process.run FAILED ou INTERRUPTED que será revisada",
    )
    process_retry.add_argument(
        "--cwd",
        required=True,
        help="diretório de trabalho explícito da nova tentativa",
    )
    process_retry.add_argument(
        "--process-timeout",
        type=float,
        default=120.0,
        help="timeout da nova tentativa em segundos",
    )
    process_retry.add_argument(
        "executable",
        help="executável iniciado diretamente, sem shell implícito",
    )
    process_retry.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        help="argumentos entregues diretamente ao executável na nova tentativa",
    )

    plan_patch = commands.add_parser(
        "plan-patch",
        help="resolve explicitamente um CHANGE/unknown com uma alteração textual localizada",
    )
    plan_patch.add_argument(
        "goal_id",
        help="ID do Goal cujo próximo CHANGE/unknown será modificado",
    )
    plan_patch.add_argument(
        "--workspace",
        required=True,
        help="diretório raiz autorizado para a modificação",
    )
    plan_patch.add_argument(
        "--file",
        required=True,
        dest="relative_path",
        help="caminho relativo do arquivo dentro do workspace",
    )
    plan_patch.add_argument(
        "--old",
        required=True,
        dest="expected_text",
        help="trecho UTF-8 que precisa existir exatamente uma vez",
    )
    plan_patch.add_argument(
        "--new",
        required=True,
        dest="replacement_text",
        help="trecho UTF-8 substituto; use uma string vazia para remoção",
    )

    file_retry = commands.add_parser(
        "file-retry",
        help="autoriza nova tentativa file.patch após falha ou interrupção operacional",
    )
    file_retry.add_argument(
        "action_id",
        help="ID da tentativa file.patch FAILED ou INTERRUPTED que será revisada",
    )
    file_retry.add_argument(
        "--workspace",
        required=True,
        help="diretório raiz autorizado para a nova tentativa",
    )
    file_retry.add_argument(
        "--file",
        required=True,
        dest="relative_path",
        help="caminho relativo do arquivo dentro do workspace",
    )
    file_retry.add_argument(
        "--old",
        required=True,
        dest="expected_text",
        help="trecho UTF-8 que precisa existir exatamente uma vez na nova tentativa",
    )
    file_retry.add_argument(
        "--new",
        required=True,
        dest="replacement_text",
        help="trecho UTF-8 substituto; use uma string vazia para remoção",
    )

    plan_analyze = commands.add_parser(
        "plan-analyze",
        help="executa o próximo step cognition.analyze READY do Plan ativo",
    )
    plan_analyze.add_argument(
        "--model",
        required=True,
        help="nome do modelo já instalado no Ollama",
    )
    plan_analyze.add_argument(
        "goal_id",
        help="ID do Goal cujo próximo step cognition.analyze será executado",
    )
    _add_ollama_arguments(plan_analyze)

    analysis_retry = commands.add_parser(
        "analysis-retry",
        help="autoriza nova tentativa cognition.analyze após falha ou interrupção operacional",
    )
    analysis_retry.add_argument(
        "--model",
        required=True,
        help="nome do modelo já instalado no Ollama",
    )
    analysis_retry.add_argument(
        "action_id",
        help="ID da tentativa cognition.analyze FAILED ou INTERRUPTED que será revisada",
    )
    _add_ollama_arguments(analysis_retry)

    analysis_assess = commands.add_parser(
        "analysis-assess",
        help="avalia semanticamente uma Action cognition.analyze concluída",
    )
    analysis_assess.add_argument(
        "--model",
        required=True,
        help="nome do modelo já instalado no Ollama",
    )
    analysis_assess.add_argument(
        "action_id",
        help="ID da Action cognition.analyze COMPLETED",
    )
    _add_ollama_arguments(analysis_assess)

    process_verify = commands.add_parser(
        "process-verify",
        help="verifica objetivamente a evidência técnica de uma Action process.run concluída",
    )
    process_verify.add_argument(
        "action_id",
        help="ID da Action process.run COMPLETED que será verificada",
    )

    file_verify = commands.add_parser(
        "file-verify",
        help="verifica objetivamente o estado atual produzido por uma Action file.patch",
    )
    file_verify.add_argument(
        "action_id",
        help="ID da Action file.patch COMPLETED que será verificada",
    )

    action_answer = commands.add_parser(
        "action-answer",
        help="registra a resposta do usuário para uma Action user.ask em espera",
    )
    action_answer.add_argument("action_id", help="ID da Action user.ask em WAITING")
    action_answer.add_argument("text", nargs="+", help="resposta fornecida pelo usuário")

    action_assess = commands.add_parser(
        "action-assess",
        help="avalia semanticamente se a resposta user.ask satisfaz o critério do step",
    )
    action_assess.add_argument(
        "--model",
        required=True,
        help="nome do modelo já instalado no Ollama",
    )
    action_assess.add_argument("action_id", help="ID da Action user.ask COMPLETED")
    _add_ollama_arguments(action_assess)

    action_retry = commands.add_parser(
        "action-retry",
        help="autoriza explicitamente uma nova tentativa user.ask após review negativo",
    )
    action_retry.add_argument(
        "action_id",
        help="ID da tentativa user.ask anterior que será revisada",
    )
    action_retry.add_argument(
        "text",
        nargs="*",
        help="prompt refinado opcional; se omitido, reutiliza a solicitação anterior",
    )

    verification_confirm = commands.add_parser(
        "verification-confirm",
        help="confirma explicitamente um assessment de Action SATISFIED como VERIFIED",
    )
    verification_confirm.add_argument(
        "assessment_verification_id",
        help="ID do VerificationResult ASSESSED que será confirmado",
    )

    return parser


def _add_ollama_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ollama-url",
        default="http://127.0.0.1:11434",
        help="URL local da API do Ollama",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="timeout da chamada ao runtime em segundos",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_dir = args.data_dir.resolve()
    try:
        with RuntimeLock(data_dir):
            return _run_locked(args, data_dir)
    except RuntimeAlreadyActiveError as exc:
        print(f"Runtime: ocupado ({exc})")
        return 2


def _run_locked(args: argparse.Namespace, data_dir: Path) -> int:
    database_path, schema_version = initialize_storage(data_dir)
    suspend_active_experiences(database_path)
    interrupt_running_actions(database_path)

    simon_entity = get_or_create_entity(
        database_path,
        entity_id=SIMON_ENTITY_ID,
        kind="system",
        name="SIMON",
        aliases=("S.I.M.O.N.",),
    )

    startup_event = Event.create(
        kind="system.started",
        source="system",
        payload={"version": __version__, "schema_version": schema_version},
        related_entity_ids=(simon_entity.id,),
    )
    append_event(database_path, startup_event)

    set_current_claim(
        database_path,
        subject_id=simon_entity.id,
        predicate="storage.schema_version",
        value=schema_version,
        epistemic_status="DIRECT_OBSERVATION",
        evidence_event_ids=(startup_event.id,),
        valid_from=startup_event.occurred_at,
    )

    if args.command == "resume":
        return _resume(database_path, args.goal_id)
    if args.command == "executive-next":
        return _executive_next(database_path, args.goal_id)
    if args.command == "executive-step":
        return _executive_step(
            database_path,
            args.goal_id,
            args.ollama_url,
            args.timeout,
            args.model,
        )
    if args.command == "executive-continue":
        return _executive_continue(
            database_path,
            args.goal_id,
            args.ollama_url,
            args.timeout,
            args.model,
            args.max_transitions,
        )
    if args.command == "user-turn":
        return _user_turn(
            database_path,
            " ".join(args.text),
            args.goal_id,
            args.ollama_url,
            args.timeout,
            args.model,
            args.max_transitions,
        )
    if args.command == "model-check":
        return _model_check(args.ollama_url, args.timeout)
    if args.command == "model-test":
        return _model_test(args.ollama_url, args.timeout, args.model)
    if args.command == "interpret":
        return _interpret(
            database_path,
            args.ollama_url,
            args.timeout,
            args.model,
            " ".join(args.text),
        )
    if args.command == "goal-propose":
        return _goal_propose(
            database_path,
            args.ollama_url,
            args.timeout,
            args.model,
            " ".join(args.text),
        )
    if args.command == "goal-accept":
        return _goal_accept(database_path, args.proposal_event_id)
    if args.command == "goal-assess":
        return _goal_assess(
            database_path,
            args.ollama_url,
            args.timeout,
            args.model,
            args.goal_id,
        )
    if args.command == "goal-complete":
        return _goal_complete(database_path, args.assessment_verification_id)
    if args.command == "experience-remember":
        return _experience_remember(
            database_path,
            args.experience_id,
            args.kind,
            args.scope,
            " ".join(args.content),
            tuple(args.entity_id),
            tuple(args.claim_id),
        )
    if args.command == "plan-propose":
        return _plan_propose(
            database_path,
            args.ollama_url,
            args.timeout,
            args.model,
            args.goal_id,
        )
    if args.command == "plan-materialize":
        return _plan_materialize(database_path, args.proposal_event_id)
    if args.command == "plan-next":
        return _plan_next(database_path, args.goal_id)
    if args.command == "plan-complete":
        return _plan_complete(database_path, args.goal_id)
    if args.command == "plan-ask":
        return _plan_ask(database_path, args.goal_id)
    if args.command == "plan-run":
        return _plan_run(
            database_path,
            args.goal_id,
            args.executable,
            args.arguments,
            args.cwd,
            args.process_timeout,
        )
    if args.command == "process-retry":
        return _process_retry(
            database_path,
            args.action_id,
            args.executable,
            args.arguments,
            args.cwd,
            args.process_timeout,
        )
    if args.command == "plan-patch":
        return _plan_patch(
            database_path,
            args.goal_id,
            args.workspace,
            args.relative_path,
            args.expected_text,
            args.replacement_text,
        )
    if args.command == "file-retry":
        return _file_retry(
            database_path,
            args.action_id,
            args.workspace,
            args.relative_path,
            args.expected_text,
            args.replacement_text,
        )
    if args.command == "plan-analyze":
        return _plan_analyze(
            database_path,
            args.ollama_url,
            args.timeout,
            args.model,
            args.goal_id,
        )
    if args.command == "analysis-retry":
        return _analysis_retry(
            database_path,
            args.ollama_url,
            args.timeout,
            args.model,
            args.action_id,
        )
    if args.command == "analysis-assess":
        return _analysis_assess(
            database_path,
            args.ollama_url,
            args.timeout,
            args.model,
            args.action_id,
        )
    if args.command == "process-verify":
        return _process_verify(database_path, args.action_id)
    if args.command == "file-verify":
        return _file_verify(database_path, args.action_id)
    if args.command == "action-answer":
        return _action_answer(database_path, args.action_id, " ".join(args.text))
    if args.command == "action-assess":
        return _action_assess(
            database_path,
            args.ollama_url,
            args.timeout,
            args.model,
            args.action_id,
        )
    if args.command == "action-retry":
        prompt = " ".join(args.text) if args.text else None
        return _action_retry(database_path, args.action_id, prompt)
    if args.command == "verification-confirm":
        return _verification_confirm(database_path, args.assessment_verification_id)

    print(f"S.I.M.O.N. {__version__}")
    print(f"Dados: {database_path.parent}")
    print(f"SQLite: pronto (schema {schema_version})")
    return 0


def _executive_step(
    database_path: Path,
    goal_id: str | None,
    base_url: str,
    timeout_seconds: float,
    model: str | None,
) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds) if model else None
    try:
        receipt = run_executive_once(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Executive runner: falha ({exc})")
        return 1

    _print_executive_run_receipt(receipt)
    if receipt.status == "FAILED":
        return 1
    if receipt.status == "MODEL_REQUIRED":
        return 2
    return 0



def _executive_continue(
    database_path: Path,
    goal_id: str | None,
    base_url: str,
    timeout_seconds: float,
    model: str | None,
    max_transitions: int,
) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds) if model else None
    try:
        receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Executive continue: falha ({exc})")
        return 1

    _print_executive_continue_receipt(receipt)
    if receipt.status == "FAILED":
        return 1
    if receipt.status == "MODEL_REQUIRED":
        return 2
    return 0


def _user_turn(
    database_path: Path,
    text: str,
    goal_id: str | None,
    base_url: str,
    timeout_seconds: float,
    model: str | None,
    max_transitions: int,
) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds) if model else None
    try:
        receipt = handle_user_turn(
            database_path,
            text,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"User turn: falha ({exc})")
        return 1

    _print_user_turn_receipt(receipt)
    if receipt.status == "FAILED":
        return 1
    if receipt.status == "UNSUPPORTED":
        return 2
    if (
        receipt.executive_receipt is not None
        and receipt.executive_receipt.status == "MODEL_REQUIRED"
    ):
        return 2
    return 0


def _print_user_turn_receipt(receipt: UserTurnReceipt) -> None:
    print(f"User turn: {receipt.status}")
    print(f"Turn Event: {receipt.turn_event.id}")
    print(f"Intent: {receipt.intent or 'não suportado'}")
    print(f"Routing Event: {receipt.routing_event.id}")
    if receipt.effect_type is not None and receipt.effect_id is not None:
        print(f"Efeito do gate: {receipt.effect_type} {receipt.effect_id}")

    if receipt.status == "ROUTED" and receipt.executive_receipt is None:
        raise RuntimeError("turno ROUTED sem resultado do Executive")
    if receipt.status == "ROUTED" and receipt.executive_receipt is not None:
        _print_executive_continue_receipt(receipt.executive_receipt)
    elif receipt.status == "UNSUPPORTED":
        print("Execução: não realizada; o gateway natural ainda não suporta esse intent")
    else:
        print(f"Execução: falhou ao rotear o turno ({receipt.error})")


def _print_executive_continue_receipt(receipt: ExecutiveContinueReceipt) -> None:
    print(f"Executive continue: {receipt.status}")
    print(f"Transições executadas: {receipt.transitions_executed}")
    for index, transition in enumerate(receipt.transitions, start=1):
        print(
            f"{index}. {transition.executed_operation} -> "
            f"{transition.result_type} {transition.result_id}"
        )

    print("Decisão final:")
    _print_executive_decision(receipt.final_decision)
    if receipt.status == "MODEL_REQUIRED":
        print("Parada: informe --model para continuar a decisão cognitiva")
    elif receipt.status == "LIMIT_REACHED":
        print("Parada: limite de transições seguras atingido; execute novamente para continuar")
    elif receipt.status == "FAILED":
        print(f"Parada: execução falhou ({receipt.error})")
    elif receipt.status == "DONE":
        print("Parada: Goal concluído")
    else:
        print("Parada: o próximo estado exige um gate externo ao condutor")

def _print_executive_run_receipt(receipt: ExecutiveRunReceipt) -> None:
    print(f"Executive runner: {receipt.status}")
    print("Decisão avaliada:")
    _print_executive_decision(receipt.decision)
    if receipt.status == "EXECUTED":
        print(f"Operação executada: {receipt.executed_operation}")
        print(f"Resultado: {receipt.result_type} {receipt.result_id}")
        print("Próxima decisão, não executada:")
        if receipt.next_decision is None:
            raise RuntimeError("runner EXECUTED sem próxima decisão reconstruída")
        _print_executive_decision(receipt.next_decision)
    elif receipt.status == "MODEL_REQUIRED":
        print("Execução: não realizada; informe --model para esta decisão cognitiva")
    elif receipt.status == "FAILED":
        print(f"Execução: falhou ({receipt.error})")
    else:
        print("Execução: não realizada; a decisão atual exige um gate externo ao runner")


def _executive_next(database_path: Path, goal_id: str | None) -> int:
    try:
        decision = decide_next(database_path, goal_id=goal_id)
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Executive: falha ({exc})")
        return 1

    _print_executive_decision(decision)
    return 0


def _print_executive_decision(decision: ExecutiveDecision) -> None:
    print(f"Executive: {decision.outcome}")
    print(f"Razão: {decision.reason_code} | {decision.reason}")
    print(f"Operação: {decision.operation or 'nenhuma'}")
    print(f"Requer modelo: {'sim' if decision.requires_model else 'não'}")
    print(f"Goal: {decision.goal_id or 'nenhum'}")
    print(f"Plan: {decision.plan_id or 'nenhum'}")
    print(f"Step: {decision.step_id or 'nenhum'}")
    print(f"Action: {decision.action_id or 'nenhuma'}")
    print(f"Verification: {decision.verification_id or 'nenhuma'}")
    print(f"Proposta de Plan: {decision.proposal_event_id or 'nenhuma'}")
    print(f"Capability: {decision.capability or 'nenhuma'}")

    if decision.goal_candidates:
        print("Goals candidatos:")
        for candidate in decision.goal_candidates:
            print(f"- {candidate.goal_id}: {candidate.status} | {candidate.title}")

    if decision.blockers:
        print("Blockers preservados:")
        for blocker in decision.blockers:
            print(f"- {blocker.kind}: {blocker.detail}")


def _resume(database_path: Path, goal_id: str | None) -> int:
    try:
        overview = reconstruct_resume_state(database_path, goal_id=goal_id)
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Retomada: falha ({exc})")
        return 1

    print(f"World revision atual: {overview.current_world_revision}")
    if overview.open_goals:
        print(f"Goals abertos: {len(overview.open_goals)}")
        for goal in overview.open_goals:
            print(f"- {goal.id}: {goal.status} | {goal.title}")
    else:
        print("Goals abertos: nenhum")

    state = overview.selected
    if state is None:
        if len(overview.open_goals) > 1 and goal_id is None:
            print("Goal selecionado: nenhum (informe um goal_id para detalhar)")
        else:
            print("Goal selecionado: nenhum")
        if overview.latest_experience is not None:
            experience = overview.latest_experience
            print(f"Última Experience: {experience.id} | {experience.status}")
            if experience.outcome is not None:
                print(f"Outcome: {experience.outcome}")
        else:
            print("Última Experience: nenhuma")
        _print_resume_memories(overview.memories)
        return 0

    print(f"Goal selecionado: {state.goal.id} | {state.goal.status}")
    print(f"Título: {state.goal.title}")
    if state.plan is None:
        print("Plan atual: nenhum")
    else:
        print(
            f"Plan atual: {state.plan.id} | revisão {state.plan.revision} | {state.plan.status}"
        )
        print(f"World revision do Plan: {state.plan.based_on_world_revision}")
        print(
            "World mudou desde o Plan: "
            + ("sim" if state.world_changed_since_plan else "não")
        )

    if state.readiness is None:
        print("Próximo passo executável: não aplicável")
    elif state.readiness.next_step is None:
        print("Próximo passo executável: nenhum")
        pending_step = next(
            (step for step in state.readiness.steps if step.state != "VERIFIED"),
            None,
        )
        if pending_step is not None:
            print(f"Próximo passo pendente: {pending_step.step_id} | {pending_step.state}")
            print(f"Descrição pendente: {pending_step.description}")
            print(f"Capability pendente: {pending_step.capability or 'não especificada'}")
            if pending_step.blockers:
                print("Bloqueios do passo pendente:")
                for blocker in pending_step.blockers:
                    print(f"- {blocker.kind}: {blocker.detail}")
    else:
        next_step = state.readiness.next_step
        print(f"Próximo passo executável: {next_step.step_id}")
        print(f"Descrição: {next_step.description}")
        print(f"Capability: {next_step.capability or 'não especificada'}")

    if state.actions:
        print(f"Actions reconstruídas: {len(state.actions)}")
        for resumed in state.actions:
            action = resumed.action
            verification = resumed.latest_verification_status or "sem Verification"
            print(
                f"- {action.id}: {action.kind} | {action.status} | "
                f"step {action.step_id} | {verification}"
            )
    else:
        print("Actions reconstruídas: nenhuma")

    if state.latest_experience is not None:
        experience = state.latest_experience
        print(f"Última Experience do Goal: {experience.id} | {experience.status}")
        if experience.outcome is not None:
            print(f"Outcome: {experience.outcome}")
    elif overview.latest_experience is not None:
        print(
            "Última Experience do Goal: nenhuma "
            f"(última global: {overview.latest_experience.id})"
        )
    else:
        print("Última Experience do Goal: nenhuma")

    _print_resume_memories(state.memories)
    return 0


def _print_resume_memories(memories: tuple[Memory, ...]) -> None:
    if not memories:
        print("Memories relevantes: nenhuma")
        return

    print(f"Memories relevantes: {len(memories)}")
    for memory in memories:
        print(f"- {memory.id}: {memory.kind}/{memory.scope} | {memory.content}")


def _model_check(base_url: str, timeout_seconds: float) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        models = provider.list_models()
    except ModelProviderError as exc:
        print(f"Ollama: indisponível ({exc})")
        return 1

    print(f"Ollama: pronto ({base_url.rstrip('/')})")
    if not models:
        print("Modelos locais: nenhum")
        return 0

    print(f"Modelos locais: {len(models)}")
    for model in models:
        print(f"- {model}")
    return 0


def _model_test(base_url: str, timeout_seconds: float, model: str) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        result = provider.generate_structured(
            model=model,
            system=(
                "Você está respondendo a um diagnóstico interno do SIMON. "
                "Siga estritamente o schema solicitado."
            ),
            prompt=(
                "Confirme que recebeu esta mensagem. Use status 'ok' e uma mensagem curta "
                "em português."
            ),
            response_model=ModelDiagnosticResponse,
        )
    except ModelProviderError as exc:
        print(f"Modelo: falha ({exc})")
        return 1

    print(f"Modelo: {result.model}")
    print(f"Status estruturado: {result.output.status}")
    print(f"Mensagem: {result.output.message}")
    if result.eval_count is not None:
        print(f"Tokens gerados: {result.eval_count}")
    return 0


def _run_interpretation(
    database_path: Path,
    provider: ModelProvider,
    *,
    model: str,
    text: str,
    trace_id: str,
) -> tuple[CognitiveContext, StructuredModelResult[UserInputInterpretation]]:
    append_event(
        database_path,
        Event.create(
            kind="user.input.received",
            source="user",
            payload={"text": text},
            trace_id=trace_id,
        ),
    )

    try:
        context = build_cognitive_context(database_path, text=text)
        append_event(
            database_path,
            Event.create(
                kind="cognition.context.built",
                source="cognition",
                payload={
                    "goal_ids": [goal.id for goal in context.goals],
                    "entity_ids": [entity.id for entity in context.entities],
                    "claim_ids": [claim.id for claim in context.claims],
                    "memory_ids": [memory.id for memory in context.memories],
                },
                trace_id=trace_id,
            ),
        )
        result = interpret_user_input(
            provider,
            model=model,
            text=text,
            context=context,
        )
    except (ModelProviderError, ValueError) as exc:
        append_event(
            database_path,
            Event.create(
                kind="cognition.interpretation.failed",
                source="cognition",
                payload={"model": model, "error": str(exc)},
                trace_id=trace_id,
            ),
        )
        raise

    append_event(
        database_path,
        Event.create(
            kind="cognition.interpretation.completed",
            source="cognition",
            payload={
                "model": result.model,
                "interpretation": result.output.model_dump(mode="json"),
                "prompt_eval_count": result.prompt_eval_count,
                "eval_count": result.eval_count,
                "total_duration_ns": result.total_duration_ns,
            },
            trace_id=trace_id,
        ),
    )
    return context, result


def _interpret(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    text: str,
) -> int:
    trace_id = f"trc_{uuid4().hex}"
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        context, result = _run_interpretation(
            database_path,
            provider,
            model=model,
            text=text,
            trace_id=trace_id,
        )
    except (ModelProviderError, ValueError) as exc:
        print(f"Interpretação: falha ({exc})")
        return 1

    print(f"Modelo: {result.model}")
    _print_context_summary(context)
    print(f"Intenção: {result.output.intent}")
    print(f"Objetivo: {result.output.objective or 'nenhum explícito'}")

    if result.output.entity_mentions:
        print("Entidades mencionadas:")
        for entity in result.output.entity_mentions:
            print(f"- {entity.text} ({entity.kind})")
    else:
        print("Entidades mencionadas: nenhuma")

    if result.output.ambiguities:
        print("Ambiguidades:")
        for ambiguity in result.output.ambiguities:
            print(f"- {ambiguity}")
    else:
        print("Ambiguidades: nenhuma")

    _print_model_metrics(result)
    return 0


def _goal_propose(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    text: str,
) -> int:
    trace_id = f"trc_{uuid4().hex}"
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)

    try:
        context, interpretation_result = _run_interpretation(
            database_path,
            provider,
            model=model,
            text=text,
            trace_id=trace_id,
        )
    except (ModelProviderError, ValueError) as exc:
        print(f"Interpretação: falha ({exc})")
        return 1

    interpretation = interpretation_result.output
    print(f"Modelo: {interpretation_result.model}")
    _print_context_summary(context)
    print(f"Intenção: {interpretation.intent}")

    if interpretation.intent != "REQUEST":
        print("Proposta de Goal: não gerada (a intenção não é REQUEST)")
        return 0

    try:
        proposal_result = propose_goal(
            provider,
            model=model,
            text=text,
            interpretation=interpretation,
            context=context,
        )
    except (ModelProviderError, ValueError) as exc:
        append_event(
            database_path,
            Event.create(
                kind="cognition.goal_proposal.failed",
                source="cognition",
                payload={"model": model, "error": str(exc)},
                trace_id=trace_id,
            ),
        )
        print(f"Proposta de Goal: falha ({exc})")
        return 1

    proposal_event = Event.create(
        kind="cognition.goal_proposal.completed",
        source="cognition",
        payload={
            "model": proposal_result.model,
            "proposal": proposal_result.output.model_dump(mode="json"),
            "prompt_eval_count": proposal_result.prompt_eval_count,
            "eval_count": proposal_result.eval_count,
            "total_duration_ns": proposal_result.total_duration_ns,
        },
        trace_id=trace_id,
    )
    append_event(database_path, proposal_event)

    proposal = proposal_result.output
    print("Proposta de Goal:")
    print(f"Título: {proposal.title}")
    print(f"Estado desejado: {proposal.desired_state}")
    print("Critérios de sucesso:")
    for criterion in proposal.success_criteria:
        print(f"- {criterion}")

    if proposal.open_questions:
        print("Questões em aberto:")
        for question in proposal.open_questions:
            print(f"- {question}")
    else:
        print("Questões em aberto: nenhuma")

    _print_model_metrics(proposal_result)
    print(f"ID da proposta: {proposal_event.id}")
    print("Goal persistido: não")
    return 0


def _goal_accept(database_path: Path, proposal_event_id: str) -> int:
    trace_id = f"trc_{uuid4().hex}"
    try:
        acceptance = accept_goal_proposal(
            database_path,
            proposal_event_id,
            trace_id=trace_id,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"Aceitação de Goal: falha ({exc})")
        return 1

    goal = acceptance.goal
    print(f"Goal: {goal.id}")
    print(f"Título: {goal.title}")
    print(f"Origem: {goal.origin}")
    print(f"Status: {goal.status}")
    if acceptance.created:
        print("Goal persistido: sim")
    else:
        print("Goal persistido: já existia para esta proposta")
    return 0


def _goal_assess(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    goal_id: str,
) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        receipt = assess_goal_outcome(
            database_path,
            provider,
            model=model,
            goal_id=goal_id,
        )
    except (ModelProviderError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Assessment de Goal: falha ({exc})")
        return 1

    goal = get_goal(database_path, goal_id)
    if goal is None:
        print(f"Assessment de Goal: falha (goal não encontrado: {goal_id})")
        return 1

    desired_description = goal.desired_state.get("description")
    print(f"Modelo: {receipt.model}")
    print(f"Goal: {goal.id} ({goal.title})")
    print(f"Plan avaliado: {receipt.plan_id} (revisão {receipt.plan_revision})")
    if isinstance(desired_description, str) and desired_description.strip():
        print(f"Estado desejado: {desired_description.strip()}")
    print(f"Veredito geral: {receipt.overall_verdict}")
    print("Critérios:")
    criteria_by_index = {
        index: criterion
        for index, criterion in enumerate(goal.success_criteria, start=1)
    }
    for item in sorted(receipt.assessment.criteria, key=lambda value: value.criterion_index):
        criterion = criteria_by_index[item.criterion_index].get("description", "")
        print(f"- [{item.criterion_index}] {item.verdict}: {criterion}")
        print(f"  Justificativa: {item.rationale}")
        if item.supporting_step_ids:
            print(f"  Steps de suporte: {', '.join(item.supporting_step_ids)}")
        else:
            print("  Steps de suporte: nenhum")

    if receipt.assessment.missing_evidence:
        print("Evidência ausente:")
        for missing in receipt.assessment.missing_evidence:
            print(f"- {missing}")
    else:
        print("Evidência ausente: nenhuma")

    if receipt.prompt_eval_count is not None:
        print(f"Tokens de entrada: {receipt.prompt_eval_count}")
    if receipt.eval_count is not None:
        print(f"Tokens gerados: {receipt.eval_count}")
    if receipt.total_duration_ns is not None:
        print(f"Duração: {receipt.total_duration_ns / 1_000_000_000:.2f}s")
    print(f"Verification: {receipt.verification.id}")
    print(f"Status persistido: {receipt.verification.status}")
    print("Goal alterado: não")
    if receipt.created:
        print("Assessment criada: sim")
    else:
        print("Assessment criada: não (já existia para este Plan e modelo)")
    return 0


def _goal_complete(database_path: Path, assessment_verification_id: str) -> int:
    try:
        receipt = complete_goal_from_assessment(
            database_path,
            assessment_verification_id=assessment_verification_id,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Conclusão de Goal: falha ({exc})")
        return 1

    print(f"Goal: {receipt.goal.id} ({receipt.goal.title})")
    print(f"Assessment confirmado: {receipt.assessment.id}")
    print(f"Verification: {receipt.verification.id}")
    print(f"Status epistemológico: {receipt.verification.status}")
    print(f"Status do Goal: {receipt.goal.status}")
    print(f"Confirmação: {receipt.confirmation_event_id}")
    print(f"Conclusão: {receipt.completion_event_id}")
    print(f"Experience: {receipt.experience_closure.experience.id}")
    print(f"Outcome da Experience: {receipt.experience_closure.experience.outcome}")
    if receipt.experience_closure.created:
        print("Experience consolidada: sim")
    else:
        print("Experience consolidada: não (já existia)")
    if receipt.created:
        print("Goal concluído: sim")
    else:
        print("Goal concluído: não (esta confirmação já havia sido aplicada)")
    return 0


def _experience_remember(
    database_path: Path,
    experience_id: str,
    kind: str,
    scope: str,
    content: str,
    entity_ids: tuple[str, ...],
    claim_ids: tuple[str, ...],
) -> int:
    try:
        receipt = promote_experience_to_memory(
            database_path,
            experience_id=experience_id,
            kind=kind,
            content=content,
            scope=scope,
            entity_ids=entity_ids,
            source_claim_ids=claim_ids,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Promoção de Memory: falha ({exc})")
        return 1

    print(f"Experience: {receipt.experience.id} ({receipt.experience.title})")
    print(f"Outcome: {receipt.experience.outcome}")
    print(f"Memory: {receipt.memory.id}")
    print(f"Kind: {receipt.memory.kind}")
    print(f"Scope: {receipt.memory.scope}")
    print(f"Conteúdo: {receipt.memory.content}")
    if receipt.memory.entity_ids:
        print(f"Entities: {', '.join(receipt.memory.entity_ids)}")
    else:
        print("Entities: nenhuma")
    if receipt.memory.source_claim_ids:
        print(f"Claims: {', '.join(receipt.memory.source_claim_ids)}")
    else:
        print("Claims: nenhuma")
    print(f"Promoção registrada: {receipt.promotion_event_id}")
    print("Memory criada por decisão explícita: sim")
    return 0


def _plan_propose(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    goal_id: str,
) -> int:
    try:
        ensure_plan_proposal_allowed(database_path, goal_id=goal_id)
    except PlanProposalGateError as exc:
        print(f"Proposta de Plan: não gerada ({exc})")
        return 0
    except (TypeError, ValueError) as exc:
        print(f"Proposta de Plan: falha ({exc})")
        return 1

    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        receipt = propose_plan_for_goal(
            database_path,
            provider,
            model=model,
            goal_id=goal_id,
        )
    except PlanProposalGateError as exc:
        print(f"Proposta de Plan: não gerada ({exc})")
        return 0
    except (ModelProviderError, TypeError, ValueError) as exc:
        print(f"Proposta de Plan: falha ({exc})")
        return 1

    result = receipt.result
    goal = receipt.goal
    context = receipt.context
    goal_assessment = receipt.goal_assessment
    plan_failure = receipt.plan_failure

    print(f"Modelo: {result.model}")
    print(f"Goal: {goal.id} ({goal.title})")
    _print_context_summary(context)
    if goal_assessment is not None:
        print(
            "Assessment de continuação: "
            f"{goal_assessment.verification_id} ({goal_assessment.verdict})"
        )
        print(
            "Plan anterior avaliado: "
            f"{goal_assessment.plan_id} (revisão {goal_assessment.plan_revision})"
        )
    if plan_failure is not None:
        print(
            "Replanejamento motivado por falha: "
            f"{plan_failure.verification_id} ({plan_failure.blocker_kind})"
        )
        print(
            "Plan ACTIVE substituível: "
            f"{plan_failure.plan_id} (revisão {plan_failure.plan_revision})"
        )
        print(f"Step afetado: {plan_failure.step_id}")
    print("Proposta de Plan:")
    print(f"Resumo: {result.output.summary}")
    print("Passos:")
    for step in result.output.steps:
        print(f"- {step.id} [{step.kind}] {step.description}")
        if step.intent_role is not None and step.intent_actor is not None:
            print(f"  Intent: {step.intent_role} / {step.intent_actor}")
        print(f"  Capability: {step.capability}")
        if step.capability_detail is not None:
            print(f"  Detalhe da capability: {step.capability_detail}")
        if step.depends_on:
            print(f"  Depende de: {', '.join(step.depends_on)}")
        else:
            print("  Depende de: nenhum")
        if step.preconditions:
            print(f"  Preconditions: {'; '.join(step.preconditions)}")
        else:
            print("  Preconditions: nenhuma")
        print(f"  Verificação: {step.verification}")

    if result.output.open_questions:
        print("Questões em aberto:")
        for question in result.output.open_questions:
            print(f"- {question}")
    else:
        print("Questões em aberto: nenhuma")

    _print_model_metrics(result)
    print(f"ID da proposta: {receipt.proposal_event.id}")
    print("Plan persistido: não")
    return 0


def _plan_materialize(database_path: Path, proposal_event_id: str) -> int:
    trace_id = f"trc_{uuid4().hex}"
    try:
        materialization = materialize_plan_proposal(
            database_path,
            proposal_event_id,
            trace_id=trace_id,
        )
    except (TypeError, ValueError, RuntimeError) as exc:
        print(f"Materialização de Plan: falha ({exc})")
        return 1

    plan = materialization.plan
    print(f"Plan: {plan.id}")
    print(f"Goal: {plan.goal_id}")
    print(f"Revisão: {plan.revision}")
    print(f"Status: {plan.status}")
    print(f"Passos: {len(plan.steps)}")
    if materialization.created:
        print("Plan persistido: sim")
    else:
        print("Plan persistido: já existia para esta proposta")
    return 0


def _plan_next(database_path: Path, goal_id: str) -> int:
    trace_id = f"trc_{uuid4().hex}"
    try:
        readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    except (TypeError, ValueError) as exc:
        print(f"Avaliação de Plan: falha ({exc})")
        return 1

    _record_plan_readiness(database_path, readiness, trace_id=trace_id)

    print(f"Goal: {readiness.plan.goal_id}")
    print(f"Plan: {readiness.plan.id}")
    print(f"Revisão: {readiness.plan.revision}")
    if readiness.available_capabilities:
        print(
            "Capabilities executáveis registradas: "
            + ", ".join(readiness.available_capabilities)
        )
    else:
        print("Capabilities executáveis registradas: nenhuma")

    if readiness.next_step is None:
        print("Próximo passo executável: nenhum")
    else:
        print(f"Próximo passo executável: {readiness.next_step.step_id}")
        print(f"Descrição: {readiness.next_step.description}")
        print(f"Capability: {readiness.next_step.capability or 'não especificada'}")

    print("Avaliação dos passos:")
    for step in readiness.steps:
        print(f"- {step.step_id}: {step.state}")
        for blocker in step.blockers:
            print(f"  {blocker.kind}: {blocker.detail}")

    print("Action criada: não")
    return 0



def _plan_complete(database_path: Path, goal_id: str) -> int:
    trace_id = f"trc_{uuid4().hex}"
    try:
        completion = complete_verified_plan(
            database_path,
            goal_id=goal_id,
            trace_id=trace_id,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Conclusão de Plan: falha ({exc})")
        return 1

    print(f"Plan: {completion.plan.id}")
    print(f"Goal: {completion.plan.goal_id}")
    print(f"Revisão: {completion.plan.revision}")
    print(f"Status: {completion.plan.status}")
    print(f"Steps verificados: {len(completion.verified_step_ids)}")
    print(f"Conclusão registrada: {completion.completion_event_id}")
    if completion.created:
        print("Plan concluído: sim")
    else:
        print("Plan concluído: não (já estava concluído)")
    print("Goal alterado: não")
    return 0


def _plan_ask(database_path: Path, goal_id: str) -> int:
    try:
        dispatch = dispatch_next_user_ask(database_path, goal_id=goal_id)
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Action user.ask: falha ({exc})")
        return 1

    print(f"Action: {dispatch.action.id}")
    print(f"Goal: {dispatch.action.goal_id}")
    print(f"Plan: {dispatch.action.plan_id}")
    print(f"Step: {dispatch.action.step_id}")
    print(f"Capability: {dispatch.action.kind}")
    print(f"Status: {dispatch.action.status}")
    print(f"Solicitação: {dispatch.prompt}")
    if dispatch.created:
        print("Action criada: sim")
    else:
        print("Action criada: não (já aguardava resposta)")
    return 0


def _plan_run(
    database_path: Path,
    goal_id: str,
    executable: str,
    arguments: Sequence[str],
    working_directory: str,
    timeout_seconds: float,
) -> int:
    try:
        request = ProcessRunRequest(
            executable=executable,
            arguments=tuple(arguments),
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
        receipt = execute_next_process_run(
            database_path,
            goal_id=goal_id,
            request=request,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Action process.run: falha ({exc})")
        return 1

    print(f"Action: {receipt.action.id}")
    print(f"Goal: {receipt.action.goal_id}")
    print(f"Plan: {receipt.action.plan_id}")
    print(f"Step: {receipt.action.step_id}")
    print(f"Capability: {receipt.action.kind}")
    print(f"Status: {receipt.action.status}")
    print(f"Autorização registrada: {receipt.authorization_event_id}")
    print(f"Execução registrada: {receipt.execution_event_id}")
    if receipt.exit_code is not None:
        print(f"Exit code: {receipt.exit_code}")
    print(f"Duração: {receipt.duration_seconds:.3f}s")
    if receipt.stdout:
        print("stdout:")
        print(receipt.stdout, end="" if receipt.stdout.endswith("\n") else "\n")
    else:
        print("stdout: vazio")
    if receipt.stderr:
        print("stderr:")
        print(receipt.stderr, end="" if receipt.stderr.endswith("\n") else "\n")
    else:
        print("stderr: vazio")
    print("Verification criada: não")
    return 0 if receipt.action.status == "COMPLETED" else 1


def _process_retry(
    database_path: Path,
    action_id: str,
    executable: str,
    arguments: Sequence[str],
    working_directory: str,
    timeout_seconds: float,
) -> int:
    try:
        request = ProcessRunRequest(
            executable=executable,
            arguments=tuple(arguments),
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
        receipt = retry_process_run(
            database_path,
            action_id=action_id,
            request=request,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Retry process.run: falha ({exc})")
        return 1

    print(f"Action anterior: {receipt.retry_of_action_id}")
    print(f"Action: {receipt.action.id}")
    print(f"Goal: {receipt.action.goal_id}")
    print(f"Plan: {receipt.action.plan_id}")
    print(f"Step: {receipt.action.step_id}")
    print(f"Status: {receipt.action.status}")
    print(f"Autorização de retry: {receipt.authorization_event_id}")
    print(f"Execução registrada: {receipt.execution_event_id}")
    if receipt.exit_code is not None:
        print(f"Exit code: {receipt.exit_code}")
    print(f"Duração: {receipt.duration_seconds:.3f}s")
    if receipt.stdout:
        print("stdout:")
        print(receipt.stdout, end="" if receipt.stdout.endswith("\n") else "\n")
    else:
        print("stdout: vazio")
    if receipt.stderr:
        print("stderr:")
        print(receipt.stderr, end="" if receipt.stderr.endswith("\n") else "\n")
    else:
        print("stderr: vazio")
    print("Verification criada: não")
    return 0 if receipt.action.status == "COMPLETED" else 1


def _plan_patch(
    database_path: Path,
    goal_id: str,
    workspace: str,
    relative_path: str,
    expected_text: str,
    replacement_text: str,
) -> int:
    try:
        request = FilePatchRequest(
            workspace=workspace,
            relative_path=relative_path,
            expected_text=expected_text,
            replacement_text=replacement_text,
        )
        receipt = execute_next_file_patch(
            database_path,
            goal_id=goal_id,
            request=request,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Action file.patch: falha ({exc})")
        return 1

    print(f"Action: {receipt.action.id}")
    print(f"Goal: {receipt.action.goal_id}")
    print(f"Plan: {receipt.action.plan_id}")
    print(f"Step: {receipt.action.step_id}")
    print(f"Capability resolvida: {receipt.action.kind}")
    print(f"Status: {receipt.action.status}")
    print(f"Arquivo: {receipt.target_path}")
    print(f"Autorização registrada: {receipt.authorization_event_id}")
    print(f"Modificação registrada: {receipt.modification_event_id}")
    if receipt.before_sha256 is not None:
        print(f"SHA-256 anterior: {receipt.before_sha256}")
    if receipt.after_sha256 is not None:
        print(f"SHA-256 atual: {receipt.after_sha256}")
    print("Verification criada: não")
    return 0 if receipt.action.status == "COMPLETED" else 1


def _file_retry(
    database_path: Path,
    action_id: str,
    workspace: str,
    relative_path: str,
    expected_text: str,
    replacement_text: str,
) -> int:
    try:
        request = FilePatchRequest(
            workspace=workspace,
            relative_path=relative_path,
            expected_text=expected_text,
            replacement_text=replacement_text,
        )
        receipt = retry_file_patch(
            database_path,
            action_id=action_id,
            request=request,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Retry file.patch: falha ({exc})")
        return 1

    print(f"Action anterior: {receipt.retry_of_action_id}")
    print(f"Action: {receipt.action.id}")
    print(f"Goal: {receipt.action.goal_id}")
    print(f"Plan: {receipt.action.plan_id}")
    print(f"Step: {receipt.action.step_id}")
    print(f"Capability resolvida: {receipt.action.kind}")
    print(f"Status: {receipt.action.status}")
    print(f"Arquivo: {receipt.target_path}")
    print(f"Autorização de retry: {receipt.authorization_event_id}")
    print(f"Modificação registrada: {receipt.modification_event_id}")
    if receipt.before_sha256 is not None:
        print(f"SHA-256 anterior: {receipt.before_sha256}")
    if receipt.after_sha256 is not None:
        print(f"SHA-256 atual: {receipt.after_sha256}")
    print("Verification criada: não")
    return 0 if receipt.action.status == "COMPLETED" else 1


def _plan_analyze(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    goal_id: str,
) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        receipt = execute_next_cognition_analysis(
            database_path,
            provider,
            model=model,
            goal_id=goal_id,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Action cognition.analyze: falha ({exc})")
        return 1

    print(f"Action: {receipt.action.id}")
    print(f"Goal: {receipt.action.goal_id}")
    print(f"Plan: {receipt.action.plan_id}")
    print(f"Step: {receipt.action.step_id}")
    print(f"Capability: {receipt.action.kind}")
    print(f"Status: {receipt.action.status}")
    print(f"Modelo: {receipt.model}")
    print(f"Evidências consumidas: {len(receipt.evidence_event_ids)}")
    for event_id in receipt.evidence_event_ids:
        print(f"- {event_id}")
    print(f"Resultado registrado: {receipt.result_event_id}")

    if receipt.analysis is None:
        failure = receipt.action.failure or {}
        print(f"Falha cognitiva: {failure.get('message', 'não especificada')}")
        print("Verification criada: não")
        return 1

    print("Análise:")
    print(receipt.analysis.summary)
    if receipt.analysis.findings:
        print("Findings:")
        for finding in receipt.analysis.findings:
            print(f"- {finding.statement}")
            print(f"  Evidência: {', '.join(finding.evidence_event_ids)}")
    else:
        print("Findings: nenhum")
    if receipt.analysis.uncertainties:
        print("Incertezas:")
        for uncertainty in receipt.analysis.uncertainties:
            print(f"- {uncertainty}")
    else:
        print("Incertezas: nenhuma")
    if receipt.prompt_eval_count is not None:
        print(f"Tokens de entrada: {receipt.prompt_eval_count}")
    if receipt.eval_count is not None:
        print(f"Tokens gerados: {receipt.eval_count}")
    if receipt.total_duration_ns is not None:
        print(f"Duração: {receipt.total_duration_ns / 1_000_000_000:.2f}s")
    print("Verification criada: não")
    return 0


def _analysis_retry(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    action_id: str,
) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        receipt = retry_cognition_analysis(
            database_path,
            provider,
            model=model,
            action_id=action_id,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Retry cognition.analyze: falha ({exc})")
        return 1

    print(f"Action anterior: {receipt.retry_of_action_id}")
    print(f"Action: {receipt.action.id}")
    print(f"Goal: {receipt.action.goal_id}")
    print(f"Plan: {receipt.action.plan_id}")
    print(f"Step: {receipt.action.step_id}")
    print(f"Capability: {receipt.action.kind}")
    print(f"Status: {receipt.action.status}")
    print(f"Modelo: {receipt.model}")
    print(f"Evidências consumidas: {len(receipt.evidence_event_ids)}")
    for event_id in receipt.evidence_event_ids:
        print(f"- {event_id}")
    print(f"Resultado registrado: {receipt.result_event_id}")

    if receipt.analysis is None:
        failure = receipt.action.failure or {}
        print(f"Falha cognitiva: {failure.get('message', 'não especificada')}")
        print("Verification criada: não")
        return 1

    print("Análise:")
    print(receipt.analysis.summary)
    if receipt.analysis.findings:
        print("Findings:")
        for finding in receipt.analysis.findings:
            print(f"- {finding.statement}")
            print(f"  Evidência: {', '.join(finding.evidence_event_ids)}")
    else:
        print("Findings: nenhum")
    if receipt.analysis.uncertainties:
        print("Incertezas:")
        for uncertainty in receipt.analysis.uncertainties:
            print(f"- {uncertainty}")
    else:
        print("Incertezas: nenhuma")
    if receipt.prompt_eval_count is not None:
        print(f"Tokens de entrada: {receipt.prompt_eval_count}")
    if receipt.eval_count is not None:
        print(f"Tokens gerados: {receipt.eval_count}")
    if receipt.total_duration_ns is not None:
        print(f"Duração: {receipt.total_duration_ns / 1_000_000_000:.2f}s")
    print("Verification criada: não")
    return 0


def _analysis_assess(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    action_id: str,
) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        receipt = assess_cognition_analysis(
            database_path,
            provider,
            model=model,
            action_id=action_id,
        )
    except (ModelProviderError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Assessment cognition.analyze: falha ({exc})")
        return 1

    criterion = receipt.verification.criteria[0].get("description")
    print(f"Modelo avaliador: {receipt.model}")
    print(f"Action: {receipt.verification.subject_id}")
    print(f"Critério: {criterion}")
    print(f"Veredito: {receipt.assessment.verdict}")
    print(f"Justificativa: {receipt.assessment.rationale}")
    if receipt.assessment.missing_information:
        print("Informações ausentes:")
        for item in receipt.assessment.missing_information:
            print(f"- {item}")
    else:
        print("Informações ausentes: nenhuma")
    if receipt.prompt_eval_count is not None:
        print(f"Tokens de entrada: {receipt.prompt_eval_count}")
    if receipt.eval_count is not None:
        print(f"Tokens gerados: {receipt.eval_count}")
    if receipt.total_duration_ns is not None:
        print(f"Duração: {receipt.total_duration_ns / 1_000_000_000:.2f}s")
    print(f"Verification: {receipt.verification.id}")
    print(f"Status persistido: {receipt.verification.status}")
    if receipt.created:
        print("Assessment criada: sim")
    else:
        print("Assessment criada: não (já existia para esta análise e modelo)")
    return 0


def _process_verify(database_path: Path, action_id: str) -> int:
    try:
        receipt = verify_process_run_execution(database_path, action_id=action_id)
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Verification process.run: falha ({exc})")
        return 1

    observed = receipt.verification.observed
    print(f"Action: {receipt.action.id}")
    print(f"Goal: {receipt.action.goal_id}")
    print(f"Plan: {receipt.action.plan_id}")
    print(f"Step: {receipt.action.step_id}")
    print(f"Verification: {receipt.verification.id}")
    print(f"Status persistido: {receipt.verification.status}")
    print(f"Força: {receipt.verification.strength}")
    print(f"Evidência: {receipt.verification.evidence_event_ids[0]}")
    print(f"Exit code observado: {observed.get('exit_code')}")
    print(
        "Critério do Plan preservado, sem avaliação semântica: "
        f"{observed.get('plan_verification_intent')}"
    )
    if receipt.created:
        print("Verification criada: sim")
    else:
        print("Verification criada: não (já existia para esta execução)")
    return 0


def _file_verify(database_path: Path, action_id: str) -> int:
    try:
        receipt = verify_file_patch_state(database_path, action_id=action_id)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Verification file.patch: falha ({exc})")
        return 1

    observed = receipt.verification.observed
    print(f"Action: {receipt.action.id}")
    print(f"Goal: {receipt.action.goal_id}")
    print(f"Plan: {receipt.action.plan_id}")
    print(f"Step: {receipt.action.step_id}")
    print(f"Verification: {receipt.verification.id}")
    print(f"Status persistido: {receipt.verification.status}")
    print(f"Força: {receipt.verification.strength}")
    print(f"Arquivo: {observed.get('target_path')}")
    print(f"SHA-256 esperado: {observed.get('expected_after_sha256')}")
    current_sha256 = observed.get("current_sha256")
    print(f"SHA-256 observado: {current_sha256 if current_sha256 is not None else 'indisponível'}")
    print(f"Estado observado: {observed.get('current_state')}")
    if observed.get("detail"):
        print(f"Detalhe: {observed.get('detail')}")
    print(
        "Critério do Plan preservado, sem avaliação semântica: "
        f"{observed.get('plan_verification_intent')}"
    )
    if receipt.created:
        print("Verification criada: sim")
    else:
        print("Verification criada: não (mesmo estado já havia sido observado)")
    return 0 if receipt.verification.status == "VERIFIED" else 1


def _action_answer(database_path: Path, action_id: str, text: str) -> int:
    try:
        receipt = answer_user_ask(
            database_path,
            action_id=action_id,
            response=text,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Resposta user.ask: falha ({exc})")
        return 1

    print(f"Action: {receipt.action.id}")
    print(f"Status: {receipt.action.status}")
    print(f"Resposta registrada: {receipt.response_event_id}")
    print("Verification criada: não")
    return 0


def _action_assess(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    action_id: str,
) -> int:
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)
    try:
        receipt = assess_user_ask_response(
            database_path,
            provider,
            model=model,
            action_id=action_id,
        )
    except (ModelProviderError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Assessment user.ask: falha ({exc})")
        return 1

    criterion = receipt.verification.criteria[0].get("description")
    print(f"Modelo: {receipt.model}")
    print(f"Action: {receipt.verification.subject_id}")
    print(f"Critério: {criterion}")
    print(f"Veredito: {receipt.assessment.verdict}")
    print(f"Justificativa: {receipt.assessment.rationale}")
    if receipt.assessment.missing_information:
        print("Informações ausentes:")
        for item in receipt.assessment.missing_information:
            print(f"- {item}")
    else:
        print("Informações ausentes: nenhuma")
    if receipt.prompt_eval_count is not None:
        print(f"Tokens de entrada: {receipt.prompt_eval_count}")
    if receipt.eval_count is not None:
        print(f"Tokens gerados: {receipt.eval_count}")
    if receipt.total_duration_ns is not None:
        print(f"Duração: {receipt.total_duration_ns / 1_000_000_000:.2f}s")
    print(f"Verification: {receipt.verification.id}")
    print(f"Status persistido: {receipt.verification.status}")
    if receipt.created:
        print("Assessment criada: sim")
    else:
        print("Assessment criada: não (já existia para esta resposta e modelo)")
    return 0


def _action_retry(
    database_path: Path,
    action_id: str,
    prompt: str | None,
) -> int:
    try:
        dispatch = retry_user_ask(
            database_path,
            action_id=action_id,
            prompt=prompt,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Retry user.ask: falha ({exc})")
        return 1

    print(f"Action anterior: {dispatch.retry_of_action_id}")
    print(f"Verification de review: {dispatch.review_verification_id}")
    print(f"Action: {dispatch.action.id}")
    print(f"Goal: {dispatch.action.goal_id}")
    print(f"Plan: {dispatch.action.plan_id}")
    print(f"Step: {dispatch.action.step_id}")
    print(f"Status: {dispatch.action.status}")
    print(f"Solicitação: {dispatch.prompt}")
    if dispatch.created:
        print("Retry criado: sim")
    else:
        print("Retry criado: não (já aguardava resposta)")
    return 0


def _verification_confirm(
    database_path: Path,
    assessment_verification_id: str,
) -> int:
    try:
        receipt = confirm_action_assessment(
            database_path,
            assessment_verification_id=assessment_verification_id,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Confirmação de Verification: falha ({exc})")
        return 1

    print(f"Assessment: {receipt.assessment.id}")
    print(f"Tipo: {receipt.assessment.observed.get('assessment_type')}")
    print(f"Action: {receipt.verification.subject_id}")
    print(f"Veredito avaliado: {receipt.assessment.observed.get('verdict')}")
    print(f"Verification: {receipt.verification.id}")
    print(f"Status persistido: {receipt.verification.status}")
    print(f"Força: {receipt.verification.strength}")
    print(f"Confirmação registrada: {receipt.confirmation_event_id}")
    if receipt.created:
        print("Verification confirmada: sim")
    else:
        print("Verification confirmada: não (já existia para este assessment)")
    return 0


def _record_plan_readiness(
    database_path: Path,
    readiness: PlanReadiness,
    *,
    trace_id: str,
) -> None:
    append_event(
        database_path,
        Event.create(
            kind="plan.readiness.evaluated",
            source="system",
            payload={
                "plan_id": readiness.plan.id,
                "plan_revision": readiness.plan.revision,
                "available_capabilities": list(readiness.available_capabilities),
                "next_step_id": (
                    readiness.next_step.step_id if readiness.next_step is not None else None
                ),
                "steps": [
                    {
                        "step_id": step.step_id,
                        "state": step.state,
                        "blockers": [blocker.kind for blocker in step.blockers],
                        "related_action_id": step.related_action_id,
                    }
                    for step in readiness.steps
                ],
            },
            trace_id=trace_id,
            goal_id=readiness.plan.goal_id,
        ),
    )


def _print_context_summary(context: CognitiveContext) -> None:
    print(
        "Contexto: "
        f"{len(context.goals)} goal(s), "
        f"{len(context.entities)} entity(s), "
        f"{len(context.claims)} claim(s), "
        f"{len(context.memories)} memory(s)"
    )


def _print_model_metrics[OutputT: BaseModel](
    result: StructuredModelResult[OutputT],
) -> None:
    if result.repair_count:
        print(f"Reparos estruturados: {result.repair_count}")
    if result.prompt_eval_count is not None:
        print(f"Tokens de entrada: {result.prompt_eval_count}")
    if result.eval_count is not None:
        print(f"Tokens gerados: {result.eval_count}")
    if result.total_duration_ns is not None:
        print(f"Duração: {result.total_duration_ns / 1_000_000_000:.2f}s")
