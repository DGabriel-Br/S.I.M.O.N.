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
from simon.goal_intake import accept_goal_proposal
from simon.model_provider import ModelProvider, ModelProviderError, StructuredModelResult
from simon.ollama_provider import OllamaProvider
from simon.storage import initialize_storage


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
