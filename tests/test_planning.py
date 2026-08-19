from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from simon.context import CognitiveContext
from simon.events import Event, append_event
from simon.goal_intake import get_goal_acceptance_open_questions
from simon.goal_verification import GoalAssessmentContext
from simon.goals import Goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.plan_failure import PlanFailureContext
from simon.planning import (
    PlanIntentDraft,
    PlanIntentStep,
    PlanProposal,
    PlanStepProposal,
    compile_plan_intent,
    propose_plan,
)
from simon.storage import initialize_storage


class FakeIntentProvider:
    def __init__(self, intent: PlanIntentDraft | None = None) -> None:
        self.calls = 0
        self.system = ""
        self.prompt = ""
        self.response_model: type[BaseModel] | None = None
        self.intent = intent or PlanIntentDraft(
            summary="Entender, corrigir e validar o script.",
            steps=[
                PlanIntentStep(
                    subject="Obter o código atual do script.",
                    role="COLLECT",
                    source="USER",
                    verification="O código atual foi fornecido.",
                ),
                PlanIntentStep(
                    subject="Analisar o código e a falha observada.",
                    role="ANALYZE",
                    verification="Existe uma análise registrada da causa provável.",
                ),
                PlanIntentStep(
                    subject="Aplicar a correção necessária ao script.",
                    role="CHANGE",
                    verification="A alteração necessária foi produzida.",
                ),
                PlanIntentStep(
                    subject="Executar novamente o script após a correção.",
                    role="EXECUTE",
                    verification="Existe uma nova saída de execução.",
                ),
                PlanIntentStep(
                    subject="Analisar a nova saída e comparar com os critérios do Goal.",
                    role="ANALYZE",
                    verification="A nova execução foi avaliada.",
                ),
            ],
            open_questions=[],
        )

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
        self.calls += 1
        self.system = system or ""
        self.prompt = prompt
        self.response_model = response_model
        assert isinstance(self.intent, response_model)
        return StructuredModelResult(
            model=model,
            output=self.intent,
            prompt_eval_count=100,
            eval_count=40,
            total_duration_ns=500,
        )


def _goal() -> Goal:
    return Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem erros."},
        success_criteria=({"description": "A execução termina sem erro."},),
    )


def test_propose_plan_requests_intent_instead_of_operational_plan() -> None:
    provider = FakeIntentProvider()
    goal = _goal()

    result = propose_plan(
        provider,
        model="fake-model",
        goal=goal,
        context=CognitiveContext(goals=(goal,), entities=(), claims=(), memories=()),
    )

    assert provider.calls == 1
    assert provider.response_model is PlanIntentDraft
    assert result.output.steps[0].intent_role == "COLLECT"
    assert result.output.steps[0].intent_actor == "USER"


def test_planner_contract_moves_operational_fields_to_core() -> None:
    provider = FakeIntentProvider()

    propose_plan(provider, model="fake-model", goal=_goal())

    assert "Não escolha capability, kind, depends_on, preconditions" in provider.system
    assert "Cada passo declara apenas subject, role, source e verification" in provider.system
    assert "Source só existe em COLLECT" in provider.system
    assert "Não delegue ao usuário análise, mudança, execução, correção ou teste" in provider.system
    assert "subject nomeia o objeto do trabalho e nunca é uma instrução operacional" in provider.system
    assert "o Core compila esses campos depois" in provider.system
    assert "Não omita trabalho necessário" in provider.system
    assert "disponibilidade operacional é problema do Core" in provider.system
    assert "capability_catalog" not in provider.prompt


def test_intent_compiler_maps_user_collect_to_user_ask() -> None:
    proposal = compile_plan_intent(
        PlanIntentDraft(
            summary="Coletar informação.",
            steps=[
                PlanIntentStep(
                    subject="Obter a mensagem de erro atual.",
                    role="COLLECT",
                    source="USER",
                    verification="A mensagem foi fornecida.",
                )
            ],
        )
    )

    step = proposal.steps[0]
    assert step.id == "step_01"
    assert step.kind == "EPISTEMIC"
    assert step.capability == "user.ask"
    assert step.preconditions == []


def test_intent_compiler_generates_collect_description_instead_of_reusing_model_text() -> None:
    subject = "a saída e os logs completos de uma execução já realizada"
    proposal = compile_plan_intent(
        PlanIntentDraft(
            summary="Coletar evidência existente.",
            steps=[
                PlanIntentStep(
                    subject=subject,
                    role="COLLECT",
                    source="USER",
                    verification="Os logs existentes foram fornecidos.",
                )
            ],
        )
    )

    step = proposal.steps[0]
    assert step.description == (
        "Obter do usuário informação ou evidência já existente sobre: " + subject
    )
    assert "Solicitar ao usuário que execute" not in step.description
    assert step.capability == "user.ask"


def test_intent_compiler_generates_execute_description_from_typed_role() -> None:
    subject = "o script para produzir uma nova saída observável"
    proposal = compile_plan_intent(
        PlanIntentDraft(
            summary="Produzir nova execução.",
            steps=[
                PlanIntentStep(
                    subject=subject,
                    role="EXECUTE",
                    verification="Existe uma nova saída de execução.",
                )
            ],
        )
    )

    step = proposal.steps[0]
    assert step.description == "Executar: " + subject
    assert step.capability == "process.run"
    assert step.kind == "WORLD"
    assert step.intent_actor == "SIMON"


@pytest.mark.parametrize("role", ["ANALYZE", "CHANGE", "EXECUTE"])
def test_intent_step_rejects_source_for_substantive_roles(role: str) -> None:
    with pytest.raises(ValidationError, match="não aceita source"):
        PlanIntentStep(
            subject="Trabalho substantivo do Goal.",
            role=role,  # type: ignore[arg-type]
            source="USER",
            verification="Existe evidência do efeito.",
        )


def test_intent_step_requires_source_for_collect() -> None:
    with pytest.raises(ValidationError, match="COLLECT exige source"):
        PlanIntentStep(
            subject="Uma evidência já existente.",
            role="COLLECT",
            verification="A evidência foi obtida.",
        )


def test_intent_compiler_maps_simon_analyze_to_cognition() -> None:
    proposal = compile_plan_intent(
        PlanIntentDraft(
            summary="Analisar.",
            steps=[
                PlanIntentStep(
                    subject="Analisar o código e o erro disponíveis.",
                    role="ANALYZE",
                    verification="Uma conclusão analítica foi registrada.",
                )
            ],
        )
    )

    assert proposal.steps[0].kind == "EPISTEMIC"
    assert proposal.steps[0].capability == "cognition.analyze"


def test_intent_compiler_maps_simon_execute_to_process_run() -> None:
    proposal = compile_plan_intent(
        PlanIntentDraft(
            summary="Executar.",
            steps=[
                PlanIntentStep(
                    subject="Executar o script localmente.",
                    role="EXECUTE",
                    verification="O processo produziu uma saída observável.",
                )
            ],
        )
    )

    assert proposal.steps[0].kind == "WORLD"
    assert proposal.steps[0].capability == "process.run"


def test_intent_compiler_exposes_simon_change_as_unknown_capability() -> None:
    purpose = "Modificar o conteúdo do script para corrigir a causa identificada."
    proposal = compile_plan_intent(
        PlanIntentDraft(
            summary="Corrigir.",
            steps=[
                PlanIntentStep(
                    subject=purpose,
                    role="CHANGE",
                    verification="A versão modificada do script existe.",
                )
            ],
        )
    )

    step = proposal.steps[0]
    assert step.kind == "WORLD"
    assert step.capability == "unknown"
    assert step.capability_detail == purpose


def test_intent_compiler_exposes_unspecified_simon_collection_as_unknown() -> None:
    purpose = "Obter evidência externa ainda não acessível ao SIMON."
    proposal = compile_plan_intent(
        PlanIntentDraft(
            summary="Coletar.",
            steps=[
                PlanIntentStep(
                    subject=purpose,
                    role="COLLECT",
                    source="SIMON",
                    verification="A evidência foi obtida.",
                )
            ],
        )
    )

    assert proposal.steps[0].kind == "EPISTEMIC"
    assert proposal.steps[0].capability == "unknown"
    assert proposal.steps[0].capability_detail == purpose


def test_intent_compiler_builds_serial_dependencies_by_construction() -> None:
    proposal = compile_plan_intent(FakeIntentProvider().intent)

    assert [step.id for step in proposal.steps] == [
        "step_01",
        "step_02",
        "step_03",
        "step_04",
        "step_05",
    ]
    assert proposal.steps[0].depends_on == []
    assert proposal.steps[1].depends_on == ["step_01"]
    assert proposal.steps[2].depends_on == ["step_02"]
    assert proposal.steps[3].depends_on == ["step_03"]
    assert proposal.steps[4].depends_on == ["step_04"]


def test_intent_compiler_does_not_generate_textual_preconditions() -> None:
    proposal = compile_plan_intent(FakeIntentProvider().intent)

    assert all(step.preconditions == [] for step in proposal.steps)


def test_plan_description_is_human_text_not_semantic_protocol() -> None:
    proposal = PlanProposal(
        summary="Descrição não governa os campos operacionais.",
        steps=[
            PlanStepProposal(
                id="step_01",
                description="Executar o script corrigido após as alterações aplicadas.",
                kind="WORLD",
                capability="user.perform",
                verification="Uma nova saída foi produzida.",
            )
        ],
    )

    assert proposal.steps[0].description.startswith("Executar o script corrigido")


def test_plan_proposal_rejects_dependency_on_future_step() -> None:
    with pytest.raises(ValidationError, match="passo step_01 depende de passo ainda não definido"):
        PlanProposal(
            summary="Plano inválido.",
            steps=[
                PlanStepProposal(
                    id="step_01",
                    description="Primeiro passo.",
                    kind="EPISTEMIC",
                    depends_on=["step_02"],
                    capability="cognition.analyze",
                    verification="Primeiro efeito.",
                ),
                PlanStepProposal(
                    id="step_02",
                    description="Segundo passo.",
                    kind="EPISTEMIC",
                    depends_on=["step_01"],
                    capability="cognition.analyze",
                    verification="Segundo efeito.",
                ),
            ],
        )


def test_plan_proposal_rejects_gap_in_serial_chain() -> None:
    with pytest.raises(ValidationError, match="não depende do passo imediatamente anterior step_01"):
        PlanProposal(
            summary="Plano inválido.",
            steps=[
                PlanStepProposal(
                    id="step_01",
                    description="Primeiro passo.",
                    kind="EPISTEMIC",
                    capability="cognition.analyze",
                    verification="Primeiro efeito.",
                ),
                PlanStepProposal(
                    id="step_02",
                    description="Segundo passo.",
                    kind="EPISTEMIC",
                    capability="cognition.analyze",
                    verification="Segundo efeito.",
                ),
            ],
        )


def test_plan_proposal_requires_detail_for_unknown_capability() -> None:
    with pytest.raises(ValidationError, match="capability unknown sem capability_detail"):
        PlanProposal(
            summary="Capability ausente.",
            steps=[
                PlanStepProposal(
                    id="step_01",
                    description="Realizar trabalho ainda não catalogado.",
                    kind="WORLD",
                    capability="unknown",
                    verification="O efeito foi observado.",
                )
            ],
        )


def test_plan_proposal_rejects_user_perform_as_epistemic() -> None:
    with pytest.raises(ValidationError, match="user.perform, mas não é WORLD"):
        PlanProposal(
            summary="Contrato inválido.",
            steps=[
                PlanStepProposal(
                    id="step_01",
                    description="Executar uma ação externa.",
                    kind="EPISTEMIC",
                    capability="user.perform",
                    verification="A ação foi relatada.",
                )
            ],
        )


def test_compiled_intent_provenance_must_match_operational_fields() -> None:
    with pytest.raises(ValidationError, match="capability compilada"):
        PlanProposal(
            summary="Proveniência incompatível.",
            steps=[
                PlanStepProposal(
                    id="step_01",
                    description="Analisar dados.",
                    kind="EPISTEMIC",
                    capability="user.ask",
                    verification="Análise registrada.",
                    intent_role="ANALYZE",
                    intent_actor="SIMON",
                )
            ],
        )


def test_compiled_intent_cannot_acquire_preconditions_after_compilation() -> None:
    with pytest.raises(ValidationError, match="não pode possuir preconditions"):
        PlanProposal(
            summary="Proveniência compilada.",
            steps=[
                PlanStepProposal(
                    id="step_01",
                    description="Analisar dados.",
                    kind="EPISTEMIC",
                    preconditions=["Alguma condição textual."],
                    capability="cognition.analyze",
                    verification="Análise registrada.",
                    intent_role="ANALYZE",
                    intent_actor="SIMON",
                )
            ],
        )


def test_propose_plan_preserves_unresolved_goal_questions() -> None:
    provider = FakeIntentProvider(
        PlanIntentDraft(
            summary="Coletar o que falta.",
            steps=[
                PlanIntentStep(
                    subject="Obter a informação ausente.",
                    role="COLLECT",
                    source="USER",
                    verification="A informação foi fornecida.",
                )
            ],
            open_questions=["Qual erro aparece agora?"],
        )
    )

    result = propose_plan(
        provider,
        model="fake-model",
        goal=_goal(),
        open_questions=("Qual script está falhando?", "Qual erro aparece agora?"),
    )

    assert result.output.open_questions == [
        "Qual script está falhando?",
        "Qual erro aparece agora?",
    ]


def test_propose_plan_uses_prior_goal_assessment_as_continuation_feedback() -> None:
    provider = FakeIntentProvider()
    goal = _goal()
    evidence = Event.create(
        kind="user.response.received",
        source="user",
        payload={
            "step_id": "step_03",
            "response": "NameError: resultado is not defined",
        },
        goal_id=goal.id,
    )
    assessment = GoalAssessmentContext(
        verification_id="ver_goal_assessment",
        verdict="INSUFFICIENT_EVIDENCE",
        plan_id="pln_previous",
        plan_revision=2,
        criterion_assessments=(
            {
                "criterion_index": 1,
                "verdict": "INSUFFICIENT_EVIDENCE",
                "rationale": "Falta uma execução posterior sem erro.",
                "supporting_step_ids": ["step_03"],
            },
        ),
        missing_evidence=("Registro de execução após a correção.",),
        evidence_events=(evidence,),
    )

    propose_plan(
        provider,
        model="fake-model",
        goal=goal,
        goal_assessment=assessment,
    )

    assert "prior_goal_assessment" in provider.prompt
    assert "ver_goal_assessment" in provider.prompt
    assert "Registro de execução após a correção." in provider.prompt
    assert "NameError: resultado is not defined" in provider.prompt
    assert "verified_user_responses" in provider.prompt
    assert '"step_id":"step_03"' in provider.prompt
    assert "não repita evidência já presente" in provider.system
    assert "não crie COLLECT/USER para pedir novamente o mesmo dado" in provider.system


def test_goal_acceptance_open_questions_are_recoverable_for_planning(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal()
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


def test_propose_plan_uses_active_plan_failure_as_replanning_feedback() -> None:
    provider = FakeIntentProvider()
    goal = _goal()
    evidence = Event.create(
        kind="cognition.analysis.completed",
        source="cognition",
        payload={"summary": "A hipótese atual não explica a falha."},
        goal_id=goal.id,
    )
    failure = PlanFailureContext(
        plan_id="pln_active",
        plan_revision=3,
        step_id="step_02",
        step_description="Analisar a falha observada.",
        capability="cognition.analyze",
        blocker_kind="CRITERION_NOT_SATISFIED",
        action_id="act_analysis",
        action_kind="cognition.analyze",
        verification_id="ver_failed_assessment",
        verification_status="ASSESSED",
        verification_criteria=({"description": "A hipótese explica a falha."},),
        verification_observed={
            "verdict": "NOT_SATISFIED",
            "rationale": "A hipótese não foi sustentada.",
        },
        evidence_events=(evidence,),
    )

    propose_plan(
        provider,
        model="fake-model",
        goal=goal,
        plan_failure=failure,
    )

    assert "prior_plan_failure" in provider.prompt
    assert "ver_failed_assessment" in provider.prompt
    assert "CRITERION_NOT_SATISFIED" in provider.prompt
    assert "A hipótese atual não explica a falha." in provider.prompt
    assert "replanejamento explícito" in provider.system
