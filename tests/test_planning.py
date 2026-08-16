from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from simon.context import CognitiveContext
from simon.events import Event, append_event
from simon.goal_intake import get_goal_acceptance_open_questions
from simon.goals import Goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.planning import PlanProposal, PlanStepProposal, propose_plan
from simon.storage import initialize_storage


class FakePlanProvider:
    def __init__(self) -> None:
        self.system = ""
        self.prompt = ""
        self.response_model: type[BaseModel] | None = None

    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]:
        self.system = system or ""
        self.prompt = prompt
        self.response_model = response_model
        output = PlanProposal(
            summary="Obter evidências antes de corrigir o script.",
            steps=[
                PlanStepProposal(
                    id="step_1",
                    description="Identificar o script e coletar a falha observada.",
                    kind="EPISTEMIC",
                    capability="obter contexto do usuário",
                    verification="O script e a mensagem de erro estão identificados.",
                ),
                PlanStepProposal(
                    id="step_2",
                    description="Investigar a causa da falha com base nas evidências coletadas.",
                    kind="EPISTEMIC",
                    depends_on=["step_1"],
                    capability="analisar código e evidências de execução",
                    verification="Existe uma causa sustentada pelas evidências disponíveis.",
                ),
            ],
            open_questions=[],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


def test_propose_plan_turns_missing_information_into_epistemic_work() -> None:
    provider = FakePlanProvider()
    goal = Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem a falha relatada."},
        success_criteria=({"description": "A falha original não é reproduzida."},),
    )

    result = propose_plan(
        provider,
        model="fake-model",
        goal=goal,
        open_questions=("Qual script está falhando?",),
        context=CognitiveContext(goals=(goal,), entities=(), claims=(), memories=()),
    )

    assert result.output.steps[0].kind == "EPISTEMIC"
    assert provider.response_model is PlanProposal
    assert "não escolha Tools concretas" in provider.system
    assert "não invente arquivos" in provider.system
    assert "nunca escreva 'step_X concluído' em preconditions" in provider.system
    assert "Não assuma sistema operacional" in provider.system
    assert "Não assuma acesso a repositório" in provider.system
    assert '"open_questions_from_goal_acceptance":["Qual script está falhando?"]' in provider.prompt
    assert '"desired_state":{"description":"O script executa sem a falha relatada."}' in provider.prompt
    assert result.output.open_questions == ["Qual script está falhando?"]


def test_plan_proposal_rejects_dependency_on_future_step() -> None:
    with pytest.raises(ValidationError, match="passo step_1 depende de passo ainda não definido"):
        PlanProposal(
            summary="Plano inválido",
            steps=[
                PlanStepProposal(
                    id="step_1",
                    description="Executar depois do passo futuro.",
                    kind="WORLD",
                    depends_on=["step_2"],
                    capability="alterar estado",
                    verification="Mudança observada.",
                ),
                PlanStepProposal(
                    id="step_2",
                    description="Passo posterior.",
                    kind="EPISTEMIC",
                    capability="observar estado",
                    verification="Estado observado.",
                ),
            ],
        )


def test_plan_proposal_rejects_step_dependency_hidden_in_preconditions() -> None:
    with pytest.raises(ValidationError, match="dependências entre passos devem usar depends_on"):
        PlanProposal(
            summary="Plano inválido",
            steps=[
                PlanStepProposal(
                    id="step_1",
                    description="Obter evidência.",
                    kind="EPISTEMIC",
                    capability="observar estado",
                    verification="Evidência registrada.",
                ),
                PlanStepProposal(
                    id="step_2",
                    description="Analisar evidência.",
                    kind="EPISTEMIC",
                    preconditions=["step_1 concluído."],
                    capability="analisar evidência",
                    verification="Análise registrada.",
                ),
            ],
        )


def test_goal_acceptance_open_questions_are_recoverable_for_planning(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem erro."},
        success_criteria=({"description": "Execução concluída."},),
    )
    insert_goal(database_path, goal)
    append_event(
        database_path,
        Event.create(
            kind="goal.proposal.accepted",
            source="user",
            payload={
                "proposal_event_id": "evt_source",
                "open_questions": [
                    "Qual script está falhando?",
                    "Qual erro foi observado?",
                ],
            },
            goal_id=goal.id,
        ),
    )

    assert get_goal_acceptance_open_questions(database_path, goal.id) == (
        "Qual script está falhando?",
        "Qual erro foi observado?",
    )


def test_propose_plan_preserves_all_unresolved_goal_questions() -> None:
    provider = FakePlanProvider()
    goal = Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem a falha relatada."},
        success_criteria=({"description": "A falha original não é reproduzida."},),
    )

    result = propose_plan(
        provider,
        model="fake-model",
        goal=goal,
        open_questions=(
            "Qual script está falhando?",
            "Qual erro foi observado?",
        ),
    )

    assert result.output.open_questions == [
        "Qual script está falhando?",
        "Qual erro foi observado?",
    ]
