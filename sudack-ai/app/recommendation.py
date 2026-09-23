"""Application service combining scoring, explanation, validation and caching."""

import asyncio
import re

from app.cache import ResponseCache
from app.explain import ExplanationStrategy, template_explain
from app.insights import dropout_risk, why_not
from app.models import (
    BatchRequest, BatchResponse, BatchResult, BatchTopItem, Calculation,
    Readiness, RecommendRequest, RecommendResponse, Recommendation,
)
from app.scoring import (
    Candidate, ScoringService, apply_progress, participation, readiness, skill_gaps,
)


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

        skills, applied = apply_progress(request)
        ranked = self._scoring.rank(request, skills)
        gap_closing = [candidate for candidate in ranked if candidate.closes_gap]
        others = [candidate for candidate in ranked if not candidate.closes_gap]
        # The LLM chooses among gap-closing events; enrichment events only pad a short list.
        candidates = gap_closing[:5] + others[:max(0, 3 - len(gap_closing))]

        selected: list[tuple[Candidate, str, str]] | None = None
        provider = model = None
        if candidates and self._explainer is not None:
            try:
                proposed = await asyncio.wait_for(
                    self._explainer.select(request, candidates), timeout=self._timeout
                )
                selected = self._validate_selection(proposed, candidates, request)
                if selected is not None:
                    provider = getattr(proposed, "provider", None) or getattr(self._explainer, "name", None)
                    model = getattr(proposed, "model", None) or getattr(self._explainer, "model", None)
            except Exception:
                selected = None

        source = "llm" if selected is not None else "fallback"
        if selected is None:
            fallback_candidates = gap_closing if gap_closing else ranked
            selected = [
                (candidate, template_explain(request, candidate), "template")
                for candidate in fallback_candidates[:3]
            ]

        recommendations = [
            Recommendation(
                event_id=candidate.event.event_id,
                title=candidate.event.title,
                score=round(candidate.score, 4),
                reason=reason,
                reason_source=reason_source,
                factors=candidate.factors,
                calculation=Calculation(
                    gap_closed=round(candidate.gap_closed, 4),
                    engagement=round(candidate.engagement, 4),
                    formula=f"{candidate.gap_closed:.4f} * {candidate.engagement:.4f}^0.7",
                ),
            )
            for candidate, reason, reason_source in selected
        ]

        after_skills = skills.copy()
        if selected:
            for skill, (_, new) in selected[0][0].gains.items():
                after_skills[skill] = new
        requirements, critical = request.next_grade_requirements, request.critical_skills
        result = RecommendResponse(
            recommendations=recommendations,
            readiness=Readiness(
                current=readiness(skills, requirements, critical),
                after_top=readiness(after_skills, requirements, critical),
            ),
            gaps={skill: gap for skill, gap in skill_gaps(skills, requirements).items() if gap > 0},
            applied_progress=applied,
            rejected=why_not(request, ranked, [candidate for candidate, _, _ in selected], skills),
            source=source,
            llm_provider=provider if source == "llm" else None,
            llm_model=model if source == "llm" else None,
        )
        # A template answer produced because the LLM was unavailable must not be
        # pinned until the employee's history changes; only validated LLM output is cached.
        if source == "llm":
            self._cache.set(key, result)
        return result

    def score_batch(self, request: BatchRequest) -> BatchResponse:
        results = []
        for item in request.items:
            skills, _ = apply_progress(item)
            ranked = self._scoring.rank(item, skills)
            gaps = skill_gaps(skills, item.next_grade_requirements)
            results.append(BatchResult(
                employee_id=item.employee.employee_id,
                top=[
                    BatchTopItem(
                        event_id=candidate.event.event_id,
                        score=round(candidate.score, 4),
                        primary_skill=candidate.primary_skill,
                    )
                    for candidate in ranked[:3]
                ],
                readiness=readiness(skills, item.next_grade_requirements, item.critical_skills),
                gaps={skill: gap for skill, gap in gaps.items() if gap > 0},
                participation=participation(item.history),
                risk=dropout_risk(item),
            ))
        return BatchResponse(results=results)

    @staticmethod
    def _validate_selection(
        proposed: list[dict[str, str]], candidates: list[Candidate], request: RecommendRequest
    ) -> list[tuple[Candidate, str, str]] | None:
        """Keep the LLM's choice of events; keep each reason only if it is grounded in the
        candidate's facts and not a copy of another reason, otherwise use the template for
        that event. Returns None (full fallback) when no LLM reason survives or the shape is wrong.
        """
        if not isinstance(proposed, list) or not proposed:
            return None
        by_id = {candidate.event.event_id: candidate for candidate in candidates}
        selected: list[tuple[Candidate, str, str]] = []
        seen_ids: set[str] = set()
        seen_reasons: set[str] = set()
        for item in proposed:
            if not isinstance(item, dict):
                continue
            event_id, reason = item.get("event_id"), item.get("reason")
            if event_id not in by_id or event_id in seen_ids or not isinstance(reason, str) or not reason.strip():
                continue
            candidate = by_id[event_id]
            reason = reason.strip()
            normalized = re.sub(r"\s+", " ", reason.lower())
            grounded = (
                RecommendationService._reason_is_grounded(reason, candidate, request)
                and normalized not in seen_reasons
            )
            seen_ids.add(event_id)
            seen_reasons.add(normalized)
            if grounded:
                selected.append((candidate, reason, "llm"))
            else:
                selected.append((candidate, template_explain(request, candidate), "template"))
            if len(selected) == 3:
                break
        if not any(source == "llm" for _, _, source in selected):
            return None
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
            "ru": r"истор|похож|аналогич|мероприят|активност|заверш|пропуст|участ|раньше|ещё не|еще не",
            "kk": r"тарих|ұқсас|аяқтал|қатыс|өткіз|шара|әлі",
            "en": r"histor|similar|complet|attend|miss|participat|activit|yet",
        }
        if not re.search(history_terms[request.lang], reason, re.IGNORECASE):
            return False

        # The skill levels are the facts the LLM must not blur; history counts are
        # allowed in words ("no similar activities yet"), so they are not required.
        gap = next(factor for factor in candidate.factors if factor["type"] == "skill_gap")
        gain = next(factor for factor in candidate.factors if factor["type"] == "effective_gain")
        numbers = [gap["current"], gap["required"], gain["to"]]
        return all(number is None or re.search(rf"(?<!\d){number}(?!\d)", reason)
                   for number in numbers)
