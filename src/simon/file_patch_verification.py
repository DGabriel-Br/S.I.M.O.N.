from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from simon.actions import Action, get_action_in_connection
from simon.file_patch import FilePatchRequest
from simon.verification import (
    VerificationResult,
    create_verification_result_in_connection,
    list_verification_results_in_connection,
)

VERIFICATION_TYPE = "file.patch.current_state"
VERIFICATION_STRENGTH = 4


@dataclass(frozen=True, slots=True)
class FilePatchVerificationReceipt:
    action: Action
    verification: VerificationResult
    created: bool


def verify_file_patch_state(
    database_path: Path,
    *,
    action_id: str,
) -> FilePatchVerificationReceipt:
    """Relê o alvo de file.patch e compara seu estado atual com o hash produzido pela Action."""
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        action = get_action_in_connection(connection, action_id)
        if action is None:
            raise ValueError(f"action não encontrada: {action_id}")
        _validate_action(action)
        _ensure_latest_step_attempt(connection, action)

        request = _request_from_action(action)
        authorization_event_id = _authorization_event_id(action)
        workspace = _validated_authorized_workspace(
            connection,
            action=action,
            request=request,
            authorization_event_id=authorization_event_id,
        )
        modification_event_id = _modification_event_id(action)
        expected_state = _validated_modification_event(
            connection,
            action=action,
            request=request,
            workspace=workspace,
            modification_event_id=modification_event_id,
        )
        current_state = _observe_current_state(
            workspace=workspace,
            relative_path=request.relative_path,
            expected_target_path=expected_state["target_path"],
            expected_after_sha256=expected_state["after_sha256"],
        )
        status = "VERIFIED" if current_state["current_state"] == "MATCHED" else "FAILED"

        existing = _find_existing_verification(
            connection,
            action_id=action.id,
            modification_event_id=modification_event_id,
            current_state=current_state,
            status=status,
        )
        if existing is not None:
            return FilePatchVerificationReceipt(
                action=action,
                verification=existing,
                created=False,
            )

        observed: dict[str, object] = {
            "verification_type": VERIFICATION_TYPE,
            "authorization_event_id": authorization_event_id,
            "modification_event_id": modification_event_id,
            "target_path": expected_state["target_path"],
            "relative_path": request.relative_path,
            "before_sha256": expected_state["before_sha256"],
            "expected_after_sha256": expected_state["after_sha256"],
            "current_sha256": current_state.get("current_sha256"),
            "current_state": current_state["current_state"],
            "plan_verification_intent": _plan_verification_intent(action),
            "semantic_effect_assessed": False,
        }
        if "detail" in current_state:
            observed["detail"] = current_state["detail"]

        verification = create_verification_result_in_connection(
            connection,
            subject_type="ACTION",
            subject_id=action.id,
            criteria=(
                {
                    "type": VERIFICATION_TYPE,
                    "description": (
                        "O arquivo atual ainda corresponde exatamente ao estado produzido "
                        "pela Action file.patch registrada."
                    ),
                },
            ),
            status=status,
            evidence_event_ids=(modification_event_id,),
            observed=observed,
            strength=VERIFICATION_STRENGTH,
        )
        return FilePatchVerificationReceipt(
            action=action,
            verification=verification,
            created=True,
        )


def _validate_action(action: Action) -> None:
    if action.kind != "file.patch":
        raise ValueError(f"action não representa file.patch: {action.id}")
    if action.status != "COMPLETED":
        raise ValueError(
            "verificação file.patch exige Action COMPLETED: "
            f"{action.id} está {action.status}"
        )


def _ensure_latest_step_attempt(connection: sqlite3.Connection, action: Action) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM actions
        WHERE plan_id = ? AND step_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (action.plan_id, action.step_id),
    ).fetchone()
    if row is None or str(row[0]) != action.id:
        raise ValueError("verificação exige a tentativa mais recente do step")


def _request_from_action(action: Action) -> FilePatchRequest:
    raw = action.input_data.get("request")
    if not isinstance(raw, dict):
        raise TypeError(f"Action file.patch possui request inválido: {action.id}")
    try:
        return FilePatchRequest.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(
            f"Action file.patch possui request persistido inválido: {action.id}"
        ) from exc


def _authorization_event_id(action: Action) -> str:
    value = action.input_data.get("authorization_event_id")
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Action file.patch possui authorization_event_id inválido: {action.id}")
    return value.strip()


def _modification_event_id(action: Action) -> str:
    if action.reported_result is None:
        raise ValueError(f"Action file.patch não possui resultado reportado: {action.id}")
    value = action.reported_result.get("modification_event_id")
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Action file.patch possui modification_event_id inválido: {action.id}")
    return value.strip()


def _plan_verification_intent(action: Action) -> str:
    value = action.input_data.get("verification")
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Action file.patch possui critério do Plan inválido: {action.id}")
    return value.strip()


def _validated_authorized_workspace(
    connection: sqlite3.Connection,
    *,
    action: Action,
    request: FilePatchRequest,
    authorization_event_id: str,
) -> Path:
    row = connection.execute(
        """
        SELECT kind, source, payload_json, goal_id
        FROM events
        WHERE id = ?
        """,
        (authorization_event_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Event de autorização não encontrado: {authorization_event_id}")
    authorization_kind = str(row[0])
    if authorization_kind not in {"file.patch.authorized", "action.retry.authorized"}:
        raise ValueError(f"Event não representa autorização file.patch: {authorization_event_id}")
    if str(row[1]) != "user":
        raise ValueError(f"Event não representa autorização file.patch: {authorization_event_id}")
    if row[3] is None or str(row[3]) != action.goal_id:
        raise ValueError("Event de autorização não pertence ao Goal da Action")

    payload = json.loads(str(row[2]))
    if not isinstance(payload, dict):
        raise TypeError(f"Event de autorização possui payload inválido: {authorization_event_id}")
    if payload.get("plan_id") != action.plan_id:
        raise ValueError("Event de autorização não pertence ao Plan da Action")
    if payload.get("step_id") != action.step_id:
        raise ValueError("Event de autorização não pertence ao step da Action")
    if payload.get("bound_capability") != "file.patch":
        raise ValueError("Event de autorização não confirma capability file.patch")
    if payload.get("relative_path") != request.relative_path:
        raise ValueError("Action e Event de autorização divergem sobre relative_path")
    _validate_retry_authorization(
        connection,
        action=action,
        authorization_kind=authorization_kind,
        authorization_event_id=authorization_event_id,
        payload=payload,
    )

    workspace_value = payload.get("workspace")
    if not isinstance(workspace_value, str) or not workspace_value.strip():
        raise TypeError("Event de autorização possui workspace inválido")
    workspace = Path(workspace_value).expanduser()
    if not workspace.is_absolute():
        raise ValueError("Event de autorização não preservou workspace absoluto")
    return workspace


def _validate_retry_authorization(
    connection: sqlite3.Connection,
    *,
    action: Action,
    authorization_kind: str,
    authorization_event_id: str,
    payload: dict[str, object],
) -> None:
    retry_of_action_id = action.input_data.get("retry_of_action_id")
    if retry_of_action_id is None:
        if authorization_kind != "file.patch.authorized":
            raise ValueError("Action inicial file.patch não pode usar autorização de retry")
        return

    if not isinstance(retry_of_action_id, str) or not retry_of_action_id.strip():
        raise TypeError("Action file.patch possui retry_of_action_id inválido")
    if authorization_kind != "action.retry.authorized":
        raise ValueError("Action de retry file.patch não possui autorização de retry")
    if payload.get("capability") != "file.patch":
        raise ValueError("Event de retry não autoriza capability file.patch")
    if payload.get("retry_of_action_id") != retry_of_action_id:
        raise ValueError("Action e Event de retry divergem sobre tentativa anterior")
    if action.input_data.get("retry_authorization_event_id") != authorization_event_id:
        raise ValueError("Action e Event divergem sobre autorização de retry")

    previous = connection.execute(
        """
        SELECT goal_id, plan_id, step_id, kind, status
        FROM actions
        WHERE id = ?
        """,
        (retry_of_action_id,),
    ).fetchone()
    if previous is None:
        raise ValueError(f"Action anterior do retry não encontrada: {retry_of_action_id}")
    if tuple(str(value) for value in previous[:4]) != (
        action.goal_id,
        action.plan_id,
        action.step_id,
        "file.patch",
    ):
        raise ValueError("Action anterior do retry não pertence ao mesmo file.patch")
    previous_status = str(previous[4])
    if previous_status not in {"FAILED", "INTERRUPTED"}:
        raise ValueError("Action anterior do retry não preserva status operacional elegível")
    if payload.get("previous_status") != previous_status:
        raise ValueError("Event de retry diverge sobre status da tentativa anterior")


def _validated_modification_event(
    connection: sqlite3.Connection,
    *,
    action: Action,
    request: FilePatchRequest,
    workspace: Path,
    modification_event_id: str,
) -> dict[str, str]:
    row = connection.execute(
        """
        SELECT kind, source, payload_json, goal_id
        FROM events
        WHERE id = ?
        """,
        (modification_event_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Event de modificação não encontrado: {modification_event_id}")
    if str(row[0]) != "file.patch.completed" or str(row[1]) != "tool":
        raise ValueError(f"Event não representa file.patch concluído: {modification_event_id}")
    if row[3] is None or str(row[3]) != action.goal_id:
        raise ValueError("Event de modificação não pertence ao Goal da Action")

    payload = json.loads(str(row[2]))
    if not isinstance(payload, dict):
        raise TypeError(f"Event de modificação possui payload inválido: {modification_event_id}")
    if payload.get("action_id") != action.id:
        raise ValueError("Event de modificação não pertence à Action informada")
    if payload.get("plan_id") != action.plan_id:
        raise ValueError("Event de modificação não pertence ao Plan da Action")
    if payload.get("step_id") != action.step_id:
        raise ValueError("Event de modificação não pertence ao step da Action")
    if payload.get("relative_path") != request.relative_path:
        raise ValueError("Action e Event de modificação divergem sobre relative_path")
    retry_of_action_id = action.input_data.get("retry_of_action_id")
    if retry_of_action_id is None:
        if payload.get("retry_of_action_id") is not None:
            raise ValueError("Event de modificação declara retry ausente na Action")
    elif payload.get("retry_of_action_id") != retry_of_action_id:
        raise ValueError("Action e Event de modificação divergem sobre retry_of_action_id")

    target_path = _required_text(payload, "target_path")
    before_sha256 = _required_sha256(payload, "before_sha256")
    after_sha256 = _required_sha256(payload, "after_sha256")
    expected_text_sha256 = _required_sha256(payload, "expected_text_sha256")
    replacement_text_sha256 = _required_sha256(payload, "replacement_text_sha256")

    reported_result = action.reported_result
    if reported_result is None:
        raise ValueError(f"Action file.patch não possui resultado reportado: {action.id}")
    if reported_result.get("target_path") != target_path:
        raise ValueError("Action e Event divergem sobre target_path")
    if reported_result.get("relative_path") != request.relative_path:
        raise ValueError("Action e resultado reportado divergem sobre relative_path")
    if reported_result.get("before_sha256") != before_sha256:
        raise ValueError("Action e Event divergem sobre before_sha256")
    if reported_result.get("after_sha256") != after_sha256:
        raise ValueError("Action e Event divergem sobre after_sha256")

    if _sha256(request.expected_text.encode("utf-8")) != expected_text_sha256:
        raise ValueError("request e Event divergem sobre expected_text")
    if _sha256(request.replacement_text.encode("utf-8")) != replacement_text_sha256:
        raise ValueError("request e Event divergem sobre replacement_text")

    expected_target = workspace.joinpath(*Path(request.relative_path).parts)
    if str(expected_target) != target_path:
        raise ValueError("workspace autorizado e Event divergem sobre target_path")

    return {
        "target_path": target_path,
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
    }


def _observe_current_state(
    *,
    workspace: Path,
    relative_path: str,
    expected_target_path: str,
    expected_after_sha256: str,
) -> dict[str, object]:
    try:
        resolved_workspace = workspace.resolve(strict=True)
        if not resolved_workspace.is_dir():
            return {
                "current_state": "TARGET_UNAVAILABLE",
                "current_sha256": None,
                "detail": f"workspace não é diretório: {resolved_workspace}",
            }

        unresolved_target = resolved_workspace
        for part in Path(relative_path).parts:
            unresolved_target = unresolved_target / part
            if unresolved_target.is_symlink():
                return {
                    "current_state": "TARGET_UNAVAILABLE",
                    "current_sha256": None,
                    "detail": "file.patch verification não atravessa links simbólicos",
                }
        target = unresolved_target.resolve(strict=True)
        try:
            target.relative_to(resolved_workspace)
        except ValueError:
            return {
                "current_state": "TARGET_UNAVAILABLE",
                "current_sha256": None,
                "detail": "arquivo atual resolve para fora do workspace autorizado",
            }
        if not target.is_file():
            return {
                "current_state": "TARGET_UNAVAILABLE",
                "current_sha256": None,
                "detail": f"arquivo alvo inválido: {target}",
            }
        if str(target) != expected_target_path:
            return {
                "current_state": "TARGET_UNAVAILABLE",
                "current_sha256": None,
                "detail": "arquivo atual resolve para caminho diferente do alvo registrado",
            }
        current_sha256 = _sha256(target.read_bytes())
    except (FileNotFoundError, OSError) as exc:
        return {
            "current_state": "TARGET_UNAVAILABLE",
            "current_sha256": None,
            "detail": str(exc),
        }

    return {
        "current_state": (
            "MATCHED" if current_sha256 == expected_after_sha256 else "HASH_MISMATCH"
        ),
        "current_sha256": current_sha256,
    }


def _find_existing_verification(
    connection: sqlite3.Connection,
    *,
    action_id: str,
    modification_event_id: str,
    current_state: dict[str, object],
    status: str,
) -> VerificationResult | None:
    results = list_verification_results_in_connection(
        connection,
        subject_type="ACTION",
        subject_id=action_id,
    )
    if not results:
        return None

    result = results[-1]
    if result.status != status:
        return None
    if result.observed.get("verification_type") != VERIFICATION_TYPE:
        return None
    if result.observed.get("modification_event_id") != modification_event_id:
        return None
    if result.observed.get("current_state") != current_state.get("current_state"):
        return None
    if result.observed.get("current_sha256") != current_state.get("current_sha256"):
        return None
    return result


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Event de modificação possui {key} inválido")
    return value.strip()


def _required_sha256(payload: dict[str, object], key: str) -> str:
    value = _required_text(payload, key).lower()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"Event de modificação possui {key} inválido")
    return value


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
