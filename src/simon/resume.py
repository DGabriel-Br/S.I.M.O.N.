from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from simon.actions import Action, list_actions_for_plan
from simon.experiences import Experience, get_latest_experience
from simon.goals import Goal, get_goal, list_open_goals
from simon.memories import Memory, retrieve_memories
from simon.plans import Plan, get_active_plan, list_plans_for_goal
from simon.step_readiness import PlanReadiness, evaluate_active_plan
from simon.verification import list_verification_results
from simon.world import get_world_revision


@dataclass(frozen=True, slots=True)
class ResumedAction:
    action: Action
    latest_verification_id: str | None
    latest_verification_status: str | None


@dataclass(frozen=True, slots=True)
class GoalResumeState:
    goal: Goal
    plan: Plan | None
    readiness: PlanReadiness | None
    actions: tuple[ResumedAction, ...]
    current_world_revision: int
    world_changed_since_plan: bool | None
    latest_experience: Experience | None
    memories: tuple[Memory, ...]


@dataclass(frozen=True, slots=True)
class ResumeOverview:
    current_world_revision: int
    open_goals: tuple[Goal, ...]
    selected: GoalResumeState | None
    latest_experience: Experience | None
    memories: tuple[Memory, ...]


def reconstruct_resume_state(
    database_path: Path,
    *,
    goal_id: str | None = None,
    memory_limit: int = 5,
) -> ResumeOverview:
    if memory_limit <= 0:
        raise ValueError("memory_limit precisa ser positivo")

    world_revision = get_world_revision(database_path)
    open_goals = tuple(
        sorted(
            list_open_goals(database_path),
            key=lambda goal: (goal.updated_at, goal.id),
            reverse=True,
        )
    )

    selected_goal: Goal | None = None
    if goal_id is not None:
        selected_goal = get_goal(database_path, goal_id)
        if selected_goal is None:
            raise ValueError(f"goal não encontrado: {goal_id}")
    elif len(open_goals) == 1:
        selected_goal = open_goals[0]

    latest_experience = get_latest_experience(database_path)
    selected = (
        _goal_resume_state(
            database_path,
            goal=selected_goal,
            current_world_revision=world_revision,
            memory_limit=memory_limit,
        )
        if selected_goal is not None
        else None
    )

    memories: tuple[Memory, ...] = ()
    if selected is not None:
        memories = selected.memories
    elif latest_experience is not None:
        memories = retrieve_memories(
            database_path,
            source_experience_id=latest_experience.id,
            limit=memory_limit,
        )

    return ResumeOverview(
        current_world_revision=world_revision,
        open_goals=open_goals,
        selected=selected,
        latest_experience=latest_experience,
        memories=memories,
    )


def _goal_resume_state(
    database_path: Path,
    *,
    goal: Goal,
    current_world_revision: int,
    memory_limit: int,
) -> GoalResumeState:
    active_plan = get_active_plan(database_path, goal.id)
    plans = list_plans_for_goal(database_path, goal.id)
    plan = active_plan if active_plan is not None else (plans[-1] if plans else None)

    readiness: PlanReadiness | None = None
    if active_plan is not None:
        readiness = evaluate_active_plan(database_path, goal_id=goal.id)

    resumed_actions: list[ResumedAction] = []
    for known_plan in plans:
        for action in list_actions_for_plan(database_path, known_plan.id):
            verifications = list_verification_results(
                database_path,
                subject_type="ACTION",
                subject_id=action.id,
            )
            latest = verifications[-1] if verifications else None
            resumed_actions.append(
                ResumedAction(
                    action=action,
                    latest_verification_id=latest.id if latest is not None else None,
                    latest_verification_status=(latest.status if latest is not None else None),
                )
            )

    latest_experience = get_latest_experience(database_path, goal_id=goal.id)
    memories: list[Memory] = []
    seen_memory_ids: set[str] = set()

    if latest_experience is not None:
        for memory in retrieve_memories(
            database_path,
            source_experience_id=latest_experience.id,
            limit=memory_limit,
        ):
            memories.append(memory)
            seen_memory_ids.add(memory.id)

    remaining = memory_limit - len(memories)
    if remaining > 0:
        for memory in retrieve_memories(
            database_path,
            query=goal.title,
            limit=remaining,
        ):
            if memory.id in seen_memory_ids:
                continue
            memories.append(memory)
            seen_memory_ids.add(memory.id)
            if len(memories) == memory_limit:
                break

    return GoalResumeState(
        goal=goal,
        plan=plan,
        readiness=readiness,
        actions=tuple(resumed_actions),
        current_world_revision=current_world_revision,
        world_changed_since_plan=(
            current_world_revision != plan.based_on_world_revision if plan is not None else None
        ),
        latest_experience=latest_experience,
        memories=tuple(memories),
    )
