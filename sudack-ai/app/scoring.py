"""Deterministic, explainable scoring. No provider calls or persistent state."""

from dataclasses import dataclass

from app.models import Event, RecommendRequest


@dataclass(frozen=True)
class Candidate:
    event: Event
    score: float
    gap_closed: float
    engagement: float
    gains: dict[str, tuple[int, int]]
    factors: list[dict]
    primary_skill: str


def skill_gaps(skills: dict[str, int], requirements: dict[str, int]) -> dict[str, int]:
    return {skill: max(0, level - skills.get(skill, 0)) for skill, level in requirements.items()}


def effective_gain(event: Event, skills: dict[str, int]) -> dict[str, tuple[int, int]]:
    gains = {}
    for skill, change in event.skills.items():
        current = skills.get(skill, 0)
        new = min(current + change.gain, change.max_level)
        if new > current:
            gains[skill] = (current, new)
    return gains


def readiness(skills: dict[str, int], requirements: dict[str, int]) -> float:
    total = sum(1.5 * required for required in requirements.values())
    missing = sum(1.5 * gap for gap in skill_gaps(skills, requirements).values())
    return round(1 - missing / total, 2) if total else 1.0


class ScoringService:
    def rank(self, request: RecommendRequest) -> list[Candidate]:
        employee = request.employee
        gaps = skill_gaps(employee.skills, request.next_grade_requirements)
        events_by_id = {event.event_id: event for event in request.events}
        completed = {entry.event_id for entry in request.history if entry.status == "completed"}
        candidates = []

        for event in request.events:
            if event.mandatory or (event.event_id in completed and not event.recurring):
                continue
            if event.audience.roles and employee.role not in event.audience.roles:
                continue
            if event.audience.grades and employee.grade not in event.audience.grades:
                continue
            if any(employee.skills.get(skill, 0) < level for skill, level in event.prerequisites.items()):
                continue
            gains = effective_gain(event, employee.skills)
            if not gains:
                continue

            similar = [
                entry for entry in request.history
                if entry.event_id in events_by_id
                and self._similar(events_by_id[entry.event_id], event)
            ]
            completed_similar = sum(entry.status == "completed" for entry in similar)
            engagement = (completed_similar + 1) / (len(similar) + 2)
            contributions = {
                skill: (1.5 if skill in request.next_grade_requirements else 0.3)
                * min(new - current, gaps.get(skill, 0) or 0.2)
                for skill, (current, new) in gains.items()
            }
            gap_closed = sum(contributions.values())
            score = gap_closed * engagement**0.7
            primary = max(contributions, key=lambda skill: (contributions[skill], skill in request.next_grade_requirements))
            factors = self._factors(request, gains, contributions, primary, similar, completed_similar)
            candidates.append(Candidate(event, score, gap_closed, engagement, gains, factors, primary))

        return self._diversify(candidates)

    @staticmethod
    def _similar(first: Event, second: Event) -> bool:
        return first.type == second.type or bool(first.skills.keys() & second.skills.keys())

    @staticmethod
    def _factors(
        request: RecommendRequest,
        gains: dict[str, tuple[int, int]],
        contributions: dict[str, float],
        primary: str,
        similar: list,
        completed_similar: int,
    ) -> list[dict]:
        missed = sum(entry.status in {"skipped", "no_show", "declined", "dropped"} for entry in similar)
        history = {"type": "history", "text": (
            f"{completed_similar} of {len(similar)} similar activities completed; {missed} missed"
        ), "completed": completed_similar, "total": len(similar), "missed": missed}
        factors = []
        for skill in [primary, *sorted(set(gains) - {primary})]:
            current, new = gains[skill]
            required = request.next_grade_requirements.get(skill)
            name = request.skills_meta.get(skill).name if skill in request.skills_meta else skill
            if required is None:
                relevance = {"type": "grade_requirement", "text": (
                    f"{name} is outside the stated next-grade requirements"
                )}
            else:
                critical = skill in request.critical_skills
                relevance = {"type": "grade_requirement", "text": (
                    f"{name} is {'critical' if critical else 'required'} for {request.next_grade}"
                )}
            factors.extend([
                relevance,
                {"type": "skill_gap", "skill": skill, "current": current, "required": required},
            ])
            if skill == primary:
                factors.append(history)
            factors.append({
                "type": "effective_gain", "skill": skill, "from": current, "to": new,
                "weight": 1.5 if required is not None else 0.3,
                "weighted_gap_closed": round(contributions[skill], 4),
            })
        return factors

    @staticmethod
    def _diversify(candidates: list[Candidate]) -> list[Candidate]:
        remaining = sorted(candidates, key=lambda item: (-item.score, item.event.event_id))
        ranked = []
        while remaining:
            previous_skill = ranked[-1].primary_skill if ranked else None
            best = max(
                remaining,
                key=lambda item: (
                    item.score * (0.8 if item.primary_skill == previous_skill else 1.0),
                    item.score,
                    item.event.event_id,
                ),
            )
            ranked.append(best)
            remaining.remove(best)
        return ranked
