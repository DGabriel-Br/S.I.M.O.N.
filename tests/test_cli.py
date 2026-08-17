import json
import sqlite3
import sys
from pathlib import Path

from simon.actions import create_action, get_action, list_actions_for_plan, transition_action
from simon.cli import main
from simon.entities import SIMON_ENTITY_ID
from simon.experiences import create_experience, get_experience
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.storage import initialize_storage


def test_main_initializes_storage_and_records_current_world_state(
    tmp_path: Path,
    capsys: object,
) -> None:
    result = main(["--data-dir", str(tmp_path)])

    assert result == 0
    database_path = tmp_path / "simon.db"
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        entity = connection.execute(
            "SELECT kind, name FROM entities WHERE id = ?",
            (SIMON_ENTITY_ID,),
        ).fetchone()
        event = connection.execute(
            """
            SELECT id, kind, source, related_entity_ids_json
            FROM events
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        ).fetchone()
        claim = connection.execute(
            """
            SELECT predicate, value_json, epistemic_status, evidence_event_ids_json, status
            FROM claims
            WHERE subject_id = ? AND status = 'ACTIVE'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()

    assert entity == ("system", "SIMON")
    assert event is not None
    assert event[1:3] == ("system.started", "system")
    assert tuple(json.loads(str(event[3]))) == (SIMON_ENTITY_ID,)

    assert claim is not None
    assert claim[0] == "storage.schema_version"
    assert json.loads(str(claim[1])) == 10
    assert claim[2] == "DIRECT_OBSERVATION"
    assert tuple(json.loads(str(claim[3]))) == (str(event[0]),)
    assert claim[4] == "ACTIVE"


def test_repeated_startup_does_not_duplicate_same_current_claim(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(["--data-dir", str(tmp_path)]) == 0
    assert main(["--data-dir", str(tmp_path)]) == 0

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        claim_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM claims
            WHERE subject_id = ?
              AND predicate = 'storage.schema_version'
              AND status = 'ACTIVE'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'system.started'"
        ).fetchone()

    assert claim_count == (1,)
    assert event_count == (2,)


def test_startup_marks_previous_running_action_as_interrupted(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Testar recuperação",
        origin="USER",
        desired_state={"state": "recovered"},
        success_criteria=({"kind": "runtime_recovered"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=({"id": "step_1", "description": "Executar ação longa"},),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_1",
        kind="process.run",
    )
    transition_action(database_path, action.id, "RUNNING")

    assert main(["--data-dir", str(tmp_path)]) == 0

    restored = get_action(database_path, action.id)
    assert restored is not None
    assert restored.status == "INTERRUPTED"
    assert restored.failure is not None
    assert restored.failure["kind"] == "runtime_restart"


def test_startup_suspends_previous_active_experience(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience = create_experience(
        database_path,
        title="Investigar antes do reinício",
    )

    assert main(["--data-dir", str(tmp_path)]) == 0

    restored = get_experience(database_path, experience.id)
    assert restored is not None
    assert restored.status == "SUSPENDED"
    assert restored.outcome is None


def test_model_check_lists_local_models(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def list_models(self) -> tuple[str, ...]:
            return ("model-a:latest", "model-b:q4")

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(["--data-dir", str(tmp_path), "model-check"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Ollama: pronto" in output
    assert "model-a:latest" in output
    assert "model-b:q4" in output



def test_interpret_records_input_and_structured_result(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.cognition import EntityMention, UserInputInterpretation
    from simon.model_provider import StructuredModelResult

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(
            self, **kwargs: object
        ) -> StructuredModelResult[UserInputInterpretation]:
            return StructuredModelResult(
                model="fake-model",
                output=UserInputInterpretation(
                    intent="REQUEST",
                    objective="continuar o projeto SIMON",
                    entity_mentions=[EntityMention(text="SIMON", kind="PROJECT")],
                    ambiguities=[],
                ),
                prompt_eval_count=12,
                eval_count=8,
                total_duration_ns=2_000_000_000,
            )

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "interpret",
            "--model",
            "fake-model",
            "Vamos continuar o projeto SIMON",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Intenção: REQUEST" in output
    assert "Objetivo: continuar o projeto SIMON" in output
    assert "SIMON (PROJECT)" in output

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        rows = connection.execute(
            """
            SELECT kind, source, payload_json, trace_id
            FROM events
            WHERE kind IN ('user.input.received', 'cognition.interpretation.completed')
            ORDER BY occurred_at
            """
        ).fetchall()

    assert len(rows) == 2
    assert rows[0][0:2] == ("user.input.received", "user")
    assert json.loads(str(rows[0][2]))["text"] == "Vamos continuar o projeto SIMON"
    assert rows[1][0:2] == ("cognition.interpretation.completed", "cognition")
    assert json.loads(str(rows[1][2]))["interpretation"]["intent"] == "REQUEST"
    assert rows[0][3] == rows[1][3]


def test_interpret_records_context_selection_before_model_result(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.cognition import UserInputInterpretation
    from simon.model_provider import StructuredModelResult

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(
            self, **kwargs: object
        ) -> StructuredModelResult[UserInputInterpretation]:
            return StructuredModelResult(
                model="fake-model",
                output=UserInputInterpretation(
                    intent="QUESTION",
                    objective="consultar o estado do SIMON",
                    entity_mentions=[],
                    ambiguities=[],
                ),
            )

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "interpret",
            "--model",
            "fake-model",
            "O que você sabe sobre o SIMON?",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Contexto: 0 goal(s), 1 entity(s), 1 claim(s), 0 memory(s)" in output

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        row = connection.execute(
            """
            SELECT payload_json, trace_id
            FROM events
            WHERE kind = 'cognition.context.built'
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        ).fetchone()
        input_trace = connection.execute(
            """
            SELECT trace_id
            FROM events
            WHERE kind = 'user.input.received'
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    payload = json.loads(str(row[0]))
    assert payload["entity_ids"] == [SIMON_ENTITY_ID]
    assert len(payload["claim_ids"]) == 1
    assert input_trace is not None
    assert row[1] == input_trace[0]


def test_goal_propose_records_proposal_without_persisting_goal(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.cognition import GoalProposal, UserInputInterpretation
    from simon.model_provider import StructuredModelResult

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[object]:
            response_model = kwargs["response_model"]
            if response_model is UserInputInterpretation:
                return StructuredModelResult(
                    model="fake-model",
                    output=UserInputInterpretation(
                        intent="REQUEST",
                        objective="corrigir a falha do script",
                        entity_mentions=[],
                        ambiguities=[],
                    ),
                )
            if response_model is GoalProposal:
                return StructuredModelResult(
                    model="fake-model",
                    output=GoalProposal(
                        title="Corrigir falha do script",
                        desired_state="O script executa sem a falha relatada.",
                        success_criteria=["A falha original não é reproduzida."],
                        open_questions=[],
                    ),
                    prompt_eval_count=20,
                    eval_count=12,
                    total_duration_ns=1_500_000_000,
                )
            raise AssertionError("response_model inesperado")

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "goal-propose",
            "--model",
            "fake-model",
            "Veja por que esse script está falhando e corrija",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Intenção: REQUEST" in output
    assert "Título: Corrigir falha do script" in output
    assert "ID da proposta: evt_" in output
    assert "Goal persistido: não" in output

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        goal_count = connection.execute("SELECT COUNT(*) FROM goals").fetchone()
        rows = connection.execute(
            """
            SELECT kind, payload_json, trace_id
            FROM events
            WHERE kind IN (
                'user.input.received',
                'cognition.context.built',
                'cognition.interpretation.completed',
                'cognition.goal_proposal.completed'
            )
            ORDER BY occurred_at
            """
        ).fetchall()

    assert goal_count == (0,)
    assert [row[0] for row in rows] == [
        "user.input.received",
        "cognition.context.built",
        "cognition.interpretation.completed",
        "cognition.goal_proposal.completed",
    ]
    proposal_payload = json.loads(str(rows[-1][1]))
    assert proposal_payload["proposal"]["title"] == "Corrigir falha do script"
    assert len({str(row[2]) for row in rows}) == 1


def test_goal_accept_cli_persists_selected_proposal(
    tmp_path: Path,
    capsys: object,
) -> None:
    from simon.cognition import GoalProposal
    from simon.events import Event, append_event

    database_path, _ = initialize_storage(tmp_path)
    proposal = GoalProposal(
        title="Corrigir falha no script",
        desired_state="O script executa sem reproduzir a falha relatada.",
        success_criteria=["A falha original não é reproduzida."],
        open_questions=[],
    )
    proposal_event = Event.create(
        kind="cognition.goal_proposal.completed",
        source="cognition",
        payload={
            "model": "fake-model",
            "proposal": proposal.model_dump(mode="json"),
        },
        trace_id="trc_source",
    )
    append_event(database_path, proposal_event)

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "goal-accept",
            proposal_event.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Origem: USER" in output
    assert "Status: ACTIVE" in output
    assert "Goal persistido: sim" in output

    with sqlite3.connect(database_path) as connection:
        goal = connection.execute(
            "SELECT title, origin, status FROM goals"
        ).fetchone()

    assert goal == ("Corrigir falha no script", "USER", "ACTIVE")


def test_plan_propose_records_strategy_without_persisting_plan(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.events import Event, append_event
    from simon.model_provider import StructuredModelResult
    from simon.planning import PlanIntentDraft, PlanIntentStep

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem erros."},
        success_criteria=({"description": "A falha original não é reproduzida."},),
    )
    insert_goal(database_path, goal)
    append_event(
        database_path,
        Event.create(
            kind="goal.proposal.accepted",
            source="user",
            payload={
                "proposal_event_id": "evt_source",
                "open_questions": ["Qual script está falhando?"],
            },
            goal_id=goal.id,
        ),
    )

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[PlanIntentDraft]:
            assert kwargs["response_model"] is PlanIntentDraft
            return StructuredModelResult(
                model="fake-model",
                output=PlanIntentDraft(
                    summary="Coletar evidência antes da correção.",
                    steps=[
                        PlanIntentStep(
                            subject="Identificar o script e a falha observada.",
                            role="COLLECT",
                            source="USER",
                            verification="Script e erro foram identificados.",
                        )
                    ],
                    open_questions=["Qual script está falhando?"],
                ),
                prompt_eval_count=30,
                eval_count=18,
                total_duration_ns=1_200_000_000,
            )

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "plan-propose",
            "--model",
            "fake-model",
            goal.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Goal: {goal.id}" in output
    assert "step_01 [EPISTEMIC]" in output
    assert "Intent: COLLECT / USER" in output
    assert "ID da proposta: evt_" in output
    assert "Plan persistido: não" in output

    with sqlite3.connect(database_path) as connection:
        plan_count = connection.execute("SELECT COUNT(*) FROM plans").fetchone()
        rows = connection.execute(
            """
            SELECT kind, payload_json, trace_id, goal_id
            FROM events
            WHERE kind IN ('cognition.context.built', 'cognition.plan_proposal.completed')
              AND goal_id = ?
            ORDER BY occurred_at
            """,
            (goal.id,),
        ).fetchall()

    assert plan_count == (0,)
    assert [row[0] for row in rows] == [
        "cognition.context.built",
        "cognition.plan_proposal.completed",
    ]
    assert json.loads(str(rows[0][1]))["purpose"] == "plan"
    proposal_payload = json.loads(str(rows[1][1]))
    assert proposal_payload["source_open_questions"] == ["Qual script está falhando?"]
    assert proposal_payload["proposal"]["steps"][0]["kind"] == "EPISTEMIC"
    assert rows[0][2] == rows[1][2]
    assert rows[0][3] == goal.id
    assert rows[1][3] == goal.id


def test_plan_materialize_cli_persists_selected_proposal(
    tmp_path: Path,
    capsys: object,
) -> None:
    from simon.events import Event, append_event
    from simon.planning import PlanProposal, PlanStepProposal

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem erros."},
        success_criteria=({"description": "A falha não é reproduzida."},),
    )
    insert_goal(database_path, goal)
    proposal = PlanProposal(
        summary="Obter informação antes de agir.",
        steps=[
            PlanStepProposal(
                id="step_01",
                description="Solicitar o script e o erro ao usuário.",
                kind="EPISTEMIC",
                capability="user.ask",
                verification="Script e erro foram registrados.",
            )
        ],
        open_questions=["Qual script está falhando?"],
    )
    proposal_event = Event.create(
        kind="cognition.plan_proposal.completed",
        source="cognition",
        payload={
            "model": "fake-model",
            "proposal": proposal.model_dump(mode="json"),
        },
        trace_id="trc_source",
        goal_id=goal.id,
    )
    append_event(database_path, proposal_event)

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "plan-materialize",
            proposal_event.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Goal: {goal.id}" in output
    assert "Revisão: 1" in output
    assert "Status: ACTIVE" in output
    assert "Plan persistido: sim" in output

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "plan-materialize",
            proposal_event.id,
        ]
    ) == 0
    repeated_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Plan persistido: já existia para esta proposta" in repeated_output


def test_plan_next_reports_blockers_without_creating_action(
    tmp_path: Path,
    capsys: object,
) -> None:
    from simon.actions import list_actions_for_plan

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem erros."},
        success_criteria=({"description": "A falha não é reproduzida."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Obter o conteúdo do script.",
                "capability": "filesystem.read",
                "preconditions": ["O caminho do script foi confirmado."],
            },
        ),
    )

    assert main(["--data-dir", str(tmp_path), "plan-next", goal.id]) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Plan: {plan.id}" in output
    assert (
        "Capabilities executáveis registradas: cognition.analyze, file.patch, process.run, user.ask"
        in output
    )
    assert "Próximo passo executável: nenhum" in output
    assert "PRECONDITION_UNRESOLVED" in output
    assert "CAPABILITY_UNAVAILABLE" in output
    assert "Action criada: não" in output
    assert list_actions_for_plan(database_path, plan.id) == ()

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT payload_json, goal_id
            FROM events
            WHERE kind = 'plan.readiness.evaluated'
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    payload = json.loads(str(row[0]))
    assert row[1] == goal.id
    assert payload["plan_id"] == plan.id
    assert payload["available_capabilities"] == [
        "cognition.analyze",
        "file.patch",
        "process.run",
        "user.ask",
    ]
    assert payload["next_step_id"] is None
    assert payload["steps"][0]["step_id"] == "step_01"


def test_cli_user_ask_waits_across_restart_and_records_answer(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Obter erro do usuário",
        origin="USER",
        desired_state={"description": "erro disponível"},
        success_criteria=({"description": "erro informado"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar ao usuário a mensagem de erro.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece a mensagem de erro.",
            },
        ),
    )

    assert main(["--data-dir", str(tmp_path), "plan-ask", goal.id]) == 0
    first_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Status: WAITING" in first_output
    assert "Action criada: sim" in first_output

    actions = list_actions_for_plan(database_path, plan.id)
    assert len(actions) == 1
    action_id = actions[0].id

    assert main(["--data-dir", str(tmp_path)]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]
    restored = get_action(database_path, action_id)
    assert restored is not None
    assert restored.status == "WAITING"

    assert main(["--data-dir", str(tmp_path), "plan-ask", goal.id]) == 0
    second_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Action: {action_id}" in second_output
    assert "Action criada: não (já aguardava resposta)" in second_output

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "action-answer",
            action_id,
            "ValueError: arquivo ausente",
        ]
    ) == 0
    answer_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Status: COMPLETED" in answer_output
    assert "Verification criada: não" in answer_output

    completed = get_action(database_path, action_id)
    assert completed is not None
    assert completed.status == "COMPLETED"


def test_action_assess_cli_persists_assessment_without_promoting_to_verified(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.model_provider import StructuredModelResult
    from simon.user_ask import answer_user_ask, dispatch_next_user_ask
    from simon.user_ask_verification import UserAskCriterionAssessment

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Obter script",
        origin="USER",
        desired_state={"description": "conteúdo do script disponível"},
        success_criteria=({"description": "script recebido"},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar ao usuário o conteúdo do script.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece o código ou arquivo do script.",
            },
        ),
    )
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer_user_ask(
        database_path,
        action_id=dispatch.action.id,
        response="Ainda não forneci o conteúdo do script.",
    )

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[object]:
            return StructuredModelResult(
                model="fake-model",
                output=UserAskCriterionAssessment(
                    verdict="NOT_SATISFIED",
                    rationale="A resposta afirma que o conteúdo ainda não foi fornecido.",
                    missing_information=["conteúdo do script"],
                ),
                prompt_eval_count=20,
                eval_count=8,
                total_duration_ns=500_000_000,
            )

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "action-assess",
            "--model",
            "fake-model",
            dispatch.action.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Veredito: NOT_SATISFIED" in output
    assert "Status persistido: ASSESSED" in output
    assert "Assessment criada: sim" in output

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT status, observed_json FROM verification_results WHERE subject_id = ?",
            (dispatch.action.id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "ASSESSED"
    observed = json.loads(str(row[1]))
    assert observed["verdict"] == "NOT_SATISFIED"


def test_action_retry_cli_creates_reviewed_waiting_attempt(
    tmp_path: Path,
    capsys: object,
) -> None:
    from simon.user_ask import answer_user_ask, dispatch_next_user_ask
    from simon.verification import create_verification_result

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Obter script",
        origin="USER",
        desired_state={"description": "conteúdo do script disponível"},
        success_criteria=({"description": "script recebido"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar ao usuário o conteúdo do script.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece o código ou arquivo do script.",
            },
        ),
    )
    first = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer = answer_user_ask(
        database_path,
        action_id=first.action.id,
        response="Ainda não tenho o script.",
    )
    review = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=first.action.id,
        criteria=({"description": "O usuário fornece o código ou arquivo do script."},),
        status="ASSESSED",
        evidence_event_ids=(answer.response_event_id,),
        observed={
            "assessment_type": "user.ask.semantic",
            "verdict": "NOT_SATISFIED",
            "response_event_id": answer.response_event_id,
            "model": "fake-model",
        },
        strength=2,
    )

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "action-retry",
            first.action.id,
            "Cole",
            "o",
            "script",
            "completo.",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Action anterior: {first.action.id}" in output
    assert f"Verification de review: {review.id}" in output
    assert "Status: WAITING" in output
    assert "Solicitação: Cole o script completo." in output
    assert "Retry criado: sim" in output

    actions = list_actions_for_plan(database_path, plan.id)
    assert len(actions) == 2
    assert actions[-1].status == "WAITING"
    assert actions[-1].input_data["retry_of_action_id"] == first.action.id

    assert main(
        ["--data-dir", str(tmp_path), "action-retry", first.action.id]
    ) == 0
    repeated_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Action: {actions[-1].id}" in repeated_output
    assert "Retry criado: não (já aguardava resposta)" in repeated_output


def test_verification_confirm_cli_promotes_satisfied_assessment(
    tmp_path: Path,
    capsys: object,
) -> None:
    from simon.user_ask import answer_user_ask, dispatch_next_user_ask
    from simon.verification import create_verification_result

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Obter script",
        origin="USER",
        desired_state={"description": "conteúdo do script disponível"},
        success_criteria=({"description": "script recebido"},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar ao usuário o conteúdo do script.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece o código ou arquivo do script.",
            },
        ),
    )
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer = answer_user_ask(
        database_path,
        action_id=dispatch.action.id,
        response="print('ok')",
    )
    assessment = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=dispatch.action.id,
        criteria=({"description": "O usuário fornece o código ou arquivo do script."},),
        status="ASSESSED",
        evidence_event_ids=(answer.response_event_id,),
        observed={
            "assessment_type": "user.ask.semantic",
            "verdict": "SATISFIED",
            "response_event_id": answer.response_event_id,
            "model": "fake-model",
        },
        strength=2,
    )

    assert main(
        ["--data-dir", str(tmp_path), "verification-confirm", assessment.id]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Assessment: {assessment.id}" in output
    assert f"Action: {dispatch.action.id}" in output
    assert "Veredito avaliado: SATISFIED" in output
    assert "Status persistido: VERIFIED" in output
    assert "Verification confirmada: sim" in output

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT status, observed_json FROM verification_results WHERE subject_id = ? ORDER BY created_at",
            (dispatch.action.id,),
        ).fetchall()

    assert [row[0] for row in rows] == ["ASSESSED", "VERIFIED"]
    confirmed = json.loads(str(rows[-1][1]))
    assert confirmed["confirmed_assessment_id"] == assessment.id
    assert confirmed["confirmed_by"] == "user"


def test_cli_plan_complete_finishes_verified_plan_without_goal(
    tmp_path: Path,
    capsys: object,
) -> None:
    from simon.events import Event, append_event
    from simon.verification import create_verification_result

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Concluir plan",
        origin="USER",
        desired_state={"description": "plan executado"},
        success_criteria=({"description": "resultado observado"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar passo",
                "capability": "test.capability",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="test.capability",
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(database_path, action.id, "COMPLETED", reported_result={"ok": True})
    evidence = Event.create(kind="test.plan.complete", source="test", goal_id=goal.id)
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "passo verificado"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"ok": True},
        strength=2,
    )

    assert main(["--data-dir", str(tmp_path), "plan-complete", goal.id]) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Plan: {plan.id}" in output
    assert "Status: COMPLETED" in output
    assert "Steps verificados: 1" in output
    assert "Plan concluído: sim" in output
    assert "Goal alterado: não" in output


def test_goal_assess_cli_persists_assessed_without_completing_goal(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.events import Event, append_event
    from simon.goal_verification import GoalCriterionAssessment, GoalEvidenceAssessment
    from simon.model_provider import StructuredModelResult
    from simon.plan_completion import complete_verified_plan
    from simon.verification import create_verification_result

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Corrigir script",
        origin="USER",
        desired_state={"description": "O script executa sem erro."},
        success_criteria=(
            {"description": "A execução conclui com sucesso."},
            {"description": "Não ocorre mensagem de erro."},
        ),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Coletar erro",
                "verification": "erro coletado",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="test.observe",
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(database_path, action.id, "COMPLETED", reported_result={"ok": True})
    evidence = Event.create(
        kind="test.error.observed",
        source="test",
        payload={"error": "NameError"},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "erro coletado"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"ok": True},
        strength=3,
    )
    complete_verified_plan(database_path, goal_id=goal.id)

    class FakeProvider:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[object]:
            return StructuredModelResult(
                model="fake-model",
                output=GoalEvidenceAssessment(
                    criteria=[
                        GoalCriterionAssessment(
                            criterion_index=1,
                            verdict="INSUFFICIENT_EVIDENCE",
                            rationale="Não houve nova execução bem-sucedida.",
                            supporting_step_ids=[],
                        ),
                        GoalCriterionAssessment(
                            criterion_index=2,
                            verdict="NOT_SATISFIED",
                            rationale="A evidência contém NameError.",
                            supporting_step_ids=["step_01"],
                        ),
                    ],
                    missing_evidence=["Uma execução posterior sem erro."],
                ),
                prompt_eval_count=40,
                eval_count=16,
                total_duration_ns=1_000_000_000,
            )

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "goal-assess",
            "--model",
            "fake-model",
            goal.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Goal: {goal.id} (Corrigir script)" in output
    assert f"Plan avaliado: {plan.id} (revisão 1)" in output
    assert "Veredito geral: NOT_SATISFIED" in output
    assert "Status persistido: ASSESSED" in output
    assert "Goal alterado: não" in output
    assert "Assessment criada: sim" in output

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT status FROM goals WHERE id = ?",
            (goal.id,),
        ).fetchone()
        verification = connection.execute(
            """
            SELECT status, observed_json
            FROM verification_results
            WHERE subject_type = 'GOAL' AND subject_id = ?
            """,
            (goal.id,),
        ).fetchone()

    assert row == ("ACTIVE",)
    assert verification is not None
    assert verification[0] == "ASSESSED"
    observed = json.loads(str(verification[1]))
    assert observed["verdict"] == "NOT_SATISFIED"


def test_plan_propose_uses_goal_assessment_instead_of_stale_intake_questions(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.events import Event, append_event
    from simon.model_provider import StructuredModelResult
    from simon.planning import PlanIntentDraft, PlanIntentStep
    from simon.verification import create_verification_result

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem erros."},
        success_criteria=({"description": "A execução conclui sem erro."},),
    )
    insert_goal(database_path, goal)
    append_event(
        database_path,
        Event.create(
            kind="goal.proposal.accepted",
            source="user",
            payload={
                "proposal_event_id": "evt_source",
                "open_questions": ["Qual script está falhando?"],
            },
            goal_id=goal.id,
        ),
    )
    evidence = Event.create(
        kind="user.response.received",
        source="user",
        payload={"response": "NameError: resultado is not defined"},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    assessment = create_verification_result(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
        criteria=goal.success_criteria,
        status="ASSESSED",
        evidence_event_ids=(evidence.id,),
        observed={
            "assessment_type": "goal.semantic",
            "verdict": "INSUFFICIENT_EVIDENCE",
            "criterion_assessments": [
                {
                    "criterion_index": 1,
                    "verdict": "INSUFFICIENT_EVIDENCE",
                    "rationale": "Falta executar após a correção.",
                    "supporting_step_ids": [],
                }
            ],
            "missing_evidence": ["Execução posterior sem erro."],
            "plan_id": "pln_completed",
            "plan_revision": 2,
            "model": "assessment-model",
        },
        strength=2,
    )

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[PlanIntentDraft]:
            prompt = kwargs.get("prompt")
            assert isinstance(prompt, str)
            assert assessment.id in prompt
            assert "Execução posterior sem erro." in prompt
            assert "NameError: resultado is not defined" in prompt
            return StructuredModelResult(
                model="fake-model",
                output=PlanIntentDraft(
                    summary="Investigar e corrigir antes de reexecutar.",
                    steps=[
                        PlanIntentStep(
                            subject="Analisar a falha já observada.",
                            role="ANALYZE",
                            verification="Existe uma hipótese causal sustentada pela evidência.",
                        )
                    ],
                ),
            )

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "plan-propose",
            "--model",
            "fake-model",
            goal.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Assessment de continuação: {assessment.id} (INSUFFICIENT_EVIDENCE)" in output
    assert "Plan anterior avaliado: pln_completed (revisão 2)" in output

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT payload_json
            FROM events
            WHERE kind = 'cognition.plan_proposal.completed' AND goal_id = ?
            ORDER BY occurred_at DESC, id DESC
            LIMIT 1
            """,
            (goal.id,),
        ).fetchone()

    assert row is not None
    payload = json.loads(str(row[0]))
    assert payload["source_open_questions"] == []
    assert payload["source_goal_assessment_id"] == assessment.id
    assert payload["source_completed_plan_id"] == "pln_completed"


def test_cli_plan_patch_resolves_change_unknown_without_auto_verification(
    tmp_path: Path,
    capsys: object,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Corrigir script local",
        origin="USER",
        desired_state={"description": "script corrigido"},
        success_criteria=({"description": "arquivo modificado"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Realizar a mudança: corrigir variável",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "Correção localizada da variável",
                "verification": "Arquivo modificado e salvo.",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
        ),
    )

    assert main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "plan-patch",
            goal.id,
            "--workspace",
            str(workspace),
            "--file",
            "script.py",
            "--old",
            "valor = 1",
            "--new",
            "valor = 2",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Plan: {plan.id}" in output
    assert "Capability resolvida: file.patch" in output
    assert "Status: COMPLETED" in output
    assert "Verification criada: não" in output
    assert target.read_text(encoding="utf-8") == "valor = 2\n"

    actions = list_actions_for_plan(database_path, plan.id)
    assert len(actions) == 1
    assert actions[0].kind == "file.patch"
    assert actions[0].status == "COMPLETED"


def test_cli_plan_run_executes_next_process_step_without_auto_verification(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Executar script local",
        origin="USER",
        desired_state={"description": "execução observada"},
        success_criteria=({"description": "resultado registrado"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar script de teste.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "A execução produziu saída observável.",
            },
        ),
    )

    assert main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "plan-run",
            goal.id,
            "--cwd",
            str(tmp_path),
            sys.executable,
            "-c",
            "print('cli-ok')",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Plan: {plan.id}" in output
    assert "Capability: process.run" in output
    assert "Status: COMPLETED" in output
    assert "Exit code: 0" in output
    assert "cli-ok" in output
    assert "Verification criada: não" in output

    actions = list_actions_for_plan(database_path, plan.id)
    assert len(actions) == 1
    assert actions[0].status == "COMPLETED"


def test_cli_process_verify_promotes_observed_execution_without_semantic_claim(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Executar script local",
        origin="USER",
        desired_state={"description": "execução observada"},
        success_criteria=({"description": "resultado registrado"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar script de teste.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "A execução produziu saída observável.",
            },
        ),
    )

    assert main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "plan-run",
            goal.id,
            "--cwd",
            str(tmp_path),
            sys.executable,
            "-c",
            "import sys; print('observado'); sys.exit(7)",
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    actions = list_actions_for_plan(database_path, plan.id)
    assert len(actions) == 1
    action = actions[0]

    assert main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "process-verify",
            action.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Action: {action.id}" in output
    assert "Status persistido: VERIFIED" in output
    assert "Exit code observado: 7" in output
    assert "Critério do Plan preservado, sem avaliação semântica" in output
    assert "Verification criada: sim" in output

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT status, evidence_event_ids_json, observed_json
            FROM verification_results
            WHERE subject_type = 'ACTION' AND subject_id = ?
            """,
            (action.id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "VERIFIED"
    observed = json.loads(str(row[2]))
    assert observed["exit_code"] == 7
    assert observed["semantic_effect_assessed"] is False


def test_cli_file_verify_confirms_current_patch_state_without_semantic_claim(
    tmp_path: Path,
    capsys: object,
) -> None:
    workspace = tmp_path / "workspace-file-verify"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data-file-verify")
    goal = Goal.create(
        title="Corrigir script local",
        origin="USER",
        desired_state={"description": "script corrigido"},
        success_criteria=({"description": "arquivo modificado"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Realizar a mudança: corrigir variável",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "Correção localizada da variável",
                "verification": "Arquivo modificado e salvo.",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
        ),
    )

    assert main(
        [
            "--data-dir",
            str(tmp_path / "data-file-verify"),
            "plan-patch",
            goal.id,
            "--workspace",
            str(workspace),
            "--file",
            "script.py",
            "--old",
            "valor = 1",
            "--new",
            "valor = 2",
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    actions = list_actions_for_plan(database_path, plan.id)
    assert len(actions) == 1
    action = actions[0]

    assert main(
        [
            "--data-dir",
            str(tmp_path / "data-file-verify"),
            "file-verify",
            action.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Action: {action.id}" in output
    assert "Status persistido: VERIFIED" in output
    assert "Estado observado: MATCHED" in output
    assert "Critério do Plan preservado, sem avaliação semântica" in output
    assert "Verification criada: sim" in output
    assert target.read_text(encoding="utf-8") == "valor = 2\n"
