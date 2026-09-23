"""Deterministic, explainable scoring. No provider calls or persistent state."""

from dataclasses import dataclass
from datetime import date

from app.models import Event, HistoryEntry, RecommendRequest

WEIGHT_CRITICAL = 2.5      # gap in a critical skill of the next grade
WEIGHT_REQUIRED = 1.5      # gap in any other required skill of the next grade
WEIGHT_OTHER = 0.3         # growth outside the next-grade requirements
NO_GAP_CREDIT = 0.2        # small credit for growing a skill that already meets the requirement
SAME_TYPE_WEIGHT = 0.3     # history of the same event type but unrelated skills
OLD_HISTORY_WEIGHT = 0.6   # history older than one year before the latest known entry
RECENT_DAYS = 365
MISSED_STATUSES = {"skipped", "no_show", "declined", "dropped", "overdue"}
ACTIVE_STATUSES = {"in_progress", "overdue"}


@dataclass(frozen=True)
class Candidate:
    event: Event
    score: float
    gap_closed: float
    engagement: float
    gains: dict[str, tuple[int, int]]
    factors: list[dict]
    primary_skill: str
    closes_gap: bool


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


def skill_weight(skill: str, requirements: dict[str, int], critical: list[str]) -> float:
    if skill in critical and skill in requirements:
        return WEIGHT_CRITICAL
    if skill in requirements:
        return WEIGHT_REQUIRED
    return WEIGHT_OTHER


def readiness(skills: dict[str, int], requirements: dict[str, int], critical: list[str] = ()) -> float:
    weights = {skill: skill_weight(skill, requirements, list(critical)) for skill in requirements}
    total = sum(weights[skill] * required for skill, required in requirements.items())
    missing = sum(weights[skill] * gap for skill, gap in skill_gaps(skills, requirements).items())
    return round(1 - missing / total, 2) if total else 1.0


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]) if len(value) >= 10 else date.fromisoformat(f"{value}-01")
    except ValueError:
        return None


def apply_progress(request: RecommendRequest) -> tuple[dict[str, int], list[dict]]:
    """Skill levels reflect the last assessment; completions after `last_review_date`
    are applied on top so progress is visible before the next review."""
    skills = dict(request.employee.skills)
    review = parse_date(request.employee.last_review_date)
    if review is None:
        return skills, []
    events_by_id = {event.event_id: event for event in request.events}
    applied = []
    completed = [
        (parse_date(entry.date), entry) for entry in request.history
        if entry.status == "completed" and parse_date(entry.date) is not None
    ]
    for when, entry in sorted(completed, key=lambda pair: pair[0]):
        if when <= review or entry.event_id not in events_by_id:
            continue
        for skill, (current, new) in effective_gain(events_by_id[entry.event_id], skills).items():
            skills[skill] = new
            applied.append({"event_id": entry.event_id, "skill": skill, "from": current, "to": new})
    return skills, applied


def participation(history: list[HistoryEntry]) -> dict:
    """Compact engagement summary for the HR view: who is dropping out of development."""
    dates = [d for d in (parse_date(entry.date) for entry in history) if d]
    return {
        "completed": sum(entry.status == "completed" for entry in history),
        "missed": sum(entry.status in MISSED_STATUSES for entry in history),
        "in_progress": sum(entry.status == "in_progress" for entry in history),
        "total": len(history),
        "last_activity_date": max(dates).isoformat() if dates else None,
    }


class ScoringService:
    def rank(self, request: RecommendRequest, skills: dict[str, int] | None = None) -> list[Candidate]:
        employee = request.employee
        skills = skills if skills is not None else apply_progress(request)[0]
        gaps = skill_gaps(skills, request.next_grade_requirements)
        events_by_id = {event.event_id: event for event in request.events}
        completed = {entry.event_id for entry in request.history if entry.status == "completed"}
        active = {entry.event_id for entry in request.history if entry.status in ACTIVE_STATUSES}
        latest = max((d for d in (parse_date(entry.date) for entry in request.history) if d), default=None)
        candidates = []

        for event in request.events:
            if event.mandatory or event.event_id in active:
                continue
            if event.event_id in completed and not event.recurring:
                continue
            if event.audience.roles and employee.role not in event.audience.roles:
                continue
            if event.audience.grades and employee.grade not in event.audience.grades:
                continue
            if any(skills.get(skill, 0) < level for skill, level in event.prerequisites.items()):
                continue
            # A scheduled (non self-paced) event with no upcoming session cannot be attended.
            if event.format and event.format != "self_paced" and event.upcoming_sessions == []:
                continue
            gains = effective_gain(event, skills)
            if not gains:
                continue

            related, same_type = [], []
            for entry in request.history:
                # An activity still underway is neither a completion nor a miss.
                if entry.status == "in_progress":
                    continue
                past = events_by_id.get(entry.event_id)
                if past is None:
                    continue
                if past.skills.keys() & event.skills.keys():
                    related.append(entry)
                elif past.type == event.type:
                    same_type.append(entry)
            engagement = self._engagement(related, same_type, latest)

            contributions = {
                skill: skill_weight(skill, request.next_grade_requirements, request.critical_skills)
                * min(new - current, gaps.get(skill, 0) or NO_GAP_CREDIT)
                for skill, (current, new) in gains.items()
            }
            gap_closed = sum(contributions.values())
            score = gap_closed * engagement**0.7
            primary = max(contributions, key=lambda skill: (contributions[skill], skill in request.critical_skills))
            closes_gap = any(gaps.get(skill, 0) > 0 for skill in gains)
            factors = self._factors(request, gains, contributions, primary, related, same_type)
            candidates.append(Candidate(event, score, gap_closed, engagement, gains, factors, primary, closes_gap))

        return self._diversify(candidates)

    @staticmethod
    def _recency(entry: HistoryEntry, latest: date | None) -> float:
        when = parse_date(entry.date)
        if latest is None or when is None:
            return 1.0
        return 1.0 if (latest - when).days <= RECENT_DAYS else OLD_HISTORY_WEIGHT

    @classmethod
    def _engagement(cls, related: list[HistoryEntry], same_type: list[HistoryEntry], latest: date | None) -> float:
        """Laplace-smoothed completion rate: skill-related history counts fully,
        same-type history weakly, entries older than a year at a discount."""
        weight = 0.0
        completed = 0.0
        for entries, tier in ((related, 1.0), (same_type, SAME_TYPE_WEIGHT)):
            for entry in entries:
                w = tier * cls._recency(entry, latest)
                weight += w
                if entry.status == "completed":
                    completed += w
        return (completed + 1) / (weight + 2)

    @staticmethod
    def _factors(
        request: RecommendRequest,
        gains: dict[str, tuple[int, int]],
        contributions: dict[str, float],
        primary: str,
        related: list[HistoryEntry],
        same_type: list[HistoryEntry],
    ) -> list[dict]:
        completed = sum(entry.status == "completed" for entry in related)
        missed = sum(entry.status in MISSED_STATUSES for entry in related)
        type_completed = sum(entry.status == "completed" for entry in same_type)
        type_missed = sum(entry.status in MISSED_STATUSES for entry in same_type)
        text = f"{completed} of {len(related)} activities on the same skills completed; {missed} missed"
        if same_type:
            text += (f"; {type_completed} of {len(same_type)} same-type activities on other skills "
                     f"completed; {type_missed} missed")
        history = {
            "type": "history", "text": text,
            "completed": completed, "total": len(related), "missed": missed,
            "same_type_completed": type_completed, "same_type_total": len(same_type),
            "same_type_missed": type_missed,
        }
        factors = []
        for skill in [primary, *sorted(set(gains) - {primary})]:
            current, new = gains[skill]
            required = request.next_grade_requirements.get(skill)
            name = request.skills_meta.get(skill).name if skill in request.skills_meta else skill
            critical = skill in request.critical_skills and required is not None
            if required is None:
                relevance = {"type": "grade_requirement", "text": (
                    f"{name} is outside the stated next-grade requirements"
                ), "critical": False}
            else:
                relevance = {"type": "grade_requirement", "text": (
                    f"{name} is {'critical' if critical else 'required'} for {request.next_grade}"
                ), "critical": critical}
            factors.extend([
                relevance,
                {"type": "skill_gap", "skill": skill, "name": name, "current": current, "required": required},
            ])
            if skill == primary:
                factors.append(history)
            factors.append({
                "type": "effective_gain", "skill": skill, "from": current, "to": new,
                "weight": skill_weight(skill, request.next_grade_requirements, request.critical_skills),
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
