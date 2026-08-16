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

