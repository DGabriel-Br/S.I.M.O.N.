import json
import sqlite3
from pathlib import Path

from simon.actions import create_action, get_action, transition_action
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
    assert json.loads(str(claim[1])) == 9
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
    from simon.planning import PlanProposal, PlanStepProposal

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

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[PlanProposal]:
            assert kwargs["response_model"] is PlanProposal
            return StructuredModelResult(
                model="fake-model",
                output=PlanProposal(
                    summary="Coletar evidência antes da correção.",
                    steps=[
                        PlanStepProposal(
                            id="step_1",
                            description="Identificar o script e a falha observada.",
                            kind="EPISTEMIC",
                            capability="obter contexto do usuário",
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
    assert "step_1 [EPISTEMIC]" in output
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
                capability="obter contexto do usuário",
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
