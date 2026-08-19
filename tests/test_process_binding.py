from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from simon.plans import Plan
from simon.process_binding import ProcessRunRequest, bind_process_run_step


def _plan(*, status: str = "ACTIVE", capability: str = "process.run", kind: str = "WORLD") -> Plan:
    now = datetime.now(UTC)
    return Plan(
        id="pln_process_binding",
        goal_id="gol_process_binding",
        revision=3,
        based_on_world_revision=7,
        steps=(
            {
                "id": "step_01",
                "description": "Executar: texto humano que não é protocolo operacional",
                "kind": kind,
                "depends_on": [],
                "preconditions": [],
                "capability": capability,
                "capability_detail": None,
                "verification": "A execução produziu saída observável.",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
        ),
        status=status,
        created_at=now,
        updated_at=now,
    )


def _request() -> ProcessRunRequest:
    return ProcessRunRequest(
        executable="python",
        arguments=["C:\\projeto\\script.py", "--mode", "check"],
        working_directory="C:\\projeto",
        timeout_seconds=45,
    )


def test_process_run_request_keeps_command_components_structured() -> None:
    request = _request()

    assert request.executable == "python"
    assert request.arguments == ("C:\\projeto\\script.py", "--mode", "check")
    assert request.working_directory == "C:\\projeto"
    assert request.timeout_seconds == 45
    assert request.argv() == (
        "python",
        "C:\\projeto\\script.py",
        "--mode",
        "check",
    )


def test_process_run_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="shell"):
        ProcessRunRequest(
            executable="python",
            working_directory="C:\\projeto",
            shell=True,
        )


def test_process_run_request_rejects_invalid_timeout() -> None:
    with pytest.raises(ValidationError, match="timeout_seconds"):
        ProcessRunRequest(
            executable="python",
            working_directory="C:\\projeto",
            timeout_seconds=0,
        )


def test_binding_preserves_explicit_request_without_parsing_description() -> None:
    plan = _plan()
    request = _request()

    binding = bind_process_run_step(plan, step_id="step_01", request=request)

    assert binding.goal_id == plan.goal_id
    assert binding.plan_id == plan.id
    assert binding.plan_revision == 3
    assert binding.step_id == "step_01"
    assert binding.capability == "process.run"
    assert binding.verification == "A execução produziu saída observável."
    assert binding.request is request
    assert binding.request.argv()[0] == "python"
    assert "texto humano" not in binding.request.argv()


def test_binding_rejects_non_process_run_step() -> None:
    with pytest.raises(ValueError, match="exige capability process.run"):
        bind_process_run_step(
            _plan(capability="cognition.analyze", kind="EPISTEMIC"),
            step_id="step_01",
            request=_request(),
        )


def test_binding_rejects_inactive_plan() -> None:
    with pytest.raises(ValueError, match="exige plan ACTIVE"):
        bind_process_run_step(
            _plan(status="COMPLETED"),
            step_id="step_01",
            request=_request(),
        )
