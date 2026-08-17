from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from simon.actions import Action, create_action_in_connection, transition_action_in_connection
from simon.events import Event
from simon.plans import Plan
from simon.step_readiness import PlanReadiness, StepReadiness, evaluate_active_plan

PatchPath = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1024),
]
PatchText = Annotated[
    str,
    StringConstraints(max_length=100_000),
]
ExpectedPatchText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100_000),
]


class FilePatchRequest(BaseModel):
    """Substituição textual localizada dentro de um workspace explicitamente autorizado."""

    model_config = ConfigDict(extra="forbid")

    workspace: PatchPath = Field(
        description="Diretório raiz autorizado para a modificação local."
    )
    relative_path: PatchPath = Field(
        description="Caminho relativo ao workspace; caminhos absolutos e '..' são proibidos."
    )
    expected_text: ExpectedPatchText = Field(
        description="Trecho UTF-8 que precisa existir exatamente uma vez antes da alteração."
    )
    replacement_text: PatchText = Field(
        description="Novo trecho UTF-8 que substituirá expected_text. Pode ser vazio para remoção."
    )

    @model_validator(mode="after")
    def validate_patch_shape(self) -> Self:
        if self.expected_text == self.replacement_text:
            raise ValueError("file.patch exige uma mudança efetiva")

        windows_path = PureWindowsPath(self.relative_path)
        posix_path = PurePosixPath(self.relative_path)
        if (
            windows_path.is_absolute()
            or bool(windows_path.drive)
            or bool(windows_path.root)
            or posix_path.is_absolute()
            or bool(posix_path.root)
        ):
            raise ValueError("relative_path precisa permanecer relativo ao workspace")
        if ".." in windows_path.parts or ".." in posix_path.parts:
            raise ValueError("relative_path não pode sair do workspace com '..'")
        return self


@dataclass(frozen=True, slots=True)
class FilePatchBinding:
    goal_id: str
    plan_id: str
    plan_revision: int
    step_id: str
    verification: str
    capability_detail: str
    request: FilePatchRequest


@dataclass(frozen=True, slots=True)
class FilePatchReceipt:
    action: Action
    binding: FilePatchBinding
    authorization_event_id: str
    modification_event_id: str
    target_path: str
    before_sha256: str | None
    after_sha256: str | None


def bind_file_patch_step(
    plan: Plan,
    *,
    step_id: str,
    request: FilePatchRequest,
) -> FilePatchBinding:
    """Liga explicitamente um CHANGE/unknown a file.patch sem reinterpretar sua descrição."""
    if plan.status != "ACTIVE":
        raise ValueError(f"file.patch exige Plan ACTIVE: {plan.id}")

    raw_step = _plan_step(plan, step_id)
    if _required_text(raw_step, "kind") != "WORLD":
        raise ValueError("file.patch exige step WORLD")
    if _required_text(raw_step, "intent_role") != "CHANGE":
        raise ValueError("file.patch só pode resolver um step intent_role=CHANGE")
    if _required_text(raw_step, "intent_actor") != "SIMON":
        raise ValueError("file.patch só pode resolver mudança atribuída ao SIMON")

    capability = _required_text(raw_step, "capability")
    if capability != "unknown":
        raise ValueError(f"file.patch v0.1 resolve somente capability unknown: {capability}")

    capability_detail = _required_text(raw_step, "capability_detail")
    verification = _required_text(raw_step, "verification")
    return FilePatchBinding(
        goal_id=plan.goal_id,
        plan_id=plan.id,
        plan_revision=plan.revision,
        step_id=step_id,
        verification=verification,
        capability_detail=capability_detail,
        request=request,
    )


def execute_next_file_patch(
    database_path: Path,
    *,
    goal_id: str,
    request: FilePatchRequest,
    trace_id: str | None = None,
) -> FilePatchReceipt:
    """Resolve explicitamente o próximo CHANGE/unknown e aplica uma substituição localizada."""
    readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    step = _next_bindable_file_patch_step(readiness)
    if step is None:
        raise ValueError("plan não possui step CHANGE/unknown elegível para file.patch")

    binding = bind_file_patch_step(
        readiness.plan,
        step_id=step.step_id,
        request=request,
    )
    workspace, target = _resolve_target(request)
    patch_trace_id = trace_id or f"trc_{uuid4().hex}"

    authorization_event = Event.create(
        kind="file.patch.authorized",
        source="user",
        payload={
            "plan_id": binding.plan_id,
            "plan_revision": binding.plan_revision,
            "step_id": binding.step_id,
            "bound_capability": "file.patch",
            "workspace": str(workspace),
            "relative_path": request.relative_path,
        },
        trace_id=patch_trace_id,
        goal_id=binding.goal_id,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_step_has_no_attempt(connection, binding)
        action = create_action_in_connection(
            connection,
            goal_id=binding.goal_id,
            plan_id=binding.plan_id,
            step_id=binding.step_id,
            kind="file.patch",
            input_data={
                "request": request.model_dump(mode="json"),
                "verification": binding.verification,
                "capability_detail": binding.capability_detail,
                "authorization_event_id": authorization_event.id,
                "bound_from_capability": "unknown",
            },
        )
        running = transition_action_in_connection(connection, action.id, "RUNNING")
        _insert_event(connection, authorization_event)
        _insert_event(
            connection,
            Event.create(
                kind="file.patch.started",
                source="tool",
                payload={
                    "action_id": running.id,
                    "plan_id": running.plan_id,
                    "step_id": running.step_id,
                    "target_path": str(target),
                    "relative_path": request.relative_path,
                },
                trace_id=patch_trace_id,
                goal_id=running.goal_id,
            ),
        )

    try:
        before = target.read_bytes()
        expected = request.expected_text.encode("utf-8")
        replacement = request.replacement_text.encode("utf-8")
        occurrences = before.count(expected)
        if occurrences != 1:
            return _record_failure(
                database_path,
                binding=binding,
                action_id=running.id,
                authorization_event_id=authorization_event.id,
                target=target,
                trace_id=patch_trace_id,
                failure_kind="expected_text_not_unique",
                message=(
                    "expected_text precisa ocorrer exatamente uma vez; "
                    f"ocorrências encontradas: {occurrences}"
                ),
            )

        before.decode("utf-8")
        after = before.replace(expected, replacement, 1)
        before_sha256 = _sha256(before)
        after_sha256 = _sha256(after)
        _atomic_replace(target, after)
    except UnicodeDecodeError as exc:
        return _record_failure(
            database_path,
            binding=binding,
            action_id=running.id,
            authorization_event_id=authorization_event.id,
            target=target,
            trace_id=patch_trace_id,
            failure_kind="unsupported_encoding",
            message=f"file.patch v0.1 exige arquivo UTF-8: {exc}",
        )
    except OSError as exc:
        return _record_failure(
            database_path,
            binding=binding,
            action_id=running.id,
            authorization_event_id=authorization_event.id,
            target=target,
            trace_id=patch_trace_id,
            failure_kind="filesystem_write",
            message=str(exc),
        )

    modification_event = Event.create(
        kind="file.patch.completed",
        source="tool",
        payload={
            "action_id": running.id,
            "plan_id": running.plan_id,
            "step_id": running.step_id,
            "target_path": str(target),
            "relative_path": request.relative_path,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "expected_text_sha256": _sha256(expected),
            "replacement_text_sha256": _sha256(replacement),
        },
        trace_id=patch_trace_id,
        goal_id=running.goal_id,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        completed = transition_action_in_connection(
            connection,
            running.id,
            "COMPLETED",
            reported_result={
                "modification_event_id": modification_event.id,
                "target_path": str(target),
                "relative_path": request.relative_path,
                "before_sha256": before_sha256,
                "after_sha256": after_sha256,
            },
        )
        _insert_event(connection, modification_event)

    return FilePatchReceipt(
        action=completed,
        binding=binding,
        authorization_event_id=authorization_event.id,
        modification_event_id=modification_event.id,
        target_path=str(target),
        before_sha256=before_sha256,
        after_sha256=after_sha256,
    )


def _next_bindable_file_patch_step(readiness: PlanReadiness) -> StepReadiness | None:
    for step in readiness.steps:
        if step.state != "BLOCKED" or step.capability != "unknown":
            continue
        if len(step.blockers) != 1:
            continue
        blocker = step.blockers[0]
        if blocker.kind != "CAPABILITY_UNAVAILABLE" or blocker.detail != "unknown":
            continue
        raw_step = _plan_step(readiness.plan, step.step_id)
        if raw_step.get("intent_role") == "CHANGE" and raw_step.get("intent_actor") == "SIMON":
            return step
    return None


def _resolve_target(request: FilePatchRequest) -> tuple[Path, Path]:
    workspace = Path(request.workspace).expanduser().resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError(f"workspace não é diretório: {workspace}")

    unresolved_target = workspace
    for part in Path(request.relative_path).parts:
        unresolved_target = unresolved_target / part
        if unresolved_target.is_symlink():
            raise ValueError("file.patch v0.1 não atravessa links simbólicos")
    target = unresolved_target.resolve(strict=True)
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("arquivo alvo resolve para fora do workspace autorizado") from exc
    if not target.is_file():
        raise ValueError(f"arquivo alvo inválido: {target}")
    return workspace, target


def _atomic_replace(target: Path, content: bytes) -> None:
    mode = stat.S_IMODE(target.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".simon-tmp",
        dir=target.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, target)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _record_failure(
    database_path: Path,
    *,
    binding: FilePatchBinding,
    action_id: str,
    authorization_event_id: str,
    target: Path,
    trace_id: str,
    failure_kind: str,
    message: str,
) -> FilePatchReceipt:
    failure_event = Event.create(
        kind="file.patch.failed",
        source="tool",
        payload={
            "action_id": action_id,
            "plan_id": binding.plan_id,
            "step_id": binding.step_id,
            "target_path": str(target),
            "relative_path": binding.request.relative_path,
            "failure_kind": failure_kind,
            "message": message,
        },
        trace_id=trace_id,
        goal_id=binding.goal_id,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        failed = transition_action_in_connection(
            connection,
            action_id,
            "FAILED",
            failure={
                "kind": failure_kind,
                "message": message,
                "failure_event_id": failure_event.id,
            },
        )
        _insert_event(connection, failure_event)

    return FilePatchReceipt(
        action=failed,
        binding=binding,
        authorization_event_id=authorization_event_id,
        modification_event_id=failure_event.id,
        target_path=str(target),
        before_sha256=None,
        after_sha256=None,
    )


def _ensure_step_has_no_attempt(
    connection: sqlite3.Connection,
    binding: FilePatchBinding,
) -> None:
    row = connection.execute(
        """
        SELECT id, status
        FROM actions
        WHERE plan_id = ? AND step_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (binding.plan_id, binding.step_id),
    ).fetchone()
    if row is not None:
        raise ValueError(
            "step CHANGE já possui tentativa registrada: "
            f"{row[0]} ({row[1]})"
        )


def _plan_step(plan: Plan, step_id: str) -> dict[str, object]:
    for raw_step in plan.steps:
        if raw_step.get("id") == step_id:
            return raw_step
    raise ValueError(f"passo não encontrado no Plan: {step_id}")


def _required_text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} possui tipo inválido")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{key} não pode ser vazio")
    return normalized


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _insert_event(connection: sqlite3.Connection, event: Event) -> None:
    connection.execute(
        """
        INSERT INTO events (
            id,
            kind,
            occurred_at,
            source,
            payload_json,
            trace_id,
            related_entity_ids_json,
            goal_id,
            experience_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.kind,
            event.occurred_at.isoformat(),
            event.source,
            json.dumps(event.payload, ensure_ascii=False, separators=(",", ":")),
            event.trace_id,
            json.dumps(event.related_entity_ids, separators=(",", ":")),
            event.goal_id,
            event.experience_id,
        ),
    )
