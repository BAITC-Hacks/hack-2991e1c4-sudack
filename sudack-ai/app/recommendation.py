"""Application service combining scoring, explanation, validation and caching."""

import asyncio
import re

from app.cache import ResponseCache
from app.explain import ExplanationStrategy, template_explain
from app.models import (
    BatchRequest, BatchResponse, BatchResult, BatchTopItem, Calculation,
    Readiness, RecommendRequest, RecommendResponse, Recommendation,
)
from app.scoring import Candidate, ScoringService, readiness


class RecommendationService:
    def __init__(
        self,
        scoring: ScoringService | None = None,
        explainer: ExplanationStrategy | None = None,
        cache: ResponseCache | None = None,
        timeout: float = 8.0,
    ) -> None:
        self._scoring = scoring or ScoringService()
        self._explainer = explainer
        self._cache = cache or ResponseCache()
        self._timeout = timeout

    async def recommend(self, request: RecommendRequest) -> RecommendResponse:
        key = self._cache.key(request)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        ranked = self._scoring.rank(request)
        candidates = ranked[:5]
        selected = None
        if candidates and self._explainer is not None:
            try:
                proposed = await asyncio.wait_for(
                    self._explainer.select(request, candidates), timeout=self._timeout
                )
                selected = self._validate_selection(proposed, candidates, request)
            except Exception:
                selected = None

        source = "llm" if selected is not None else "fallback"
        if selected is None:
            gap_closing = [
                candidate for candidate in ranked
                if any(
                    skill in request.next_grade_requirements
                    and current < request.next_grade_requirements[skill]
                    and new > current
                    for skill, (current, new) in candidate.gains.items()
                )
            ]
            fallback_candidates = gap_closing if gap_closing else ranked
            selected = [
                (candidate, template_explain(request, candidate))
                for candidate in fallback_candidates[:3]
            ]

        recommendations = [
            Recommendation(
                event_id=candidate.event.event_id,
                title=candidate.event.title,
                score=round(candidate.score, 4),
                reason=reason,
                factors=candidate.factors,
                calculation=Calculation(
                    gap_closed=round(candidate.gap_closed, 4),
                    engagement=round(candidate.engagement, 4),
                    formula=f"{candidate.gap_closed:.4f} * {candidate.engagement:.4f}^0.7",
                ),
            )
            for candidate, reason in selected
        ]

        after_skills = request.employee.skills.copy()
        if selected:
            for skill, (_, new) in selected[0][0].gains.items():
                after_skills[skill] = new
        result = RecommendResponse(
            recommendations=recommendations,
            readiness=Readiness(
                current=readiness(request.employee.skills, request.next_grade_requirements),
                after_top=readiness(after_skills, request.next_grade_requirements),
            ),
            source=source,
        )
        self._cache.set(key, result)
        return result

    def score_batch(self, request: BatchRequest) -> BatchResponse:
        results = []
        for item in request.items:
            ranked = self._scoring.rank(item)
            results.append(BatchResult(
                employee_id=item.employee.employee_id,
                top=[BatchTopItem(event_id=candidate.event.event_id, score=round(candidate.score, 4))
                     for candidate in ranked[:3]],
                readiness=readiness(item.employee.skills, item.next_grade_requirements),
            ))
        return BatchResponse(results=results)

    @staticmethod
    def _validate_selection(
        proposed: list[dict[str, str]], candidates: list[Candidate], request: RecommendRequest
    ) -> list[tuple[Candidate, str]] | None:
        if not isinstance(proposed, list) or not 1 <= len(proposed) <= 3:
            return None
        by_id = {candidate.event.event_id: candidate for candidate in candidates}
        selected = []
        seen = set()
        for item in proposed:
            if not isinstance(item, dict):
                return None
            event_id, reason = item.get("event_id"), item.get("reason")
            if event_id not in by_id or event_id in seen or not isinstance(reason, str) or not reason.strip():
                return None
            if not RecommendationService._reason_is_grounded(reason, by_id[event_id], request):
                return None
            seen.add(event_id)
            selected.append((by_id[event_id], reason.strip()))
        return selected

    @staticmethod
    def _reason_is_grounded(reason: str, candidate: Candidate, request: RecommendRequest) -> bool:
        if request.lang == "kk" and not re.search(r"[ӘәҒғҚқҢңӨөҰұҮүҺһІі]", reason):
            return False
        if request.lang == "ru" and not re.search(r"[А-Яа-яЁё]", reason):
            return False
        if request.lang == "en" and (not re.search(r"[A-Za-z]", reason)
                                     or re.search(r"[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]", reason)):
            return False

        history_terms = {
            "ru": r"истор|похож|аналогич|мероприят|активност|заверш|пропуст|участ",
            "kk": r"тарих|ұқсас|аяқтал|қатыс|өткіз|шара",
            "en": r"histor|similar|complet|attend|miss|participat|activit",
        }
        if not re.search(history_terms[request.lang], reason, re.IGNORECASE):
            return False

        gap = next(factor for factor in candidate.factors if factor["type"] == "skill_gap")
        history = next(factor for factor in candidate.factors if factor["type"] == "history")
        gain = next(factor for factor in candidate.factors if factor["type"] == "effective_gain")
        numbers = [gap["current"], gap["required"], gain["to"],
                   history["completed"], history["total"]]
        return all(number is None or re.search(rf"(?<!\d){number}(?!\d)", reason)
                   for number in numbers)
