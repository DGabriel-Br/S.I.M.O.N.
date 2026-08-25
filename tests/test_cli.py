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
    assert json.loads(str(claim[1])) == 11
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


def test_cli_file_retry_reauthorizes_failed_patch_with_new_request(
    tmp_path: Path,
    capsys: object,
) -> None:
    workspace = tmp_path / "workspace-file-retry"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 3\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data-file-retry")
    goal = Goal.create(
        title="Corrigir patch após falha",
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
            str(tmp_path / "data-file-retry"),
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
    ) == 1
    capsys.readouterr()  # type: ignore[attr-defined]

    first = list_actions_for_plan(database_path, plan.id)[0]
    assert first.status == "FAILED"

    assert main(
        [
            "--data-dir",
            str(tmp_path / "data-file-retry"),
            "file-retry",
            first.id,
            "--workspace",
            str(workspace),
            "--file",
            "script.py",
            "--old",
            "valor = 3",
            "--new",
            "valor = 2",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Action anterior: {first.id}" in output
    assert "Capability resolvida: file.patch" in output
    assert "Status: COMPLETED" in output
    assert "Autorização de retry:" in output
    assert "Verification criada: não" in output
    assert target.read_text(encoding="utf-8") == "valor = 2\n"

    actions = list_actions_for_plan(database_path, plan.id)
    assert [action.status for action in actions] == ["FAILED", "COMPLETED"]
    assert actions[-1].input_data["retry_of_action_id"] == first.id


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


def test_goal_complete_cli_confirms_satisfied_assessment_and_closes_goal(
    tmp_path: Path,
    capsys: object,
) -> None:
    from simon.events import Event, append_event
    from simon.plan_completion import complete_verified_plan
    from simon.verification import create_verification_result

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Concluir correção",
        origin="USER",
        desired_state={"description": "O script executa corretamente."},
        success_criteria=({"description": "A execução final está correta."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar verificação final.",
                "verification": "Execução observada.",
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
        kind="test.goal.complete.cli.evidence",
        source="test",
        payload={"ok": True},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "execução observada"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"ok": True},
        strength=3,
    )
    completion = complete_verified_plan(database_path, goal_id=goal.id)
    assessment = create_verification_result(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
        criteria=goal.success_criteria,
        status="ASSESSED",
        evidence_event_ids=(completion.completion_event_id, evidence.id),
        observed={
            "assessment_type": "goal.semantic",
            "verdict": "SATISFIED",
            "criterion_assessments": [
                {
                    "criterion_index": 1,
                    "verdict": "SATISFIED",
                    "rationale": "A evidência final satisfaz o critério.",
                    "supporting_step_ids": ["step_01"],
                }
            ],
            "missing_evidence": [],
            "plan_id": plan.id,
            "plan_revision": plan.revision,
            "plan_completion_event_id": completion.completion_event_id,
            "model": "fake-model",
        },
        strength=2,
    )

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "goal-complete",
            assessment.id,
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Goal: {goal.id} (Concluir correção)" in output
    assert f"Assessment confirmado: {assessment.id}" in output
    assert "Status epistemológico: VERIFIED" in output
    assert "Status do Goal: COMPLETED" in output
    assert "Goal concluído: sim" in output

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT status FROM goals WHERE id = ?",
            (goal.id,),
        ).fetchone()
    assert row == ("COMPLETED",)


def test_experience_remember_cli_promotes_closed_experience_to_memory(
    tmp_path: Path,
    capsys: object,
) -> None:
    from simon.experiences import close_experience
    from simon.memories import get_memory

    database_path, _ = initialize_storage(tmp_path)
    experience = create_experience(database_path, title="Aprender com execução")
    closed = close_experience(
        database_path,
        experience.id,
        outcome="SUCCESS",
        summary="Execução concluída com evidência suficiente.",
    )

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "experience-remember",
            closed.id,
            "--kind",
            "SEMANTIC",
            "--scope",
            "PROJECT",
            "Verificar",
            "evidência",
            "antes",
            "de",
            "concluir.",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Experience: {closed.id} (Aprender com execução)" in output
    assert "Outcome: SUCCESS" in output
    assert "Kind: SEMANTIC" in output
    assert "Scope: PROJECT" in output
    assert "Conteúdo: Verificar evidência antes de concluir." in output
    assert "Memory criada por decisão explícita: sim" in output

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT id FROM memories ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        event = connection.execute(
            """
            SELECT source, experience_id
            FROM events
            WHERE kind = 'memory.promoted_from_experience'
            ORDER BY occurred_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    memory = get_memory(database_path, str(row[0]))
    assert memory is not None
    assert memory.source_experience_ids == (closed.id,)
    assert event == ("user", closed.id)


def test_process_retry_cli_recovers_failed_process_attempt(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Recuperar execução",
        origin="USER",
        desired_state={"description": "A execução foi recuperada."},
        success_criteria=({"description": "Existe execução observável."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar processo.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "A execução produziu resultado técnico observável.",
            },
        ),
    )

    missing = str(tmp_path / "missing-process")
    assert main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "plan-run",
            goal.id,
            "--cwd",
            str(tmp_path),
            missing,
        ]
    ) == 1
    failed = list_actions_for_plan(database_path, plan.id)[0]
    assert failed.status == "FAILED"
    capsys.readouterr()  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "process-retry",
            failed.id,
            "--cwd",
            str(tmp_path),
            sys.executable,
            "-c",
            "print('recovered-cli')",
        ]
    ) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Action anterior: {failed.id}" in output
    assert "Status: COMPLETED" in output
    assert "recovered-cli" in output


def test_plan_propose_does_not_replace_healthy_active_plan(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Executar script",
        origin="USER",
        desired_state={"description": "O script foi executado."},
        success_criteria=({"description": "Existe execução observável."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar o script.",
                "kind": "WORLD",
                "capability": "process.run",
                "verification": "Existe execução observável.",
            },
        ),
    )

    class UnexpectedProvider:
        def __init__(self, **kwargs: object) -> None:
            raise AssertionError("Planner não deveria ser chamado com Plan ACTIVE saudável")

    monkeypatch.setattr("simon.cli.OllamaProvider", UnexpectedProvider)  # type: ignore[attr-defined]

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
    assert "Proposta de Plan: não gerada" in output
    assert f"Plan ACTIVE {plan.id} ainda possui step executável: step_01" in output


def test_plan_propose_uses_failed_active_plan_as_explicit_replanning_context(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.actions import create_action, transition_action
    from simon.events import Event, append_event
    from simon.model_provider import StructuredModelResult
    from simon.planning import PlanIntentDraft, PlanIntentStep
    from simon.verification import create_verification_result

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Corrigir estratégia",
        origin="USER",
        desired_state={"description": "A falha deixa de ocorrer."},
        success_criteria=({"description": "A falha não é reproduzida."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar a hipótese atual.",
                "kind": "EPISTEMIC",
                "capability": "cognition.analyze",
                "verification": "A hipótese explica a falha observada.",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="cognition.analyze",
    )
    transition_action(database_path, action.id, "RUNNING")
    action = transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={"analysis_event_id": "evt_analysis"},
    )
    evidence = Event.create(
        kind="cognition.analysis.completed",
        source="cognition",
        payload={"action_id": action.id, "summary": "A hipótese não explica o erro."},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    verification = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "A hipótese explica a falha observada."},),
        status="ASSESSED",
        evidence_event_ids=(evidence.id,),
        observed={
            "assessment_type": "cognition.analyze.semantic",
            "verdict": "NOT_SATISFIED",
            "rationale": "A hipótese foi contrariada pela evidência.",
        },
        strength=2,
    )

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[PlanIntentDraft]:
            prompt = kwargs.get("prompt")
            assert isinstance(prompt, str)
            assert verification.id in prompt
            assert "CRITERION_NOT_SATISFIED" in prompt
            return StructuredModelResult(
                model="fake-model",
                output=PlanIntentDraft(
                    summary="Testar uma estratégia alternativa.",
                    steps=[
                        PlanIntentStep(
                            subject="uma estratégia alternativa que discrimine a causa",
                            role="EXECUTE",
                            verification="Existe nova evidência observável da estratégia alternativa.",
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
    assert f"Replanejamento motivado por falha: {verification.id}" in output
    assert f"Plan ACTIVE substituível: {plan.id} (revisão 1)" in output

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
    assert payload["source_active_plan_id"] == plan.id
    assert payload["source_active_plan_revision"] == 1
    assert payload["source_failure_step_id"] == "step_01"
    assert payload["source_failure_action_id"] == action.id
    assert payload["source_failure_verification_id"] == verification.id
    assert payload["source_failure_blocker_kind"] == "CRITERION_NOT_SATISFIED"


def test_analysis_retry_cli_executes_explicit_new_attempt(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    from simon.cognition_analysis import CognitionAnalysis
    from simon.model_provider import StructuredModelResult

    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Retentar análise",
        origin="USER",
        desired_state={"description": "A análise foi concluída."},
        success_criteria=({"description": "Existe análise persistida."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar: dado disponível.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "A análise foi produzida.",
            },
        ),
    )
    failed = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="cognition.analyze",
        input_data={"model": "fake-model"},
    )
    transition_action(database_path, failed.id, "RUNNING")
    failed = transition_action(
        database_path,
        failed.id,
        "FAILED",
        failure={"kind": "model_provider", "message": "runtime indisponível"},
    )

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[CognitionAnalysis]:
            return StructuredModelResult(
                model="fake-model",
                output=CognitionAnalysis(
                    summary="A análise foi concluída após nova tentativa.",
                    findings=[],
                    uncertainties=["Não havia evidência anterior para um finding factual."],
                ),
            )

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "analysis-retry",
            "--model",
            "fake-model",
            failed.id,
        ]
    ) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert f"Action anterior: {failed.id}" in output
    assert "Status: COMPLETED" in output
    assert "A análise foi concluída após nova tentativa." in output


def test_observe_cli_records_signal_and_attention_assessment(
    tmp_path: Path,
    capsys: object,
) -> None:
    result = main(
        [
            "--data-dir",
            str(tmp_path),
            "observe",
            "--source",
            "filesystem",
            "--kind",
            "file.changed",
            "--world-change",
            "target.txt",
            "foi",
            "alterado",
        ]
    )

    assert result == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Observer: filesystem" in output
    assert "Sinal: file.changed" in output
    assert "Resumo: target.txt foi alterado" in output
    assert "Attention: UPDATE_WORLD" in output
    assert "Efeito aplicado ao World/Executive: não" in output

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        rows = connection.execute(
            """
            SELECT kind, source, payload_json, trace_id
            FROM events
            WHERE kind IN ('perception.observation.recorded', 'attention.assessed')
            ORDER BY occurred_at, rowid
            """
        ).fetchall()

    assert len(rows) == 2
    assert rows[0][0:2] == ("perception.observation.recorded", "perception")
    assert rows[1][0:2] == ("attention.assessed", "attention")
    assert rows[0][3] == rows[1][3]
    assessment_payload = json.loads(str(rows[1][2]))
    assert assessment_payload["destination"] == "UPDATE_WORLD"
    assert assessment_payload["effect_applied"] is False


def test_observe_cli_defaults_to_record_without_escalation_signal(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "observe",
            "--source",
            "process-monitor",
            "--kind",
            "heartbeat",
            "serviço",
            "continua",
            "ativo",
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Attention: RECORD" in output
    assert "Razões: no_escalation_signal" in output


def test_claim_propose_cli_consumes_update_world_without_persisting_belief(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "observe",
            "--source",
            "filesystem",
            "--kind",
            "system.changed",
            "--entity-id",
            SIMON_ENTITY_ID,
            "--world-change",
            "estado",
            "do",
            "SIMON",
            "mudou",
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        row = connection.execute(
            """
            SELECT id
            FROM events
            WHERE kind = 'attention.assessed'
            ORDER BY occurred_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
        before_revision = connection.execute(
            "SELECT revision FROM world_state WHERE singleton = 1"
        ).fetchone()

    assert row is not None
    attention_event_id = str(row[0])
    assert before_revision is not None

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "claim-propose",
            "--attention-event-id",
            attention_event_id,
            "--subject-id",
            SIMON_ENTITY_ID,
            "--predicate",
            "runtime.state",
            "--value-json",
            '{"state":"changed"}',
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Proposed Claim: evt_" in output
    assert f"Attention: {attention_event_id}" in output
    assert f"Subject: {SIMON_ENTITY_ID}" in output
    assert "Predicate: runtime.state" in output
    assert 'Value: {"state": "changed"}' in output
    assert "Claim persistida no Belief Store: não" in output
    assert "World revision alterada: não" in output

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        proposal = connection.execute(
            """
            SELECT kind, source, payload_json
            FROM events
            WHERE kind = 'world.claim.proposed'
            ORDER BY occurred_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
        belief = connection.execute(
            """
            SELECT id
            FROM claims
            WHERE subject_id = ? AND predicate = 'runtime.state'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()
        after_revision = connection.execute(
            "SELECT revision FROM world_state WHERE singleton = 1"
        ).fetchone()

    assert proposal is not None
    assert proposal[0:2] == ("world.claim.proposed", "perception")
    payload = json.loads(str(proposal[2]))
    assert payload["attention_event_id"] == attention_event_id
    assert payload["effect_applied"] is False
    assert belief is None
    assert after_revision == before_revision


def test_claim_validate_cli_classifies_ready_without_mutating_world(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "observe",
            "--source",
            "filesystem",
            "--kind",
            "system.changed",
            "--entity-id",
            SIMON_ENTITY_ID,
            "--world-change",
            "estado",
            "do",
            "SIMON",
            "mudou",
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        attention = connection.execute(
            """
            SELECT id
            FROM events
            WHERE kind = 'attention.assessed'
            ORDER BY occurred_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
    assert attention is not None

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "claim-propose",
            "--attention-event-id",
            str(attention[0]),
            "--subject-id",
            SIMON_ENTITY_ID,
            "--predicate",
            "runtime.state",
            "--value-json",
            '{"state":"changed"}',
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        proposal = connection.execute(
            """
            SELECT id
            FROM events
            WHERE kind = 'world.claim.proposed'
            ORDER BY occurred_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
        before_revision = connection.execute(
            "SELECT revision FROM world_state WHERE singleton = 1"
        ).fetchone()
    assert proposal is not None
    assert before_revision is not None

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "claim-validate",
            "--proposal-event-id",
            str(proposal[0]),
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Claim validation: evt_" in output
    assert f"Proposed Claim: {proposal[0]}" in output
    assert "Outcome: READY" in output
    assert "Razões: no_active_claim" in output
    assert "Efeito aplicado ao Belief Store: não" in output
    assert "World revision alterada: não" in output

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        validation = connection.execute(
            """
            SELECT kind, source, payload_json
            FROM events
            WHERE kind = 'world.claim.validation.completed'
            ORDER BY occurred_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
        belief = connection.execute(
            """
            SELECT id
            FROM claims
            WHERE subject_id = ? AND predicate = 'runtime.state'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()
        after_revision = connection.execute(
            "SELECT revision FROM world_state WHERE singleton = 1"
        ).fetchone()

    assert validation is not None
    assert validation[0:2] == ("world.claim.validation.completed", "world")
    payload = json.loads(str(validation[2]))
    assert payload["outcome"] == "READY"
    assert payload["effect_applied"] is False
    assert belief is None
    assert after_revision == before_revision


def test_claim_accept_ready_cli_requires_human_confirmation_before_world_change(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "observe",
            "--source",
            "filesystem",
            "--kind",
            "system.changed",
            "--entity-id",
            SIMON_ENTITY_ID,
            "--world-change",
            "estado",
            "do",
            "SIMON",
            "mudou",
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        attention = connection.execute(
            """
            SELECT id FROM events
            WHERE kind = 'attention.assessed'
            ORDER BY occurred_at DESC, rowid DESC LIMIT 1
            """
        ).fetchone()
    assert attention is not None

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "claim-propose",
            "--attention-event-id",
            str(attention[0]),
            "--subject-id",
            SIMON_ENTITY_ID,
            "--predicate",
            "runtime.state",
            "--value-json",
            '{"state":"changed"}',
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        proposal = connection.execute(
            """
            SELECT id FROM events
            WHERE kind = 'world.claim.proposed'
            ORDER BY occurred_at DESC, rowid DESC LIMIT 1
            """
        ).fetchone()
    assert proposal is not None

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "claim-validate",
            "--proposal-event-id",
            str(proposal[0]),
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        validation = connection.execute(
            """
            SELECT id FROM events
            WHERE kind = 'world.claim.validation.completed'
            ORDER BY occurred_at DESC, rowid DESC LIMIT 1
            """
        ).fetchone()
        before_revision = connection.execute(
            "SELECT revision FROM world_state WHERE singleton = 1"
        ).fetchone()
    assert validation is not None
    assert before_revision is not None

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "claim-accept-ready",
            "--validation-event-id",
            str(validation[0]),
        ]
    ) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Claim acceptance: evt_" in output
    assert f"Validation: {validation[0]}" in output
    assert "Claim: clm_" in output
    assert "Autoridade: USER_CONFIRMATION" in output
    assert "Claim persistida no Belief Store: sim" in output
    assert "World revision alterada: sim" in output

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        claim = connection.execute(
            """
            SELECT status, epistemic_status, value_json
            FROM claims
            WHERE subject_id = ? AND predicate = 'runtime.state'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()
        acceptance = connection.execute(
            """
            SELECT source, payload_json
            FROM events
            WHERE kind = 'world.claim.accepted'
            ORDER BY occurred_at DESC, rowid DESC LIMIT 1
            """
        ).fetchone()
        after_revision = connection.execute(
            "SELECT revision FROM world_state WHERE singleton = 1"
        ).fetchone()

    assert claim == ("ACTIVE", "DIRECT_OBSERVATION", '{"state":"changed"}')
    assert acceptance is not None
    assert acceptance[0] == "user"
    acceptance_payload = json.loads(str(acceptance[1]))
    assert acceptance_payload["validation_event_id"] == str(validation[0])
    assert acceptance_payload["authority"] == "USER_CONFIRMATION"
    assert after_revision == (int(before_revision[0]) + 1,)
