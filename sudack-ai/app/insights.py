"""Explainable insights built on the deterministic scorer.

1. why_not        - why the naive "lowest skill" pick lost (counterfactual for the jury trap)
2. simulate       - greedy roadmap of activities to the next grade with dates and hours
3. dropout_risk   - who is falling out of development, with reasons and a working format
4. event_impact   - what a draft HR event would do across the workforce
No provider calls, no persistent state.
"""

from collections import Counter
from datetime import date, timedelta

from app.models import Event, HistoryEntry, RecommendRequest
from app.scoring import (
    MISSED_STATUSES, Candidate, ScoringService, apply_progress, parse_date, readiness, skill_gaps,
)

RECENT_WINDOW_DAYS = 180
STALE_IN_PROGRESS_DAYS = 90


def _name(request: RecommendRequest, skill: str) -> str:
    return request.skills_meta[skill].name if skill in request.skills_meta else skill


def _as_of(request: RecommendRequest) -> date | None:
    explicit = parse_date(request.as_of)
    if explicit:
        return explicit
    dates = [d for d in (parse_date(entry.date) for entry in request.history) if d]
    if dates:
        return max(dates)
    sessions = [d for event in request.events for d in (parse_date(s) for s in event.upcoming_sessions or []) if d]
    return min(sessions) if sessions else None


# --------------------------------------------------------------------------- 1. why not

_WHY_NOT = {
    "ru": {
        "lead": "{name}: {current} при требуемых {required} для {grade}{largest}.",
        "largest": ", самый большой разрыв",
        "equal": "вклад в переход и история участия одинаковы, события равнозначны",
        "engagement": "история участия по этим навыкам слабее ({eng:.2f} против {top_eng:.2f})",
        "no_event": "нет доступных активностей, развивающих этот навык (аудитория, предусловия или потолок уровня).",
        "but": "Но:",
        "missed": "вы пропустили {missed} из {total} активностей по этому навыку",
        "critical": "{top} критичен для {grade}, а {name} нет",
        "outside": "навык вне требований {grade}",
        "smaller": "вклад в переход меньше ({gap:.2f} против {top_gap:.2f})",
    },
    "kk": {
        "lead": "{name}: {grade} үшін {required} қажет, қазір {current}{largest}.",
        "largest": ", ең үлкен алшақтық",
        "equal": "үлесі мен қатысу тарихы бірдей, шаралар тең",
        "engagement": "осы дағдылар бойынша қатысу тарихы әлсіз ({eng:.2f} және {top_eng:.2f})",
        "no_event": "бұл дағдыны дамытатын қолжетімді шара жоқ (аудитория, алғышарттар немесе деңгей шегі).",
        "but": "Бірақ:",
        "missed": "осы дағды бойынша {total} шараның {missed} өткізіп алдыңыз",
        "critical": "{top} {grade} үшін шешуші, ал {name} емес",
        "outside": "дағды {grade} талаптарына кірмейді",
        "smaller": "грейдке өтуге үлесі кішірек ({gap:.2f} және {top_gap:.2f})",
    },
    "en": {
        "lead": "{name}: {current} against {required} needed for {grade}{largest}.",
        "largest": ", the largest gap",
        "equal": "same contribution and history, the events are equivalent",
        "engagement": "weaker participation history on these skills ({eng:.2f} vs {top_eng:.2f})",
        "no_event": "no available activity develops this skill (audience, prerequisites or level ceiling).",
        "but": "But:",
        "missed": "you missed {missed} of {total} activities on this skill",
        "critical": "{top} is critical for {grade} and {name} is not",
        "outside": "the skill is outside the {grade} requirements",
        "smaller": "it contributes less to the promotion ({gap:.2f} vs {top_gap:.2f})",
    },
}


def _rejected_item(
    request: RecommendRequest, candidate: Candidate, skill: str, skills: dict[str, int], top: Candidate | None,
    largest_gap: bool = False,
) -> dict:
    text = _WHY_NOT[request.lang]
    required = request.next_grade_requirements.get(skill)
    current = skills.get(skill, 0)
    history = next(factor for factor in candidate.factors if factor["type"] == "history")
    clauses = []
    if required is None:
        clauses.append(text["outside"].format(grade=request.next_grade))
    if history["missed"]:
        clauses.append(text["missed"].format(missed=history["missed"], total=history["total"]))
    if top is not None:
        top_critical = top.primary_skill in request.critical_skills
        if top_critical and skill not in request.critical_skills:
            clauses.append(text["critical"].format(
                top=_name(request, top.primary_skill), grade=request.next_grade, name=_name(request, skill),
            ))
        if not clauses:
            if abs(candidate.gap_closed - top.gap_closed) < 1e-9 and abs(candidate.engagement - top.engagement) < 1e-9:
                clauses.append(text["equal"])
            elif abs(candidate.gap_closed - top.gap_closed) < 1e-9:
                clauses.append(text["engagement"].format(eng=candidate.engagement, top_eng=top.engagement))
            else:
                clauses.append(text["smaller"].format(gap=candidate.gap_closed, top_gap=top.gap_closed))
    lead = text["lead"].format(
        name=_name(request, skill), current=current, required=required, grade=request.next_grade,
        largest=text["largest"] if largest_gap else "",
    ) if required is not None else f"{_name(request, skill)}: {current}."
    reason = f"{lead} {text['but']} {'; '.join(clauses)}." if clauses else lead
    return {
        "event_id": candidate.event.event_id, "title": candidate.event.title, "skill": skill,
        "current": current, "required": required, "score": round(candidate.score, 4), "reason": reason,
    }


def why_not(
    request: RecommendRequest, ranked: list[Candidate], selected: list[Candidate], skills: dict[str, int],
) -> list[dict]:
    """Why the top recommendation is first: up to two alternatives a naive rule would pick
    (the largest-gap skill, then the next best by score) and what they lost on. An alternative
    may still appear lower in the recommendations; `recommended_position` says where."""
    gaps = {s: g for s, g in skill_gaps(skills, request.next_grade_requirements).items() if g > 0}
    if not gaps or not selected:
        return []
    top = selected[0]
    selected_ids = {top.event.event_id}
    selected_skills = set(top.gains)
    positions = {c.event.event_id: index + 1 for index, c in enumerate(selected)}
    text = _WHY_NOT[request.lang]
    out: list[dict] = []

    lowest = min(gaps, key=lambda s: (-gaps[s], skills.get(s, 0), s))
    if lowest not in selected_skills:
        alternatives = [c for c in ranked if lowest in c.gains and c.event.event_id not in selected_ids]
        if alternatives:
            out.append(_rejected_item(request, alternatives[0], lowest, skills, top, largest_gap=True))
        else:
            out.append({
                "event_id": None, "title": None, "skill": lowest, "current": skills.get(lowest, 0),
                "required": request.next_grade_requirements[lowest], "score": None,
                "reason": text["lead"].format(
                    name=_name(request, lowest), current=skills.get(lowest, 0),
                    required=request.next_grade_requirements[lowest], grade=request.next_grade,
                    largest=text["largest"],
                ) + " " + text["but"] + " " + text["no_event"],
            })

    for candidate in ranked:
        if len(out) >= 2:
            break
        if candidate.event.event_id in selected_ids or any(item["event_id"] == candidate.event.event_id for item in out):
            continue
        out.append(_rejected_item(request, candidate, candidate.primary_skill, skills, top))
        break
    for item in out:
        item["recommended_position"] = positions.get(item["event_id"])
    return out


# --------------------------------------------------------------------------- 2. simulator

def simulate(request: RecommendRequest, max_steps: int = 8) -> dict:
    """Greedy roadmap: at each step take the eligible event that closes the most weighted gap,
    apply its gains, and schedule it on the first free session after its prerequisites are met."""
    scoring = ScoringService()
    skills, _ = apply_progress(request)
    initial = dict(skills)
    requirements, critical = request.next_grade_requirements, request.critical_skills
    as_of = _as_of(request)
    history = list(request.history)
    completed_ids = {entry.event_id for entry in history if entry.status == "completed"}
    used_sessions: dict[str, set[date]] = {}
    skill_ready_on: dict[str, date | None] = {}  # when a planned step raised a skill
    steps: list[dict] = []
    path = [readiness(skills, requirements, critical)]
    total_hours = 0.0
    hit_limit = False

    while True:
        if not any(gap > 0 for gap in skill_gaps(skills, requirements).values()):
            break
        planned = request.model_copy(update={"history": history})
        candidates = [c for c in scoring.rank(planned, skills) if c.closes_gap]
        candidates.sort(key=lambda c: (-c.gap_closed, -c.engagement, c.event.event_id))
        chosen = None
        for candidate in candidates:
            when = _schedule(candidate.event, as_of, used_sessions, skill_ready_on, initial)
            if when is not False:
                chosen = (candidate, when)
                break
        if chosen is None:
            break
        if len(steps) >= max_steps:
            hit_limit = True
            break
        candidate, when = chosen
        changes = []
        for skill, (current, new) in candidate.gains.items():
            skills[skill] = new
            skill_ready_on[skill] = when
            changes.append({"skill": skill, "name": _name(request, skill), "from": current, "to": new,
                            "required": requirements.get(skill)})
        history.append(HistoryEntry(event_id=candidate.event.event_id, status="completed",
                                    date=when.isoformat() if when else None))
        completed_ids.add(candidate.event.event_id)
        hours = candidate.event.duration_hours or 0.0
        total_hours += hours
        path.append(readiness(skills, requirements, critical))
        steps.append({
            "event_id": candidate.event.event_id, "title": candidate.event.title,
            "type": candidate.event.type, "format": candidate.event.format,
            "date": when.isoformat() if when else None, "duration_hours": hours,
            "skill_changes": changes, "readiness_after": path[-1],
        })

    remaining = {s: g for s, g in skill_gaps(skills, requirements).items() if g > 0}
    total_levels = sum(skill_gaps(initial, requirements).values())
    closed_levels = total_levels - sum(remaining.values())
    dates = [parse_date(step["date"]) for step in steps if step["date"]]
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "next_grade": request.next_grade,
        "reachable": not remaining,
        "steps": steps,
        "total_hours": total_hours,
        "estimated_completion": max(dates).isoformat() if dates else None,
        "readiness_path": path,
        "coverage": {
            "gap_levels_total": total_levels,
            "gap_levels_closed": closed_levels,
            "ratio": round(closed_levels / total_levels, 3) if total_levels else 1.0,
        },
        "remaining_gaps": remaining,
        "blocked": [
            {"skill": skill, "name": _name(request, skill), "current": skills.get(skill, 0),
             "required": requirements[skill],
             "reason": _block_reason(request, skill, skills, completed_ids, hit_limit)}
            for skill in remaining
        ],
    }


def _schedule(
    event: Event, as_of: date | None, used: dict[str, set[date]],
    ready_on: dict[str, date | None], initial: dict[str, int],
) -> date | None | bool:
    """Return the session date for this step, None for undated self-paced work,
    or False when no free session exists after the steps that satisfy its prerequisites."""
    earliest, strict = as_of, False
    for skill, level in event.prerequisites.items():
        if initial.get(skill, 0) >= level:
            continue  # was already met before the roadmap; no ordering constraint
        when = ready_on.get(skill)
        if when and (earliest is None or when >= earliest):
            earliest, strict = when, True  # must come after the step that raised the prerequisite
    sessions = sorted(d for d in (parse_date(s) for s in event.upcoming_sessions or []) if d)
    if event.format == "self_paced" or not sessions:
        return earliest + timedelta(days=1) if strict and earliest else earliest
    taken = used.setdefault(event.event_id, set())
    for session in sessions:
        if session in taken:
            continue
        if earliest is not None and (session < earliest or (strict and session == earliest)):
            continue
        taken.add(session)
        return session
    return False


def _block_reason(
    request: RecommendRequest, skill: str, skills: dict[str, int], completed_ids: set[str], hit_limit: bool,
) -> str:
    """Why the roadmap cannot raise this skill further, in the order HR can act on it."""
    developing = [e for e in request.events if skill in e.skills and not e.mandatory]
    if not developing:
        return "no_event_for_skill"
    employee = request.employee
    in_audience = [
        e for e in developing
        if (not e.audience.roles or employee.role in e.audience.roles)
        and (not e.audience.grades or employee.grade in e.audience.grades)
    ]
    if not in_audience:
        return "audience"
    raising = [e for e in in_audience if e.skills[skill].max_level > skills.get(skill, 0)]
    if not raising:
        return "ceiling"
    if all(any(skills.get(s, 0) < level for s, level in e.prerequisites.items()) for e in raising):
        return "prerequisites"
    if all(e.event_id in completed_ids and not e.recurring for e in raising):
        return "already_completed"
    if hit_limit:
        return "step_limit"
    return "unscheduled"


# --------------------------------------------------------------------------- 3. dropout risk


def dropout_risk(request: RecommendRequest) -> dict:
    events_by_id = {event.event_id: event for event in request.events}
    as_of = _as_of(request)
    history = request.history
    completed = [h for h in history if h.status == "completed"]
    missed = [h for h in history if h.status in MISSED_STATUSES]
    decided = len(completed) + len(missed)
    if not history:
        return {"score": 0.0, "level": "low", "reasons": [{"code": "no_history"}], "suggested_format": None}

    def recent(entry: HistoryEntry) -> bool:
        when = parse_date(entry.date)
        return bool(as_of and when and (as_of - when).days <= RECENT_WINDOW_DAYS)

    miss_rate = len(missed) / decided if decided else 0.0
    recent_missed = sum(recent(h) for h in missed)
    last_completed = max((parse_date(h.date) for h in completed if parse_date(h.date)), default=None)
    days_since = (as_of - last_completed).days if as_of and last_completed else None
    inactive = decided > 0 and (days_since is None or days_since > RECENT_WINDOW_DAYS)
    stale = sum(
        1 for h in history
        if h.status == "in_progress" and as_of and parse_date(h.date)
        and (as_of - parse_date(h.date)).days > STALE_IN_PROGRESS_DAYS
    )
    declined = sum(h.status == "declined" for h in history)

    score = 0.45 * miss_rate + 0.25 * min(recent_missed / 3, 1.0) + 0.2 * inactive + 0.1 * min(stale, 1)
    level = "high" if score >= 0.55 else "medium" if score >= 0.3 else "low"
    reasons = []
    if decided >= 2 and miss_rate >= 0.5:
        reasons.append({"code": "high_miss_rate", "missed": len(missed), "decided": decided})
    if recent_missed >= 2:
        reasons.append({"code": "recent_misses", "count": recent_missed, "window_days": RECENT_WINDOW_DAYS})
    if inactive:
        reasons.append({"code": "inactive", "days_since_completion": days_since})
    if stale:
        reasons.append({"code": "stale_in_progress", "count": stale})
    if declined >= 2:
        reasons.append({"code": "declined_assignments", "count": declined})

    by_format: dict[str, list[int]] = {}
    for entry in completed + missed:
        event = events_by_id.get(entry.event_id)
        if event is None or not event.format:
            continue
        bucket = by_format.setdefault(event.format, [0, 0])
        bucket[0] += entry.status == "completed"
        bucket[1] += 1
    suggested = None
    if len(by_format) >= 2:
        best = max(by_format, key=lambda f: (by_format[f][0] / by_format[f][1], by_format[f][1]))
        worst = min(by_format, key=lambda f: by_format[f][0] / by_format[f][1])
        if best != worst and by_format[best][0] / by_format[best][1] >= 0.5 and by_format[worst][0] / by_format[worst][1] < 0.5:
            suggested = best
    return {"score": round(score, 3), "level": level, "reasons": reasons, "suggested_format": suggested}


# --------------------------------------------------------------------------- 4. event impact


def _in_audience(event: Event, request: RecommendRequest, skills: dict[str, int]) -> bool:
    employee = request.employee
    if event.audience.roles and employee.role not in event.audience.roles:
        return False
    if event.audience.grades and employee.grade not in event.audience.grades:
        return False
    return all(skills.get(skill, 0) >= level for skill, level in event.prerequisites.items())


def event_impact(draft: Event, items: list[RecommendRequest]) -> dict:
    scoring = ScoringService()
    audience = 0
    closers: list[str] = []
    expected = 0.0
    levels = 0
    by_skill: Counter = Counter()
    catalog: Counter = Counter()
    titles: dict[str, str] = {}

    for item in items:
        skills, _ = apply_progress(item)
        if _in_audience(draft, item, skills):
            audience += 1
        gaps = skill_gaps(skills, item.next_grade_requirements)
        for candidate in scoring.rank(item, skills):
            titles[candidate.event.event_id] = candidate.event.title
            if candidate.closes_gap:
                catalog[candidate.event.event_id] += 1
        with_draft = item.model_copy(update={"events": [*item.events, draft]})
        candidate = next((c for c in scoring.rank(with_draft, skills) if c.event.event_id == draft.event_id), None)
        if candidate is not None and candidate.closes_gap:
            closers.append(item.employee.employee_id)
            expected += candidate.engagement
            for skill, (current, new) in candidate.gains.items():
                if gaps.get(skill, 0) > 0:
                    levels += min(new - current, gaps[skill])
                    by_skill[skill] += 1

    hours = draft.duration_hours
    return {
        "event_id": draft.event_id,
        "title": draft.title,
        "employees": len(items),
        "audience_count": audience,
        "gap_closing_count": len(closers),
        "gap_closing_employees": closers,
        "expected_completions": round(expected, 2),
        "gap_levels_closed": levels,
        "hours_per_gap_level": round(hours * len(closers) / levels, 2) if hours and levels else None,
        "by_skill": dict(by_skill),
        "catalog_rank": 1 + sum(count > len(closers) for count in catalog.values()),
        "catalog_top": [
            {"event_id": event_id, "title": titles.get(event_id, event_id), "gap_closing_count": count}
            for event_id, count in sorted(catalog.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
        ],
    }
