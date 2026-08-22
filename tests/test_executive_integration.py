from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

from simon.cli import main
from simon.cognition_analysis import AnalysisFinding, CognitionAnalysis
from simon.cognition_analysis_verification import CognitionAnalysisCriterionAssessment
from simon.goal_verification import GoalCriterionAssessment, GoalEvidenceAssessment
from simon.goals import Goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.plans import create_plan
from simon.storage import initialize_storage


class ExecutiveCycleProvider:
    def __init__(self, **kwargs: object) -> None:
        pass

    def list_models(self) -> tuple[str, ...]:
        return ("integration-model",)

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]:
        del system, temperature

        if response_model is CognitionAnalysis:
            payload = _prompt_payload(prompt)
            evidence = payload["evidence"]
            assert isinstance(evidence, list)
            target = _execution_evidence(evidence, expected="FIXED")
            if target is None:
                target = _execution_evidence(evidence, expected="BROKEN")
            assert target is not None
            event_id = target["event_id"]
            assert isinstance(event_id, str)
            event_payload = target["payload"]
            assert isinstance(event_payload, dict)
            stdout = event_payload.get("stdout")
            assert isinstance(stdout, str)
            if "FIXED" in stdout:
                statement = "A execução corrigida produziu FIXED sem reproduzir BROKEN."
            else:
                statement = "A execução inicial produziu BROKEN e tornou a falha observável."
            output = CognitionAnalysis(
                summary=statement,
                findings=[
                    AnalysisFinding(
                        statement=statement,
                        evidence_event_ids=[event_id],
                    )
                ],
                uncertainties=[],
            )
        elif response_model is CognitionAnalysisCriterionAssessment:
            output = CognitionAnalysisCriterionAssessment(
                verdict="SATISFIED",
                rationale="A análise satisfaz o critério e referencia evidência persistida.",
                missing_information=[],
            )
        elif response_model is GoalEvidenceAssessment:
            output = GoalEvidenceAssessment(
                criteria=[
                    GoalCriterionAssessment(
                        criterion_index=1,
                        verdict="SATISFIED",
                        rationale="A execução final verificada produziu FIXED sem BROKEN.",
                        supporting_step_ids=["step_05"],
                    )
                ],
                missing_evidence=[],
            )
        else:
            raise AssertionError(f"response_model inesperado: {response_model.__name__}")

        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


def _prompt_payload(prompt: str) -> dict[str, object]:
    _, raw_json = prompt.split("\n", 1)
    payload = json.loads(raw_json)
    assert isinstance(payload, dict)
    return payload


def _execution_evidence(
    evidence: list[object],
    *,
    expected: str,
) -> dict[str, object] | None:
    for item in reversed(evidence):
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        stdout = payload.get("stdout")
        if isinstance(stdout, str) and expected in stdout:
            return item
    return None


def _single_value(database_path: Path, query: str, parameters: tuple[object, ...] = ()) -> str:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(query, parameters).fetchone()
    assert row is not None
    return str(row[0])


def _latest_action_id(database_path: Path, *, plan_id: str, step_id: str) -> str:
    return _single_value(
        database_path,
        """
        SELECT id
        FROM actions
        WHERE plan_id = ? AND step_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (plan_id, step_id),
    )


def _latest_assessment_id(database_path: Path, *, subject_type: str, subject_id: str) -> str:
    return _single_value(
        database_path,
        """
        SELECT id
        FROM verification_results
        WHERE subject_type = ? AND subject_id = ? AND status = 'ASSESSED'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (subject_type, subject_id),
    )


def _run_executive_step_in_new_process(
    data_dir: Path,
    *,
    goal_id: str,
) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    source_path = str(project_root / "src")
    existing_pythonpath = env.get("PYTHONPATH")
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
            "executive-step",
            goal_id,
        ],
        cwd=project_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_executive_foreground_cycle_survives_restarts_and_respects_gates(
    tmp_path: Path,
    monkeypatch: object,
    capsys: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "simon.cli.OllamaProvider",
        ExecutiveCycleProvider,
    )

    data_dir = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script_path = workspace / "target.py"
    script_path.write_text('print("BROKEN")\n', encoding="utf-8")

    database_path, _ = initialize_storage(data_dir)
    goal = Goal.create(
        title="Corrigir script pelo Executive",
        origin="USER",
        desired_state={"description": "O script produz FIXED sem reproduzir BROKEN."},
        success_criteria=(
            {"description": "A execução final produz FIXED e não reproduz BROKEN."},
        ),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar o script para observar a falha.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "Existe uma execução inicial observável.",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
            {
                "id": "step_02",
                "description": "Analisar a saída inicial.",
                "kind": "EPISTEMIC",
                "depends_on": ["step_01"],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "A análise identifica a falha BROKEN.",
                "intent_role": "ANALYZE",
                "intent_actor": "SIMON",
            },
            {
                "id": "step_03",
                "description": "Substituir BROKEN por FIXED no script.",
                "kind": "WORLD",
                "depends_on": ["step_02"],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "Substituição localizada de BROKEN por FIXED",
                "verification": "O arquivo foi modificado e salvo.",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
            {
                "id": "step_04",
                "description": "Executar novamente o script corrigido.",
                "kind": "WORLD",
                "depends_on": ["step_03"],
                "preconditions": [],
                "capability": "process.run",
                "verification": "Existe uma execução final observável.",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
            {
                "id": "step_05",
                "description": "Analisar a saída final.",
                "kind": "EPISTEMIC",
                "depends_on": ["step_04"],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "A saída final mostra FIXED sem BROKEN.",
                "intent_role": "ANALYZE",
                "intent_actor": "SIMON",
            },
        ),
    )

    # O Executive reconhece o efeito externo, mas não atravessa a autorização.
    assert main(["--data-dir", str(data_dir), "executive-step", goal.id]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Executive runner: STOPPED" in output
    assert "NEEDS_OPERATION_AUTHORIZATION" in output
    assert "Operação: plan.run" in output

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-run",
            goal.id,
            "--cwd",
            str(workspace),
            sys.executable,
            str(script_path),
        ]
    ) == 0
    first_run = _latest_action_id(database_path, plan_id=plan.id, step_id="step_01")

    # Um processo novo reconstrói somente do SQLite e executa a Verification segura.
    restarted_after_run = _run_executive_step_in_new_process(data_dir, goal_id=goal.id)
    assert restarted_after_run.returncode == 0, restarted_after_run.stderr
    assert "Executive runner: EXECUTED" in restarted_after_run.stdout
    assert "Operação executada: process.verify" in restarted_after_run.stdout
    assert "Operação: plan.analyze" in restarted_after_run.stdout

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "executive-step",
            "--model",
            "integration-model",
            goal.id,
        ]
    ) == 0
    first_analysis = _latest_action_id(database_path, plan_id=plan.id, step_id="step_02")
    assert first_analysis != first_run

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "executive-step",
            "--model",
            "integration-model",
            goal.id,
        ]
    ) == 0
    first_assessment = _latest_assessment_id(
        database_path,
        subject_type="ACTION",
        subject_id=first_analysis,
    )

    assert main(["--data-dir", str(data_dir), "executive-step", goal.id]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Executive runner: STOPPED" in output
    assert "NEEDS_USER_CONFIRMATION" in output
    assert "Operação: verification.confirm" in output

    assert main(
        ["--data-dir", str(data_dir), "verification-confirm", first_assessment]
    ) == 0

    assert main(["--data-dir", str(data_dir), "executive-step", goal.id]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "NEEDS_OPERATION_AUTHORIZATION" in output
    assert "Operação: plan.patch" in output

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-patch",
            goal.id,
            "--workspace",
            str(workspace),
            "--file",
            script_path.name,
            "--old",
            "BROKEN",
            "--new",
            "FIXED",
        ]
    ) == 0
    patch_action = _latest_action_id(database_path, plan_id=plan.id, step_id="step_03")
    assert script_path.read_text(encoding="utf-8") == 'print("FIXED")\n'

    restarted_after_patch = _run_executive_step_in_new_process(data_dir, goal_id=goal.id)
    assert restarted_after_patch.returncode == 0, restarted_after_patch.stderr
    assert "Operação executada: file.verify" in restarted_after_patch.stdout
    assert patch_action in restarted_after_patch.stdout
    assert "Operação: plan.run" in restarted_after_patch.stdout

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-run",
            goal.id,
            "--cwd",
            str(workspace),
            sys.executable,
            str(script_path),
        ]
    ) == 0
    final_run = _latest_action_id(database_path, plan_id=plan.id, step_id="step_04")

    restarted_after_final_run = _run_executive_step_in_new_process(
        data_dir,
        goal_id=goal.id,
    )
    assert restarted_after_final_run.returncode == 0, restarted_after_final_run.stderr
    assert "Operação executada: process.verify" in restarted_after_final_run.stdout
    assert final_run in restarted_after_final_run.stdout
    assert "Operação: plan.analyze" in restarted_after_final_run.stdout

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "executive-step",
            "--model",
            "integration-model",
            goal.id,
        ]
    ) == 0
    final_analysis = _latest_action_id(database_path, plan_id=plan.id, step_id="step_05")

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "executive-step",
            "--model",
            "integration-model",
            goal.id,
        ]
    ) == 0
    final_assessment = _latest_assessment_id(
        database_path,
        subject_type="ACTION",
        subject_id=final_analysis,
    )
    assert main(
        ["--data-dir", str(data_dir), "verification-confirm", final_assessment]
    ) == 0

    assert main(["--data-dir", str(data_dir), "executive-step", goal.id]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Operação executada: plan.complete" in output
    assert "Operação: goal.assess" in output

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "executive-step",
            "--model",
            "integration-model",
            goal.id,
        ]
    ) == 0
    goal_assessment = _latest_assessment_id(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
    )

    assert main(["--data-dir", str(data_dir), "executive-step", goal.id]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "NEEDS_USER_CONFIRMATION" in output
    assert "Operação: goal.complete" in output

    assert main(["--data-dir", str(data_dir), "goal-complete", goal_assessment]) == 0

    final_restart = _run_executive_step_in_new_process(data_dir, goal_id=goal.id)
    assert final_restart.returncode == 0, final_restart.stderr
    assert "Executive runner: STOPPED" in final_restart.stdout
    assert "Executive: DONE" in final_restart.stdout
    assert "Razão: goal_completed" in final_restart.stdout

    with sqlite3.connect(database_path) as connection:
        goal_status = connection.execute(
            "SELECT status FROM goals WHERE id = ?",
            (goal.id,),
        ).fetchone()
        plan_status = connection.execute(
            "SELECT status FROM plans WHERE id = ?",
            (plan.id,),
        ).fetchone()
        startup_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'system.started'",
        ).fetchone()

    assert goal_status == ("COMPLETED",)
    assert plan_status == ("COMPLETED",)
    assert startup_count is not None and startup_count[0] >= 4
