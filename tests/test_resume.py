from pathlib import Path

from simon.actions import create_action, transition_action
from simon.cli import main
from simon.experiences import close_experience, create_experience
from simon.goals import Goal, insert_goal
from simon.memories import create_memory
from simon.plans import create_plan
from simon.resume import reconstruct_resume_state
from simon.storage import initialize_storage
from simon.world import get_world_revision


def _goal(database_path: Path) -> Goal:
    goal = Goal.create(
        title="Retomar correção do script",
        origin="USER",
        desired_state={"status": "fixed"},
        success_criteria=({"kind": "script_fixed"},),
    )
    insert_goal(database_path, goal)
    return goal


def test_resume_reconstructs_persisted_semantic_state_after_startup(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(["--data-dir", str(tmp_path)]) == 0
    database_path = tmp_path / "simon.db"
    initial_revision = get_world_revision(database_path)

    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_1",
                "description": "Perguntar qual erro precisa ser corrigido",
                "capability": "user.ask",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_1",
        kind="user.ask",
        input_data={"prompt": "Qual erro apareceu?"},
    )
    waiting = transition_action(database_path, action.id, "WAITING")

    old_experience = create_experience(database_path, title="Tentativa anterior")
    closed = close_experience(
        database_path,
        old_experience.id,
        outcome="PARTIAL",
        summary="A tentativa ensinou uma validação útil.",
    )
    memory = create_memory(
        database_path,
        kind="SEMANTIC",
        content="Retomar correção do script exige validar a evidência observada.",
        scope="PROJECT",
        source_experience_ids=(closed.id,),
    )

    capsys.readouterr()
    assert main(["--data-dir", str(tmp_path), "resume", goal.id]) == 0
    output = capsys.readouterr().out

    assert get_world_revision(database_path) == initial_revision
    assert f"Goal selecionado: {goal.id} | ACTIVE" in output
    assert f"Plan atual: {plan.id} | revisão 1 | ACTIVE" in output
    assert f"World revision do Plan: {initial_revision}" in output
    assert "World mudou desde o Plan: não" in output
    assert f"{waiting.id}: user.ask | WAITING | step step_1 | sem Verification" in output
    assert "Próximo passo executável: nenhum" in output
    assert f"{memory.id}: SEMANTIC/PROJECT" in output

    state = reconstruct_resume_state(database_path, goal_id=goal.id)
    assert state.selected is not None
    assert state.selected.goal.id == goal.id
    assert state.selected.plan == plan
    assert state.selected.actions[0].action.id == waiting.id
    assert state.selected.memories[0].id == memory.id


def test_resume_reports_multiple_open_goals_without_inventing_focus(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first = _goal(database_path)
    second = Goal.create(
        title="Outro Goal aberto",
        origin="USER",
        desired_state={"status": "done"},
        success_criteria=({"kind": "done"},),
    )
    insert_goal(database_path, second)

    assert main(["--data-dir", str(tmp_path), "resume"]) == 0
    output = capsys.readouterr().out

    assert "Goals abertos: 2" in output
    assert first.id in output
    assert second.id in output
    assert "Goal selecionado: nenhum (informe um goal_id para detalhar)" in output


def test_resume_exposes_interrupted_action_after_restart(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(["--data-dir", str(tmp_path)]) == 0
    database_path = tmp_path / "simon.db"
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_1",
                "description": "Executar processo",
                "capability": "process.run",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_1",
        kind="process.run",
    )
    transition_action(database_path, action.id, "RUNNING")

    capsys.readouterr()
    assert main(["--data-dir", str(tmp_path), "resume", goal.id]) == 0
    output = capsys.readouterr().out

    assert f"{action.id}: process.run | INTERRUPTED" in output
    assert "Próximo passo executável: nenhum" in output
