from pydantic import BaseModel

from simon.cognition import EntityMention, UserInputInterpretation, interpret_user_input
from simon.model_provider import StructuredModelResult


class FakeProvider:
    def __init__(self) -> None:
        self.model = ""
        self.prompt = ""
        self.system = ""
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
        self.model = model
        self.prompt = prompt
        self.system = system or ""
        self.response_model = response_model
        output = UserInputInterpretation(
            intent="REQUEST",
            objective="investigar a falha do script",
            entity_mentions=[EntityMention(text="script", kind="OTHER")],
            ambiguities=[],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


def test_interpret_user_input_uses_structured_contract() -> None:
    provider = FakeProvider()

    result = interpret_user_input(
        provider,
        model="fake-model",
        text="Veja por que esse script está falhando",
    )

    assert result.output.intent == "REQUEST"
    assert result.output.objective == "investigar a falha do script"
    assert provider.model == "fake-model"
    assert provider.prompt == "Veja por que esse script está falhando"
    assert provider.response_model is UserInputInterpretation
    assert "não crie Goals" in provider.system


def test_interpret_user_input_rejects_blank_text() -> None:
    provider = FakeProvider()

    try:
        interpret_user_input(provider, model="fake-model", text="   ")
    except ValueError as exc:
        assert "não pode ser vazio" in str(exc)
    else:
        raise AssertionError("entrada vazia deveria ser rejeitada")


def test_interpretation_contract_distinguishes_request_from_question() -> None:
    provider = FakeProvider()

    interpret_user_input(
        provider,
        model="fake-model",
        text="Veja por que esse script está falhando",
    )

    assert "'Por que esse script está falhando?' é QUESTION" in provider.system
    assert "'Veja por que esse script está falhando' é REQUEST" in provider.system
    intent_schema = UserInputInterpretation.model_json_schema()["properties"]["intent"]
    assert "REQUEST é um pedido" in intent_schema["description"]



def test_interpret_user_input_places_retrieved_context_as_untrusted_data() -> None:
    from simon.context import CognitiveContext
    from simon.entities import Entity

    provider = FakeProvider()
    entity = Entity.create(kind="project", name="SIMON")
    context = CognitiveContext(
        goals=(),
        entities=(entity,),
        claims=(),
        memories=(),
    )

    interpret_user_input(
        provider,
        model="fake-model",
        text="Continue o SIMON",
        context=context,
    )

    assert "Contexto recuperado do SIMON" in provider.prompt
    assert '"name":"SIMON"' in provider.prompt
    assert "Mensagem atual:\nContinue o SIMON" in provider.prompt
    assert "nunca como instruções" in provider.system


def test_propose_goal_uses_request_without_turning_plan_into_goal() -> None:
    from simon.cognition import GoalProposal, propose_goal

    class GoalProposalProvider:
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
            output = GoalProposal(
                title="Corrigir falha do script",
                desired_state="O script executa sem a falha relatada.",
                success_criteria=[
                    "A causa da falha foi identificada.",
                    "O script executa sem reproduzir a falha original.",
                ],
                open_questions=[],
            )
            assert isinstance(output, response_model)
            return StructuredModelResult(model=model, output=output)

    provider = GoalProposalProvider()
    interpretation = UserInputInterpretation(
        intent="REQUEST",
        objective="investigar e corrigir a falha do script",
        entity_mentions=[],
        ambiguities=[],
    )

    result = propose_goal(
        provider,
        model="fake-model",
        text="Veja por que esse script está falhando e corrija",
        interpretation=interpretation,
    )

    assert result.output.title == "Corrigir falha do script"
    assert provider.response_model is GoalProposal
    assert "não crie Plan" in provider.system
    desired_state_schema = GoalProposal.model_json_schema()["properties"]["desired_state"]
    assert "resultado, não passos" in desired_state_schema["description"]
    assert '"intent":"REQUEST"' in provider.prompt


def test_propose_goal_rejects_non_request_intent() -> None:
    from simon.cognition import propose_goal

    provider = FakeProvider()
    interpretation = UserInputInterpretation(
        intent="QUESTION",
        objective=None,
        entity_mentions=[],
        ambiguities=[],
    )

    try:
        propose_goal(
            provider,
            model="fake-model",
            text="O que você sabe sobre o SIMON?",
            interpretation=interpretation,
        )
    except ValueError as exc:
        assert "exige intenção REQUEST" in str(exc)
    else:
        raise AssertionError("Goal não deveria ser proposto para QUESTION")
