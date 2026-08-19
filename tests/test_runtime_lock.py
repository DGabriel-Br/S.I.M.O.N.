from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from simon.actions import create_action, get_action, transition_action
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.runtime_lock import RuntimeLock
from simon.storage import initialize_storage


def _run_resume(data_dir: Path, goal_id: str) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    source_path = str(project_root / "src")
    env["PYTHONPATH"] = (
        source_path
        if not existing_pythonpath
        else os.pathsep.join((source_path, existing_pythonpath))
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "simon",
            "--data-dir",
            str(data_dir),
            "resume",
            goal_id,
        ],
        cwd=project_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_second_runtime_cannot_interrupt_live_running_action(tmp_path: Path) -> None:
    data_dir = tmp_path / "state"
    database_path, _ = initialize_storage(data_dir)
    goal = Goal.create(
        title="Executar processo longo",
        origin="USER",
        desired_state={"description": "A execução termina de forma rastreável."},
        success_criteria=({"description": "Existe resultado verificável."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar processo.",
                "capability": "process.run",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )
    transition_action(database_path, action.id, "RUNNING")

    with RuntimeLock(data_dir):
        competing = _run_resume(data_dir, goal.id)
        still_running = get_action(database_path, action.id)

    assert competing.returncode == 2
    assert "Runtime: ocupado" in competing.stdout
    assert still_running is not None
    assert still_running.status == "RUNNING"

    recovered = _run_resume(data_dir, goal.id)
    interrupted = get_action(database_path, action.id)

    assert recovered.returncode == 0
    assert interrupted is not None
    assert interrupted.status == "INTERRUPTED"
    assert interrupted.failure is not None
    assert interrupted.failure["kind"] == "runtime_restart"
