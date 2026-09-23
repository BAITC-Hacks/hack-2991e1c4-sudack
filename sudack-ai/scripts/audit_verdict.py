"""Inspect one starter-kit employee with at most one OpenAI request.

Usage: python scripts/audit_verdict.py --live E0002 [--provider openai|nvidia]
This script deliberately disables SDK retries and failover: exactly one provider, one request.
"""

import asyncio
import json
import sys
from pathlib import Path

from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.config import Settings  # noqa: E402
from app.explain import SDKExplanationStrategy  # noqa: E402
from app.models import RecommendRequest  # noqa: E402
from app.recommendation import RecommendationService  # noqa: E402
from app.scoring import ScoringService  # noqa: E402


def load_payload(employee_id: str) -> dict:
    import csv
    from collections import defaultdict

    root = Path(__file__).resolve().parents[1] / "docs" / "data"
    skills = json.loads((root / "skills.json").read_text(encoding="utf-8"))
    employees = json.loads((root / "employees.json").read_text(encoding="utf-8"))["employees"]
    events = json.loads((root / "events.json").read_text(encoding="utf-8"))["events"]
    employee = next(item for item in employees if item["employee_id"] == employee_id)
    grades = ["Junior", "Middle", "Senior", "Lead"]
    grade = grades[min(grades.index(employee["grade"]) + 1, len(grades) - 1)]
    profile = next(item for item in skills["role_profiles"]
                   if item["role"] == employee["role"] and item["grade"] == grade)
    history = defaultdict(list)
    with (root / "activity_history.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            history[row["employee_id"]].append({
                "event_id": row["event_id"], "status": row["status"], "date": row["date"]
            })
    return {
        "employee": employee,
        "next_grade": grade,
        "next_grade_requirements": profile["required_skills"],
        "critical_skills": profile["critical_skills"],
        "skills_meta": {item["skill_id"]: {"name": item["name"], "category": item["category"]}
                        for item in skills["skills"]},
        "history": history[employee_id],
        "events": events,
        "lang": employee["preferred_language"],
    }


async def audit(employee_id: str, provider: str = "openai") -> None:
    settings = Settings()
    if provider == "openai":
        api_key, base_url, model, structured = (
            settings.openai_api_key, settings.openai_base_url, settings.llm_model or settings.openai_model, True,
        )
    elif provider == "nvidia":
        api_key, base_url, model, structured = (
            settings.nvidia_api_key, settings.nvidia_base_url, settings.nvidia_model, False,
        )
    else:
        raise SystemExit(f"Unknown provider {provider!r}")
    if not api_key.strip():
        raise SystemExit(f"{provider.upper()}_API_KEY is not configured")
    request = RecommendRequest.model_validate(load_payload(employee_id))
    candidates = ScoringService().rank(request)[:5]
    # NOTE: the service itself prefers gap-closing candidates; this list is the raw top five.

    class RecordingStrategy:
        proposal = None
        error = None

        def __init__(self, delegate: SDKExplanationStrategy) -> None:
            self.delegate = delegate

        async def select(self, request, candidates):
            try:
                self.proposal = await self.delegate.select(request, candidates)
                return self.proposal
            except BaseException as exc:
                self.error = type(exc).__name__
                raise

    async with AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=settings.llm_timeout, max_retries=0) as client:
        strategy = RecordingStrategy(SDKExplanationStrategy(client, model, structured=structured, name=provider))
        service = RecommendationService(explainer=strategy, timeout=settings.llm_timeout)
        verdict = await service.recommend(request)

    print(json.dumps({
        "provider": provider,
        "model": model,
        "employee_id": employee_id,
        "language": request.lang,
        "grade": request.employee.grade,
        "next_grade": request.next_grade,
        "history_statuses": {status: sum(row.status == status for row in request.history)
                             for status in sorted({row.status for row in request.history})},
        "top_candidates": [{
            "event_id": item.event.event_id, "score": round(item.score, 4),
            "primary_skill": item.primary_skill,
            "gap": next(factor for factor in item.factors if factor["type"] == "skill_gap"),
            "history": next(factor for factor in item.factors if factor["type"] == "history"),
            "gain": next(factor for factor in item.factors if factor["type"] == "effective_gain"),
        } for item in candidates],
        "llm_proposal": strategy.proposal,
        "llm_error_type": strategy.error,
        "verdict": {
            "source": verdict.source,
            "readiness": verdict.readiness.model_dump(),
            "recommendations": [
                {"event_id": item.event_id, "score": item.score,
                 "reason_source": item.reason_source, "reason": item.reason}
                for item in verdict.recommendations
            ],
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2 or args[0] != "--live":
        raise SystemExit("Usage: python scripts/audit_verdict.py --live EMPLOYEE_ID [--provider openai|nvidia]")
    chosen = args[args.index("--provider") + 1] if "--provider" in args else "openai"
    asyncio.run(audit(args[1], chosen))
