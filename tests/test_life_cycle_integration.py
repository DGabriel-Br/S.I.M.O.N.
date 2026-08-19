from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

from simon.cli import main
from simon.cognition import GoalProposal, UserInputInterpretation
from simon.cognition_analysis import AnalysisFinding, CognitionAnalysis
from simon.cognition_analysis_verification import CognitionAnalysisCriterionAssessment
from simon.goal_verification import GoalCriterionAssessment, GoalEvidenceAssessment
from simon.model_provider import StructuredModelResult
from simon.planning import PlanIntentDraft, PlanIntentStep


class LifeCycleProvider:
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

        if response_model is UserInputInterpretation:
            output: BaseModel = UserInputInterpretation(
                intent="REQUEST",
                objective="corrigir o script para produzir a saída FIXED",
                entity_mentions=[],
                ambiguities=[],
            )
        elif response_model is GoalProposal:
            output = GoalProposal(
                title="Corrigir script de integração",
                desired_state="O script executa e produz a saída FIXED sem reproduzir BROKEN.",
                success_criteria=[
                    "A execução final produz FIXED e não reproduz BROKEN."
                ],
                open_questions=[],
            )
        elif response_model is PlanIntentDraft:
            output = PlanIntentDraft(
                summary="Observar a falha, analisar, corrigir, reexecutar e validar.",
                steps=[
                    PlanIntentStep(
                        subject="o script atual para observar sua saída antes da correção",
                        role="EXECUTE",
                        verification="Existe uma saída observável da execução inicial.",
                    ),
                    PlanIntentStep(
                        subject="a saída inicial para identificar a falha observada",
                        role="ANALYZE",
                        verification=(
                            "A saída inicial foi analisada e a falha BROKEN foi identificada."
                        ),
                    ),
                    PlanIntentStep(
                        subject="o conteúdo do script para substituir BROKEN por FIXED",
                        role="CHANGE",
                        verification="O arquivo do script foi modificado e salvo.",
                    ),
                    PlanIntentStep(
                        subject="o script corrigido para produzir uma nova saída observável",
                        role="EXECUTE",
                        verification=(
                            "Existe uma saída observável da execução após a correção."
                        ),
                    ),
                    PlanIntentStep(
                        subject="a nova saída para verificar o resultado final da correção",
                        role="ANALYZE",
                        verification="A nova saída mostra FIXED e não reproduz BROKEN.",
                    ),
                ],
                open_questions=[],
            )
        elif response_model is CognitionAnalysis:
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
                statement = "A execução corrigida produziu FIXED e não reproduziu BROKEN."
            else:
                statement = "A execução inicial produziu BROKEN, identificando a falha observada."
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
                rationale="A análise contém a conclusão exigida e cita evidência persistida.",
                missing_information=[],
            )
        elif response_model is GoalEvidenceAssessment:
            output = GoalEvidenceAssessment(
                criteria=[
                    GoalCriterionAssessment(
                        criterion_index=1,
                        verdict="SATISFIED",
                        rationale=(
                            "A execução final verificada foi analisada como FIXED sem BROKEN."
                        ),
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


def _latest_assessment_id(database_path: Path, *, action_id: str) -> str:
    return _single_value(
        database_path,
        """
        SELECT id
        FROM verification_results
        WHERE subject_type = 'ACTION' AND subject_id = ? AND status = 'ASSESSED'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (action_id,),
    )


def _run_resume_in_new_process(
    data_dir: Path,
    *,
    goal_id: str | None = None,
) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    source_path = str(project_root / "src")
    env["PYTHONPATH"] = (
        source_path
        if not existing_pythonpath
        else os.pathsep.join((source_path, existing_pythonpath))
    )
    command = [sys.executable, "-m", "simon", "--data-dir", str(data_dir), "resume"]
    if goal_id is not None:
        command.append(goal_id)
    return subprocess.run(
        command,
        cwd=project_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_life_cycle_survives_restart_and_reuses_promoted_memory(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.setattr("simon.cli.OllamaProvider", LifeCycleProvider)  # type: ignore[attr-defined]

    data_dir = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script_path = workspace / "target.py"
    script_path.write_text('print("BROKEN")\n', encoding="utf-8")

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "goal-propose",
            "--model",
            "integration-model",
            "Corrija o script de integração para imprimir FIXED.",
        ]
    ) == 0

    database_path = data_dir / "simon.db"
    proposal_event_id = _single_value(
        database_path,
        """
        SELECT id FROM events
        WHERE kind = 'cognition.goal_proposal.completed'
        ORDER BY occurred_at DESC, id DESC LIMIT 1
        """,
    )
    assert main(["--data-dir", str(data_dir), "goal-accept", proposal_event_id]) == 0
    goal_id = _single_value(database_path, "SELECT id FROM goals LIMIT 1")

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-propose",
            "--model",
            "integration-model",
            goal_id,
        ]
    ) == 0
    plan_proposal_event_id = _single_value(
        database_path,
        """
        SELECT id FROM events
        WHERE kind = 'cognition.plan_proposal.completed' AND goal_id = ?
        ORDER BY occurred_at DESC, id DESC LIMIT 1
        """,
        (goal_id,),
    )
    assert main(
        ["--data-dir", str(data_dir), "plan-materialize", plan_proposal_event_id]
    ) == 0
    plan_id = _single_value(
        database_path,
        "SELECT id FROM plans WHERE goal_id = ? AND status = 'ACTIVE'",
        (goal_id,),
    )

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-run",
            goal_id,
            "--cwd",
            str(workspace),
            sys.executable,
            str(script_path),
        ]
    ) == 0
    first_run_action = _latest_action_id(database_path, plan_id=plan_id, step_id="step_01")
    assert main(["--data-dir", str(data_dir), "process-verify", first_run_action]) == 0

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-analyze",
            "--model",
            "integration-model",
            goal_id,
        ]
    ) == 0
    first_analysis_action = _latest_action_id(
        database_path, plan_id=plan_id, step_id="step_02"
    )
    assert main(
        [
            "--data-dir",
            str(data_dir),
            "analysis-assess",
            "--model",
            "integration-model",
            first_analysis_action,
        ]
    ) == 0
    first_assessment = _latest_assessment_id(database_path, action_id=first_analysis_action)
    assert main(
        ["--data-dir", str(data_dir), "verification-confirm", first_assessment]
    ) == 0

    restarted = _run_resume_in_new_process(data_dir, goal_id=goal_id)
    assert restarted.returncode == 0, restarted.stderr
    assert "Próximo passo executável: nenhum" in restarted.stdout
    assert "Próximo passo pendente: step_03 | BLOCKED" in restarted.stdout
    assert "Capability pendente: unknown" in restarted.stdout
    assert "CAPABILITY_UNAVAILABLE: unknown" in restarted.stdout
    assert "World mudou desde o Plan: não" in restarted.stdout
    assert "step_02" in restarted.stdout

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-patch",
            goal_id,
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
    patch_action = _latest_action_id(database_path, plan_id=plan_id, step_id="step_03")
    assert main(["--data-dir", str(data_dir), "file-verify", patch_action]) == 0
    assert script_path.read_text(encoding="utf-8") == 'print("FIXED")\n'

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-run",
            goal_id,
            "--cwd",
            str(workspace),
            sys.executable,
            str(script_path),
        ]
    ) == 0
    final_run_action = _latest_action_id(database_path, plan_id=plan_id, step_id="step_04")
    assert main(["--data-dir", str(data_dir), "process-verify", final_run_action]) == 0

    assert main(
        [
            "--data-dir",
            str(data_dir),
            "plan-analyze",
            "--model",
            "integration-model",
            goal_id,
        ]
    ) == 0
    final_analysis_action = _latest_action_id(
        database_path, plan_id=plan_id, step_id="step_05"
    )
    assert main(
        [
            "--data-dir",
            str(data_dir),
            "analysis-assess",
            "--model",
            "integration-model",
            final_analysis_action,
        ]
    ) == 0
    final_assessment = _latest_assessment_id(database_path, action_id=final_analysis_action)
    assert main(
        ["--data-dir", str(data_dir), "verification-confirm", final_assessment]
    ) == 0

    assert main(["--data-dir", str(data_dir), "plan-complete", goal_id]) == 0
    assert main(
        [
            "--data-dir",
            str(data_dir),
            "goal-assess",
            "--model",
            "integration-model",
            goal_id,
        ]
    ) == 0
    goal_assessment = _single_value(
        database_path,
        """
        SELECT id
        FROM verification_results
        WHERE subject_type = 'GOAL' AND subject_id = ? AND status = 'ASSESSED'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (goal_id,),
    )
    assert main(["--data-dir", str(data_dir), "goal-complete", goal_assessment]) == 0

    experience_id = _single_value(
        database_path,
        "SELECT id FROM experiences WHERE goal_id = ? AND status = 'CLOSED'",
        (goal_id,),
    )
    memory_text = (
        "Após uma correção local, reexecutar e verificar a saída antes de concluir o Goal."
    )
    assert main(
        [
            "--data-dir",
            str(data_dir),
            "experience-remember",
            experience_id,
            "--kind",
            "PROCEDURAL",
            "--scope",
            "PROJECT",
            memory_text,
        ]
    ) == 0

    final_restart = _run_resume_in_new_process(data_dir)
    assert final_restart.returncode == 0, final_restart.stderr
    assert "Goals abertos: nenhum" in final_restart.stdout
    assert f"Última Experience: {experience_id} | CLOSED" in final_restart.stdout
    assert "Outcome: SUCCESS" in final_restart.stdout
    assert memory_text in final_restart.stdout

    with sqlite3.connect(database_path) as connection:
        goal_status = connection.execute(
            "SELECT status FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        plan_status = connection.execute(
            "SELECT status FROM plans WHERE id = ?", (plan_id,)
        ).fetchone()
        memory_row = connection.execute(
            """
            SELECT source_experience_ids_json, status
            FROM memories
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        startup_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'system.started'"
        ).fetchone()

    assert goal_status == ("COMPLETED",)
    assert plan_status == ("COMPLETED",)
    assert memory_row is not None
    assert tuple(json.loads(str(memory_row[0]))) == (experience_id,)
    assert memory_row[1] == "ACTIVE"
    assert startup_count is not None and startup_count[0] >= 2
