from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from simon import __version__
from simon.actions import interrupt_running_actions
from simon.claims import set_current_claim
from simon.cognition import (
    UserInputInterpretation,
    interpret_user_input,
    propose_goal,
)
from simon.context import CognitiveContext, build_cognitive_context
from simon.entities import SIMON_ENTITY_ID, get_or_create_entity
from simon.events import Event, append_event
from simon.experiences import suspend_active_experiences
from simon.goal_intake import accept_goal_proposal, get_goal_acceptance_open_questions
from simon.goals import OPEN_STATUSES, get_goal
from simon.model_provider import ModelProvider, ModelProviderError, StructuredModelResult
from simon.ollama_provider import OllamaProvider
from simon.plan_intake import materialize_plan_proposal
from simon.planning import propose_plan
from simon.step_readiness import PlanReadiness, evaluate_active_plan
from simon.storage import initialize_storage
from simon.user_ask import answer_user_ask, dispatch_next_user_ask
from simon.user_ask_verification import assess_user_ask_response


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

    plan_ask = commands.add_parser(
        "plan-ask",
        help="cria a próxima Action user.ask e aguarda uma resposta do usuário",
    )
    plan_ask.add_argument(
        "goal_id",
        help="ID do Goal cujo próximo step user.ask será iniciado",
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
    database_path, schema_version = initialize_storage(args.data_dir.resolve())
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
    if args.command == "plan-ask":
        return _plan_ask(database_path, args.goal_id)
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

    print(f"S.I.M.O.N. {__version__}")
    print(f"Dados: {database_path.parent}")
    print(f"SQLite: pronto (schema {schema_version})")
    return 0


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


def _plan_propose(
    database_path: Path,
    base_url: str,
    timeout_seconds: float,
    model: str,
    goal_id: str,
) -> int:
    goal = get_goal(database_path, goal_id)
    if goal is None:
        print(f"Proposta de Plan: falha (goal não encontrado: {goal_id})")
        return 1
    if goal.status not in OPEN_STATUSES:
        print(f"Proposta de Plan: falha (goal não está aberto: {goal.status})")
        return 1

    desired_description = goal.desired_state.get("description")
    context_query = " ".join(
        part
        for part in (
            goal.title,
            desired_description if isinstance(desired_description, str) else "",
            *(
                str(criterion.get("description", ""))
                for criterion in goal.success_criteria
                if isinstance(criterion, dict)
            ),
        )
        if part.strip()
    )
    if not context_query:
        context_query = goal.title

    trace_id = f"trc_{uuid4().hex}"
    provider = OllamaProvider(base_url=base_url, timeout_seconds=timeout_seconds)

    try:
        context = build_cognitive_context(database_path, text=context_query)
        open_questions = get_goal_acceptance_open_questions(database_path, goal.id)
        append_event(
            database_path,
            Event.create(
                kind="cognition.context.built",
                source="cognition",
                payload={
                    "purpose": "plan",
                    "goal_ids": [item.id for item in context.goals],
                    "entity_ids": [entity.id for entity in context.entities],
                    "claim_ids": [claim.id for claim in context.claims],
                    "memory_ids": [memory.id for memory in context.memories],
                },
                trace_id=trace_id,
                goal_id=goal.id,
            ),
        )
        result = propose_plan(
            provider,
            model=model,
            goal=goal,
            open_questions=open_questions,
            context=context,
        )
    except (ModelProviderError, TypeError, ValueError) as exc:
        append_event(
            database_path,
            Event.create(
                kind="cognition.plan_proposal.failed",
                source="cognition",
                payload={"model": model, "error": str(exc)},
                trace_id=trace_id,
                goal_id=goal.id,
            ),
        )
        print(f"Proposta de Plan: falha ({exc})")
        return 1

    proposal_event = Event.create(
        kind="cognition.plan_proposal.completed",
        source="cognition",
        payload={
            "model": result.model,
            "proposal": result.output.model_dump(mode="json"),
            "source_open_questions": list(open_questions),
            "prompt_eval_count": result.prompt_eval_count,
            "eval_count": result.eval_count,
            "total_duration_ns": result.total_duration_ns,
        },
        trace_id=trace_id,
        goal_id=goal.id,
    )
    append_event(database_path, proposal_event)

    print(f"Modelo: {result.model}")
    print(f"Goal: {goal.id} ({goal.title})")
    _print_context_summary(context)
    print("Proposta de Plan:")
    print(f"Resumo: {result.output.summary}")
    print("Passos:")
    for step in result.output.steps:
        print(f"- {step.id} [{step.kind}] {step.description}")
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
    print(f"ID da proposta: {proposal_event.id}")
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
    if result.prompt_eval_count is not None:
        print(f"Tokens de entrada: {result.prompt_eval_count}")
    if result.eval_count is not None:
        print(f"Tokens gerados: {result.eval_count}")
    if result.total_duration_ns is not None:
        print(f"Duração: {result.total_duration_ns / 1_000_000_000:.2f}s")
