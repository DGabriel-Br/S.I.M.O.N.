from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from simon.actions import Action
from simon.goal_verification import get_latest_goal_assessment_context
from simon.plan_failure import PlanFailureContext, get_active_plan_failure_context
from simon.plan_proposal import PendingPlanProposal, find_latest_pending_plan_proposal
from simon.plans import Plan
from simon.resume import GoalResumeState, ResumedAction, reconstruct_resume_state
from simon.step_readiness import PlanReadiness, StepBlocker, StepReadiness

ExecutiveOutcome = Literal[
    "PROCEED",
    "NEEDS_USER_INPUT",
    "NEEDS_USER_CONFIRMATION",
    "NEEDS_OPERATION_AUTHORIZATION",
    "NEEDS_GOAL_SELECTION",
    "BLOCKED",
    "DONE",
]

ExecutiveOperation = Literal[
    "plan.propose",
    "plan.materialize",
    "plan.ask",
    "plan.run",
    "plan.patch",
    "plan.analyze",
    "process.verify",
    "file.verify",
    "action.assess",
    "analysis.assess",
    "verification.confirm",
    "action.answer",
    "action.retry",
    "process.retry",
    "analysis.retry",
    "file.retry",
    "plan.complete",
    "goal.assess",
    "goal.complete",
]


@dataclass(frozen=True, slots=True)
class ExecutiveGoalCandidate:
    goal_id: str
    status: str
    title: str


@dataclass(frozen=True, slots=True)
class ExecutiveDecision:
    outcome: ExecutiveOutcome
    reason_code: str
    reason: str
    operation: ExecutiveOperation | None = None
    requires_model: bool = False
    goal_id: str | None = None
    plan_id: str | None = None
    step_id: str | None = None
    action_id: str | None = None
    verification_id: str | None = None
    proposal_event_id: str | None = None
    capability: str | None = None
    blockers: tuple[StepBlocker, ...] = ()
    goal_candidates: tuple[ExecutiveGoalCandidate, ...] = ()

    def __post_init__(self) -> None:
        if not self.reason_code.strip() or not self.reason.strip():
            raise ValueError("ExecutiveDecision exige reason_code e reason")
        if self.outcome == "PROCEED" and self.operation is None:
            raise ValueError("ExecutiveDecision PROCEED exige uma operação")
        if (
            self.outcome in {"DONE", "BLOCKED", "NEEDS_GOAL_SELECTION"}
            and self.operation is not None
        ):
            raise ValueError(f"ExecutiveDecision {self.outcome} não pode executar operação")
        if self.requires_model and self.operation is None:
            raise ValueError("requires_model exige uma operação")


def decide_next(
    database_path: Path,
    *,
    goal_id: str | None = None,
) -> ExecutiveDecision:
    """Decide uma única próxima operação legítima sem alterar o estado persistido."""
    overview = reconstruct_resume_state(database_path, goal_id=goal_id)
    state = overview.selected

    if state is None:
        if len(overview.open_goals) > 1:
            return ExecutiveDecision(
                outcome="NEEDS_GOAL_SELECTION",
                reason_code="multiple_open_goals",
                reason="há mais de um Goal aberto e o Executive não escolhe foco arbitrariamente",
                goal_candidates=tuple(
                    ExecutiveGoalCandidate(
                        goal_id=goal.id,
                        status=goal.status,
                        title=goal.title,
                    )
                    for goal in overview.open_goals
                ),
            )
        return ExecutiveDecision(
            outcome="DONE",
            reason_code="no_open_goal",
            reason="não existe Goal aberto para conduzir",
        )

    goal = state.goal
    if goal.status == "COMPLETED":
        return _decision(
            state,
            outcome="DONE",
            reason_code="goal_completed",
            reason="o Goal selecionado já está COMPLETED",
        )
    if goal.status != "ACTIVE":
        return _decision(
            state,
            outcome="BLOCKED",
            reason_code="goal_not_active",
            reason=f"o Goal selecionado está {goal.status}; o Executive não muda seu lifecycle",
        )

    plan = state.plan
    if plan is None:
        pending = find_latest_pending_plan_proposal(database_path, goal_id=goal.id)
        if pending is not None and _matches_initial_plan_need(pending):
            return _decision(
                state,
                outcome="PROCEED",
                reason_code="plan_proposal_ready_to_materialize",
                reason="já existe uma proposta de Plan concluída e ainda não materializada",
                operation="plan.materialize",
                proposal_event_id=pending.event_id,
            )
        return _decision(
            state,
            outcome="PROCEED",
            reason_code="plan_required",
            reason="o Goal ACTIVE ainda não possui Plan",
            operation="plan.propose",
            requires_model=True,
        )

    if plan.status == "ACTIVE":
        readiness = state.readiness
        if readiness is None:
            raise RuntimeError("Goal com Plan ACTIVE foi reconstruído sem PlanReadiness")
        return _decide_active_plan(database_path, state=state, readiness=readiness)

    if plan.status == "COMPLETED":
        return _decide_completed_plan(database_path, state=state, plan=plan)

    return _decision(
        state,
        outcome="PROCEED",
        reason_code="replacement_plan_required",
        reason=f"o último Plan está {plan.status} e o Goal continua ACTIVE",
        operation="plan.propose",
        requires_model=True,
    )


def _decide_active_plan(
    database_path: Path,
    *,
    state: GoalResumeState,
    readiness: PlanReadiness,
) -> ExecutiveDecision:
    in_progress = next((step for step in readiness.steps if step.state == "IN_PROGRESS"), None)
    if in_progress is not None:
        resumed = _latest_action(state, plan_id=readiness.plan.id, step_id=in_progress.step_id)
        if resumed is None:
            raise RuntimeError(f"step IN_PROGRESS sem Action reconstruída: {in_progress.step_id}")
        action = resumed.action
        if action.kind == "user.ask" and action.status == "WAITING":
            return _step_decision(
                state,
                readiness.plan,
                in_progress,
                outcome="NEEDS_USER_INPUT",
                reason_code="user_response_required",
                reason="uma Action user.ask está aguardando resposta real do usuário",
                operation="action.answer",
                action_id=action.id,
            )
        return _step_decision(
            state,
            readiness.plan,
            in_progress,
            outcome="BLOCKED",
            reason_code="action_in_progress",
            reason=f"a Action atual ainda está {action.status}",
            action_id=action.id,
        )

    pending_verification = _step_with_blocker(readiness, "VERIFICATION_PENDING")
    if pending_verification is not None:
        step, blocker = pending_verification
        resumed = _required_latest_action(state, readiness.plan.id, step.step_id)
        operation, requires_model = _verification_operation(resumed.action)
        if operation is None:
            return _step_decision(
                state,
                readiness.plan,
                step,
                outcome="BLOCKED",
                reason_code="verification_operation_unknown",
                reason=f"não existe verificador executivo conhecido para {resumed.action.kind}",
                action_id=resumed.action.id,
                blockers=step.blockers,
            )
        return _step_decision(
            state,
            readiness.plan,
            step,
            outcome="PROCEED",
            reason_code="verification_pending",
            reason="a tentativa mais recente terminou e precisa da próxima Verification",
            operation=operation,
            requires_model=requires_model,
            action_id=resumed.action.id,
            blockers=(blocker,),
        )

    confirmation = _step_with_blocker(
        readiness,
        "ASSESSED_SATISFIED_REQUIRES_CONFIRMATION",
    )
    if confirmation is not None:
        step, blocker = confirmation
        resumed = _required_latest_action(state, readiness.plan.id, step.step_id)
        return _step_decision(
            state,
            readiness.plan,
            step,
            outcome="NEEDS_USER_CONFIRMATION",
            reason_code="assessment_confirmation_required",
            reason="um assessment SATISFIED exige confirmação humana antes de virar VERIFIED",
            operation="verification.confirm",
            action_id=resumed.action.id,
            verification_id=blocker.detail,
            blockers=(blocker,),
        )

    user_ask_review = _user_ask_review(readiness, state)
    if user_ask_review is not None:
        step, blocker, action = user_ask_review
        return _step_decision(
            state,
            readiness.plan,
            step,
            outcome="PROCEED",
            reason_code="user_ask_retry_required",
            reason="a resposta anterior não satisfez o critério e a coleta pode ser refeita",
            operation="action.retry",
            action_id=action.id,
            verification_id=blocker.detail,
            blockers=(blocker,),
        )

    retry = _retry_decision(state, readiness)
    if retry is not None:
        return retry

    failure = get_active_plan_failure_context(database_path, goal_id=state.goal.id)
    if failure is not None:
        step = _required_step(readiness, failure.step_id)
        blocker = next(
            blocker for blocker in step.blockers if blocker.kind == failure.blocker_kind
        )
        pending = find_latest_pending_plan_proposal(database_path, goal_id=state.goal.id)
        if pending is not None and _matches_plan_failure(pending, failure):
            return _step_decision(
                state,
                readiness.plan,
                step,
                outcome="PROCEED",
                reason_code="replan_proposal_ready_to_materialize",
                reason=(
                    "a proposta de replanejamento atual já foi concluída e pode ser materializada"
                ),
                operation="plan.materialize",
                action_id=failure.action_id,
                verification_id=failure.verification_id,
                proposal_event_id=pending.event_id,
                blockers=(blocker,),
            )
        return _step_decision(
            state,
            readiness.plan,
            step,
            outcome="PROCEED",
            reason_code="replanning_required",
            reason="evidência negativa ou inconclusiva invalida a continuação da estratégia atual",
            operation="plan.propose",
            requires_model=True,
            action_id=failure.action_id,
            verification_id=failure.verification_id,
            blockers=(blocker,),
        )

    next_step = readiness.next_step
    if next_step is not None:
        return _ready_step_decision(state, readiness.plan, next_step)

    file_patch_step = _bindable_file_patch_step(readiness)
    if file_patch_step is not None:
        return _step_decision(
            state,
            readiness.plan,
            file_patch_step,
            outcome="NEEDS_OPERATION_AUTHORIZATION",
            reason_code="file_patch_authorization_required",
            reason="o CHANGE/unknown pode ser ligado a file.patch, mas requer autorização concreta",
            operation="plan.patch",
            capability="file.patch",
            blockers=file_patch_step.blockers,
        )

    if all(step.state == "VERIFIED" for step in readiness.steps):
        return _decision(
            state,
            outcome="PROCEED",
            reason_code="plan_ready_for_completion",
            reason="todos os steps atuais estão VERIFIED",
            operation="plan.complete",
            plan_id=readiness.plan.id,
        )

    blocked_step = next((step for step in readiness.steps if step.state != "VERIFIED"), None)
    if blocked_step is None:
        raise RuntimeError("Plan ACTIVE sem próximo step e sem step pendente")
    return _step_decision(
        state,
        readiness.plan,
        blocked_step,
        outcome="BLOCKED",
        reason_code="plan_blocked",
        reason="o próximo step não possui recovery ou operação executiva legítima neste corte",
        blockers=blocked_step.blockers,
    )


def _decide_completed_plan(
    database_path: Path,
    *,
    state: GoalResumeState,
    plan: Plan,
) -> ExecutiveDecision:
    assessment = get_latest_goal_assessment_context(database_path, state.goal.id)
    if (
        assessment is None
        or assessment.plan_id != plan.id
        or assessment.plan_revision != plan.revision
    ):
        return _decision(
            state,
            outcome="PROCEED",
            reason_code="goal_assessment_required",
            reason="o Plan está COMPLETED e ainda precisa de assessment semântico do Goal",
            operation="goal.assess",
            requires_model=True,
            plan_id=plan.id,
        )

    if assessment.verdict == "SATISFIED":
        return _decision(
            state,
            outcome="NEEDS_USER_CONFIRMATION",
            reason_code="goal_completion_confirmation_required",
            reason="o Goal foi avaliado como SATISFIED e exige confirmação humana para concluir",
            operation="goal.complete",
            plan_id=plan.id,
            verification_id=assessment.verification_id,
        )

    pending = find_latest_pending_plan_proposal(database_path, goal_id=state.goal.id)
    if pending is not None and _matches_completed_plan_continuation(
        pending,
        plan=plan,
        assessment_verification_id=assessment.verification_id,
    ):
        return _decision(
            state,
            outcome="PROCEED",
            reason_code="continuation_proposal_ready_to_materialize",
            reason="a proposta de continuação do Goal já foi concluída e pode ser materializada",
            operation="plan.materialize",
            plan_id=plan.id,
            verification_id=assessment.verification_id,
            proposal_event_id=pending.event_id,
        )

    return _decision(
        state,
        outcome="PROCEED",
        reason_code="goal_continuation_required",
        reason=(
            "o assessment do Goal não permite conclusão; uma nova estratégia precisa ser proposta"
        ),
        operation="plan.propose",
        requires_model=True,
        plan_id=plan.id,
        verification_id=assessment.verification_id,
    )


def _ready_step_decision(
    state: GoalResumeState,
    plan: Plan,
    step: StepReadiness,
) -> ExecutiveDecision:
    if step.capability == "user.ask":
        return _step_decision(
            state,
            plan,
            step,
            outcome="PROCEED",
            reason_code="user_ask_ready",
            reason="o próximo step pode criar uma pergunta ao usuário sem fabricar a resposta",
            operation="plan.ask",
        )
    if step.capability == "cognition.analyze":
        return _step_decision(
            state,
            plan,
            step,
            outcome="PROCEED",
            reason_code="cognition_analysis_ready",
            reason="o próximo step cognitivo está READY",
            operation="plan.analyze",
            requires_model=True,
        )
    if step.capability == "process.run":
        return _step_decision(
            state,
            plan,
            step,
            outcome="NEEDS_OPERATION_AUTHORIZATION",
            reason_code="process_authorization_required",
            reason="o process.run está READY, mas a execução concreta exige autorização explícita",
            operation="plan.run",
        )
    if step.capability == "file.patch":
        return _step_decision(
            state,
            plan,
            step,
            outcome="NEEDS_OPERATION_AUTHORIZATION",
            reason_code="file_patch_authorization_required",
            reason="o file.patch está READY, mas a alteração concreta exige autorização explícita",
            operation="plan.patch",
        )
    return _step_decision(
        state,
        plan,
        step,
        outcome="BLOCKED",
        reason_code="ready_capability_not_executable_by_executive",
        reason=f"a capability READY ainda não possui condução executiva: {step.capability}",
    )


def _retry_decision(
    state: GoalResumeState,
    readiness: PlanReadiness,
) -> ExecutiveDecision | None:
    for step in readiness.steps:
        review = next(
            (
                blocker
                for blocker in step.blockers
                if blocker.kind == "PREVIOUS_ATTEMPT_REQUIRES_REVIEW"
            ),
            None,
        )
        if review is None:
            continue
        resumed = _latest_action(state, plan_id=readiness.plan.id, step_id=step.step_id)
        if resumed is None:
            raise RuntimeError(f"review de tentativa sem Action reconstruída: {step.step_id}")
        action = resumed.action

        if action.kind == "process.run" and _only_blockers(
            step,
            {"PREVIOUS_ATTEMPT_REQUIRES_REVIEW"},
        ):
            operation: ExecutiveOperation | None = "process.retry"
        elif action.kind == "cognition.analyze" and _only_blockers(
            step,
            {"PREVIOUS_ATTEMPT_REQUIRES_REVIEW"},
        ):
            operation = "analysis.retry"
        elif action.kind == "file.patch" and _file_patch_retry_blockers(step):
            operation = "file.retry"
        else:
            continue

        return _step_decision(
            state,
            readiness.plan,
            step,
            outcome="NEEDS_OPERATION_AUTHORIZATION",
            reason_code="retry_authorization_required",
            reason=f"a tentativa {action.status} pode ser refeita somente por retry autorizado",
            operation=operation,
            action_id=action.id,
            blockers=step.blockers,
        )
    return None


def _verification_operation(
    action: Action,
) -> tuple[ExecutiveOperation | None, bool]:
    if action.kind == "process.run":
        return "process.verify", False
    if action.kind == "file.patch":
        return "file.verify", False
    if action.kind == "cognition.analyze":
        return "analysis.assess", True
    if action.kind == "user.ask":
        return "action.assess", True
    return None, False


def _user_ask_review(
    readiness: PlanReadiness,
    state: GoalResumeState,
) -> tuple[StepReadiness, StepBlocker, Action] | None:
    review_kinds = {"CRITERION_NOT_SATISFIED", "ASSESSMENT_INCONCLUSIVE"}
    for step in readiness.steps:
        blocker = next(
            (candidate for candidate in step.blockers if candidate.kind in review_kinds),
            None,
        )
        if blocker is None:
            continue
        resumed = _latest_action(state, plan_id=readiness.plan.id, step_id=step.step_id)
        if resumed is None or resumed.action.kind != "user.ask":
            continue
        if not _only_blockers(step, review_kinds):
            continue
        return step, blocker, resumed.action
    return None


def _matches_initial_plan_need(proposal: PendingPlanProposal) -> bool:
    return (
        proposal.source_active_plan_id is None
        and proposal.source_completed_plan_id is None
        and proposal.source_goal_assessment_id is None
    )


def _matches_plan_failure(
    proposal: PendingPlanProposal,
    failure: PlanFailureContext,
) -> bool:
    return (
        proposal.source_active_plan_id == failure.plan_id
        and proposal.source_active_plan_revision == failure.plan_revision
        and proposal.source_failure_verification_id == failure.verification_id
    )


def _matches_completed_plan_continuation(
    proposal: PendingPlanProposal,
    *,
    plan: Plan,
    assessment_verification_id: str,
) -> bool:
    return (
        proposal.source_completed_plan_id == plan.id
        and proposal.source_goal_assessment_id == assessment_verification_id
        and proposal.source_active_plan_id is None
    )


def _bindable_file_patch_step(readiness: PlanReadiness) -> StepReadiness | None:
    for step in readiness.steps:
        if step.state != "BLOCKED" or step.capability != "unknown":
            continue
        if tuple((blocker.kind, blocker.detail) for blocker in step.blockers) != (
            ("CAPABILITY_UNAVAILABLE", "unknown"),
        ):
            continue
        raw_step = _raw_step(readiness.plan, step.step_id)
        if raw_step.get("intent_role") == "CHANGE" and raw_step.get("intent_actor") == "SIMON":
            return step
    return None


def _file_patch_retry_blockers(step: StepReadiness) -> bool:
    return tuple((blocker.kind, blocker.detail) for blocker in step.blockers) == (
        ("PREVIOUS_ATTEMPT_REQUIRES_REVIEW", step.blockers[0].detail),
        ("CAPABILITY_UNAVAILABLE", "unknown"),
    )


def _only_blockers(step: StepReadiness, allowed: set[str]) -> bool:
    return bool(step.blockers) and all(blocker.kind in allowed for blocker in step.blockers)


def _step_with_blocker(
    readiness: PlanReadiness,
    kind: str,
) -> tuple[StepReadiness, StepBlocker] | None:
    for step in readiness.steps:
        for blocker in step.blockers:
            if blocker.kind == kind:
                return step, blocker
    return None


def _required_step(readiness: PlanReadiness, step_id: str) -> StepReadiness:
    step = next((candidate for candidate in readiness.steps if candidate.step_id == step_id), None)
    if step is None:
        raise RuntimeError(f"step não encontrado no readiness: {step_id}")
    return step


def _latest_action(
    state: GoalResumeState,
    *,
    plan_id: str,
    step_id: str,
) -> ResumedAction | None:
    matching = [
        resumed
        for resumed in state.actions
        if resumed.action.plan_id == plan_id and resumed.action.step_id == step_id
    ]
    return matching[-1] if matching else None


def _required_latest_action(
    state: GoalResumeState,
    plan_id: str,
    step_id: str,
) -> ResumedAction:
    resumed = _latest_action(state, plan_id=plan_id, step_id=step_id)
    if resumed is None:
        raise RuntimeError(f"step bloqueado sem tentativa reconstruída: {step_id}")
    return resumed


def _raw_step(plan: Plan, step_id: str) -> dict[str, object]:
    raw_step = next((step for step in plan.steps if step.get("id") == step_id), None)
    if raw_step is None:
        raise RuntimeError(f"step não encontrado no Plan persistido: {step_id}")
    return raw_step


def _decision(
    state: GoalResumeState,
    *,
    outcome: ExecutiveOutcome,
    reason_code: str,
    reason: str,
    operation: ExecutiveOperation | None = None,
    requires_model: bool = False,
    plan_id: str | None = None,
    step_id: str | None = None,
    action_id: str | None = None,
    verification_id: str | None = None,
    proposal_event_id: str | None = None,
    capability: str | None = None,
    blockers: tuple[StepBlocker, ...] = (),
) -> ExecutiveDecision:
    return ExecutiveDecision(
        outcome=outcome,
        reason_code=reason_code,
        reason=reason,
        operation=operation,
        requires_model=requires_model,
        goal_id=state.goal.id,
        plan_id=plan_id if plan_id is not None else (state.plan.id if state.plan else None),
        step_id=step_id,
        action_id=action_id,
        verification_id=verification_id,
        proposal_event_id=proposal_event_id,
        capability=capability,
        blockers=blockers,
    )


def _step_decision(
    state: GoalResumeState,
    plan: Plan,
    step: StepReadiness,
    *,
    outcome: ExecutiveOutcome,
    reason_code: str,
    reason: str,
    operation: ExecutiveOperation | None = None,
    requires_model: bool = False,
    action_id: str | None = None,
    verification_id: str | None = None,
    proposal_event_id: str | None = None,
    capability: str | None = None,
    blockers: tuple[StepBlocker, ...] = (),
) -> ExecutiveDecision:
    return _decision(
        state,
        outcome=outcome,
        reason_code=reason_code,
        reason=reason,
        operation=operation,
        requires_model=requires_model,
        plan_id=plan.id,
        step_id=step.step_id,
        action_id=action_id,
        verification_id=verification_id,
        proposal_event_id=proposal_event_id,
        capability=capability if capability is not None else step.capability,
        blockers=blockers,
    )
