import json
import sqlite3
from pathlib import Path

from simon.actions import create_action, transition_action
from simon.cli import main
from simon.events import Event, append_event
from simon.goals import Goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.planning import PlanIntentDraft, PlanIntentStep
from simon.plans import create_plan, get_active_plan, get_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result


def test_negative_verification_can_drive_guarded_plan_revision(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Corrigir estratégia falha",
        origin="USER",
        desired_state={"description": "A falha deixa de ocorrer."},
        success_criteria=({"description": "A falha não é reproduzida."},),
    )
    insert_goal(database_path, goal)
    first_plan = create_plan(
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
        plan_id=first_plan.id,
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
        payload={"action_id": action.id, "summary": "A hipótese foi refutada."},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    failed_assessment = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "A hipótese explica a falha observada."},),
        status="ASSESSED",
        evidence_event_ids=(evidence.id,),
        observed={
            "assessment_type": "cognition.analyze.semantic",
            "verdict": "NOT_SATISFIED",
            "rationale": "A evidência contradiz a hipótese atual.",
        },
        strength=2,
    )

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[PlanIntentDraft]:
            prompt = kwargs.get("prompt")
            assert isinstance(prompt, str)
            assert failed_assessment.id in prompt
            return StructuredModelResult(
                model="fake-model",
                output=PlanIntentDraft(
                    summary="Produzir evidência por uma estratégia alternativa.",
                    steps=[
                        PlanIntentStep(
                            subject="uma estratégia alternativa observável",
                            role="EXECUTE",
                            verification="Existe nova evidência da estratégia alternativa.",
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
    proposal_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Replanejamento motivado por falha" in proposal_output

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT id, payload_json
            FROM events
            WHERE kind = 'cognition.plan_proposal.completed' AND goal_id = ?
            ORDER BY occurred_at DESC, id DESC
            LIMIT 1
            """,
            (goal.id,),
        ).fetchone()
    assert row is not None
    proposal_event_id = str(row[0])
    proposal_payload = json.loads(str(row[1]))
    assert proposal_payload["source_failure_verification_id"] == failed_assessment.id

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "plan-materialize",
            proposal_event_id,
        ]
    ) == 0
    materialization_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Revisão: 2" in materialization_output

    restored_first = get_plan(database_path, first_plan.id)
    second_plan = get_active_plan(database_path, goal.id)
    assert restored_first is not None
    assert restored_first.status == "SUPERSEDED"
    assert second_plan is not None
    assert second_plan.revision == 2
    assert second_plan.id != first_plan.id
