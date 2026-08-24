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


class ConversationalExecutiveCycleProvider:
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
        del prompt, system, temperature

        from simon.cognition import GoalProposal, UserInputInterpretation
        from simon.planning import PlanIntentDraft, PlanIntentStep

        if response_model is UserInputInterpretation:
            output = UserInputInterpretation(
                intent="REQUEST",
                objective="Corrigir target.txt substituindo BROKEN por FIXED.",
                entity_mentions=[],
                ambiguities=[],
            )
        elif response_model is GoalProposal:
            output = GoalProposal(
                title="Corrigir target.txt",
                desired_state="target.txt contém FIXED no lugar de BROKEN.",
                success_criteria=["target.txt contém FIXED e não contém BROKEN."],
                open_questions=[],
            )
        elif response_model is PlanIntentDraft:
            output = PlanIntentDraft(
                summary="Aplicar uma substituição textual localizada e verificar o resultado.",
                steps=[
                    PlanIntentStep(
                        subject="Substituir BROKEN por FIXED em target.txt",
                        role="CHANGE",
                        verification="target.txt contém FIXED e não contém BROKEN.",
                    )
                ],
                open_questions=[],
            )
        elif response_model is GoalEvidenceAssessment:
            output = GoalEvidenceAssessment(
                criteria=[
                    GoalCriterionAssessment(
                        criterion_index=1,
                        verdict="SATISFIED",
                        rationale="O file.patch verificado deixou target.txt com FIXED sem BROKEN.",
                        supporting_step_ids=["step_01"],
                    )
                ],
                missing_evidence=[],
            )
        else:
            raise AssertionError(f"response_model inesperado: {response_model.__name__}")

        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


def _run_user_turn_in_new_process(
    data_dir: Path,
    *,
    cwd: Path,
    text: str,
    goal_id: str | None = None,
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
    command = [
        sys.executable,
        "-m",
        "simon",
        "--data-dir",
        str(data_dir),
        "user-turn",
    ]
    if goal_id is not None:
        command.extend(("--goal-id", goal_id))
    command.append(text)
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_conversational_executive_cycle_from_request_to_done_survives_restart(
    tmp_path: Path,
    monkeypatch: object,
    capsys: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "simon.cli.OllamaProvider",
        ConversationalExecutiveCycleProvider,
    )

    data_dir = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "target.txt"
    target.write_text("BROKEN\n", encoding="utf-8")
    database_path, _ = initialize_storage(data_dir)

    # 1. A conversa inicia sem Goal e cria somente uma proposta.
    assert main(
        [
            "--data-dir",
            str(data_dir),
            "user-turn",
            "--model",
            "integration-model",
            "Corrija target.txt substituindo BROKEN por FIXED",
        ]
    ) == 0
    proposed_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Intent: PROPOSE" in proposed_output
    assert "Goal persistido: não" in proposed_output

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM goals").fetchone() == (0,)

    # 2. Um segundo turno humano aceita exatamente a proposta pendente.
    assert main(["--data-dir", str(data_dir), "user-turn", "sim"]) == 0
    accepted_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Intent: ACCEPT" in accepted_output
    assert "Goal persistido: sim" in accepted_output
    goal_id = _single_value(database_path, "SELECT id FROM goals")

    # 3. CONTINUE usa o modelo para propor o Plan, materializa a proposta e para no patch.
    assert main(
        [
            "--data-dir",
            str(data_dir),
            "user-turn",
            "--model",
            "integration-model",
            "continue",
        ]
    ) == 0
    planned_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "plan.propose" in planned_output
    assert "plan.materialize" in planned_output
    assert "NEEDS_OPERATION_AUTHORIZATION" in planned_output
    assert "Operação: plan.patch" in planned_output
    plan_id = _single_value(
        database_path,
        "SELECT id FROM plans WHERE goal_id = ?",
        (goal_id,),
    )

    # 4. O próprio turno materializa a alteração, mas ainda não a executa.
    monkeypatch.chdir(workspace)  # type: ignore[attr-defined]
    assert main(
        [
            "--data-dir",
            str(data_dir),
            "user-turn",
            "No arquivo target.txt, substitua `BROKEN` por `FIXED` neste projeto",
        ]
    ) == 0
    materialized_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Intent: MATERIALIZE" in materialized_output
    assert "operation.proposal" in materialized_output
    assert "READY_FOR_AUTHORIZATION" in materialized_output
    assert target.read_text(encoding="utf-8") == "BROKEN\n"

    # 5. Outro processo consome somente essa autorização, verifica e conclui o Plan.
    authorized = _run_user_turn_in_new_process(
        data_dir,
        cwd=workspace,
        text="pode aplicar",
    )
    assert authorized.returncode == 2, authorized.stderr
    assert "Intent: AUTHORIZE" in authorized.stdout
    assert "file.verify -> verification" in authorized.stdout
    assert "plan.complete -> plan" in authorized.stdout
    assert "Operação: goal.assess" in authorized.stdout
    assert "Parada: informe --model" in authorized.stdout
    assert target.read_text(encoding="utf-8") == "FIXED\n"

    # 6. A conversa retoma o Goal, faz o assessment e para na confirmação humana.
    assert main(
        [
            "--data-dir",
            str(data_dir),
            "user-turn",
            "--model",
            "integration-model",
            "continue",
        ]
    ) == 0
    assessed_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "goal.assess -> verification" in assessed_output
    assert "NEEDS_USER_CONFIRMATION" in assessed_output
    assert "Operação: goal.complete" in assessed_output

    # 7. A confirmação final conclui o Goal sem executar trabalho externo adicional.
    assert main(["--data-dir", str(data_dir), "user-turn", "sim"]) == 0
    completed_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Intent: CONFIRM" in completed_output
    assert "Efeito do gate: goal.completed" in completed_output
    assert "Executive continue: DONE" in completed_output

    # 8. Mais um processo reconstrói o Goal concluído exclusivamente do SQLite.
    final_restart = _run_user_turn_in_new_process(
        data_dir,
        cwd=workspace,
        text="continue",
        goal_id=goal_id,
    )
    assert final_restart.returncode == 0, final_restart.stderr
    assert "Executive continue: DONE" in final_restart.stdout
    assert "Razão: goal_completed" in final_restart.stdout

    with sqlite3.connect(database_path) as connection:
        goal_status = connection.execute(
            "SELECT status FROM goals WHERE id = ?",
            (goal_id,),
        ).fetchone()
        plan_status = connection.execute(
            "SELECT status FROM plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
        startup_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'system.started'",
        ).fetchone()
        accepted_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'goal.proposal.accepted'",
        ).fetchone()
        authorization_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'file.patch.authorized'",
        ).fetchone()

    assert goal_status == ("COMPLETED",)
    assert plan_status == ("COMPLETED",)
    assert startup_count is not None and startup_count[0] >= 3
    assert accepted_count == (1,)
    assert authorization_count == (1,)
