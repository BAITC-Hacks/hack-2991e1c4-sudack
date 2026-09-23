import asyncio
from copy import deepcopy
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import create_app
from app.explain import SDKExplanationStrategy
from app.models import RecommendRequest
from app.recommendation import RecommendationService
from app.scoring import ScoringService


def payload() -> dict:
    return {
        "employee": {"employee_id": "E1", "role": "Backend Engineer", "grade": "Middle",
                     "skills": {"SK_SYSTEM_DESIGN": 2, "SK_PUBLIC_SPEAKING": 1}},
        "next_grade": "Senior",
        "next_grade_requirements": {"SK_SYSTEM_DESIGN": 4},
        "skills_meta": {"SK_SYSTEM_DESIGN": {"name": "System Design"},
                        "SK_PUBLIC_SPEAKING": {"name": "Public Speaking"}},
        "history": [],
        "events": [
            {"event_id": "EV_DESIGN", "title": "Design workshop", "type": "workshop",
             "audience": {"roles": ["Backend Engineer"], "grades": ["Middle"]},
             "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}},
            {"event_id": "EV_SPEAK", "title": "Public speaking", "type": "workshop",
             "audience": {"roles": ["Backend Engineer"], "grades": ["Middle"]},
             "skills": {"SK_PUBLIC_SPEAKING": {"gain": 1, "max_level": 5}}},
        ],
        "lang": "ru",
    }


def recommend(data: dict) -> dict:
    return asyncio.run(RecommendationService().recommend(RecommendRequest.model_validate(data))).model_dump(by_alias=True)


def test_trap_noncritical_low_skill_with_skipped_history() -> None:
    data = payload()
    data["history"] = [{"event_id": "EV_SPEAK", "status": "skipped"} for _ in range(3)]
    result = recommend(data)
    assert result["recommendations"][0]["event_id"] == "EV_DESIGN"
    assert result["source"] == "fallback"
    assert all(len(item["factors"]) >= 3 for item in result["recommendations"])


def test_trap_skill_at_ceiling_is_not_recommended() -> None:
    data = payload()
    data["employee"]["skills"]["SK_SYSTEM_DESIGN"] = 3
    data["events"][0]["skills"]["SK_SYSTEM_DESIGN"]["max_level"] = 3
    result = recommend(data)
    assert all(item["event_id"] != "EV_DESIGN" for item in result["recommendations"])


def test_trap_no_history_uses_equal_engagement() -> None:
    result = recommend(payload())
    assert result["recommendations"][0]["event_id"] == "EV_DESIGN"
    assert all(item["calculation"]["engagement"] == 0.5 for item in result["recommendations"])
    assert result["readiness"]["after_top"] > result["readiness"]["current"]


def test_real_dataset_event_shape_and_eligibility() -> None:
    data = payload()
    data["events"] = [
        {"event_id": "EV_BAD", "title": "Mandatory", "type": "course", "mandatory": True,
         "target_roles": ["Backend Engineer"], "target_grades": ["Middle"],
         "develops_skills": [{"skill_id": "SK_SYSTEM_DESIGN", "gain": 1, "max_level": 4}]},
        {"event_id": "EV_PREREQ", "title": "Advanced", "type": "course",
         "target_roles": ["Backend Engineer"], "target_grades": ["Middle"],
         "prerequisites": {"SK_SYSTEM_DESIGN": 3},
         "develops_skills": [{"skill_id": "SK_SYSTEM_DESIGN", "gain": 1, "max_level": 4}]},
        {"event_id": "EV_GOOD", "title": "Fundamentals", "type": "course",
         "target_roles": ["Backend Engineer"], "target_grades": ["Middle"],
         "develops_skills": [{"skill_id": "SK_SYSTEM_DESIGN", "gain": 1, "max_level": 4}]},
    ]
    result = recommend(data)
    assert [item["event_id"] for item in result["recommendations"]] == ["EV_GOOD"]


def test_completed_event_is_excluded() -> None:
    data = payload()
    data["history"] = [{"event_id": "EV_DESIGN", "status": "completed"}]
    result = recommend(data)
    assert all(item["event_id"] != "EV_DESIGN" for item in result["recommendations"])


def test_dataset_recurring_club_can_be_recommended_again() -> None:
    data = payload()
    data["events"] = [{
        "event_id": "EV_036", "title": "Public Speaking Club", "type": "meetup",
        "target_roles": ["Backend Engineer"], "target_grades": ["Middle"],
        "develops_skills": [{"skill_id": "SK_PUBLIC_SPEAKING", "gain": 1, "max_level": 4}],
    }]
    data["history"] = [{"event_id": "EV_036", "status": "completed"}]
    result = recommend(data)
    assert result["recommendations"][0]["event_id"] == "EV_036"


def test_batch_endpoint_never_calls_llm() -> None:
    class FailingExplainer:
        async def select(self, *_args, **_kwargs):
            raise AssertionError("batch called LLM")

    service = RecommendationService(explainer=FailingExplainer())
    with TestClient(create_app(recommendation_service=service)) as client:
        response = client.post("/score/batch", json={"items": [payload(), payload()]})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 2
    assert response.json()["results"][0]["employee_id"] == "E1"
    assert response.json()["results"][0]["top"][0]["event_id"] == "EV_DESIGN"


def test_recommend_endpoint_falls_back_on_invalid_llm_selection() -> None:
    class BadExplainer:
        async def select(self, *_args, **_kwargs):
            return [{"event_id": "NOT_A_CANDIDATE", "reason": "invented"}]

    service = RecommendationService(explainer=BadExplainer())
    with TestClient(create_app(recommendation_service=service)) as client:
        response = client.post("/recommend", json=payload())
    assert response.status_code == 200
    assert response.json()["source"] == "fallback"
    assert response.json()["recommendations"][0]["event_id"] == "EV_DESIGN"


def test_recommend_uses_valid_llm_selection_and_cache_key_changes_with_history() -> None:
    class GoodExplainer:
        calls = 0

        async def select(self, *_args, **_kwargs):
            self.calls += 1
            return [{"event_id": "EV_DESIGN", "reason": (
                "For Senior, System Design is 2 against 4 and this raises it to 3. "
                "You have no similar activity history (0 of 0)."
            )}]

    explainer = GoodExplainer()
    service = RecommendationService(explainer=explainer)
    data = payload()
    data["lang"] = "en"
    first = RecommendRequest.model_validate(data)
    assert asyncio.run(service.recommend(first)).source == "llm"
    assert asyncio.run(service.recommend(first)).source == "llm"
    assert explainer.calls == 1
    changed = deepcopy(data)
    changed["history"] = [{"event_id": "EV_SPEAK", "status": "skipped"}]
    asyncio.run(service.recommend(RecommendRequest.model_validate(changed)))
    assert explainer.calls == 2


def test_kazakh_request_rejects_english_llm_reason() -> None:
    class EnglishExplainer:
        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": (
                "For Senior, System Design is 2 against 4 and this raises it to 3. "
                "You have no similar activity history (0 of 0)."
            )}]

    data = payload()
    data["lang"] = "kk"
    result = asyncio.run(RecommendationService(explainer=EnglishExplainer()).recommend(
        RecommendRequest.model_validate(data)
    ))
    assert result.source == "fallback"
    assert "дағдысы" in result.recommendations[0].reason


def test_reason_without_numeric_facts_falls_back() -> None:
    class VagueExplainer:
        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": "Это полезно для Senior."}]

    result = asyncio.run(RecommendationService(explainer=VagueExplainer()).recommend(
        RecommendRequest.model_validate(payload())
    ))
    assert result.source == "fallback"
    assert "сейчас 2" in result.recommendations[0].reason


def test_llm_strategy_requests_structured_output() -> None:
    class FakeCompletions:
        async def create(self, **kwargs):
            assert kwargs["temperature"] == 0
            assert kwargs["response_format"]["type"] == "json_schema"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content='{"recommendations":[{"event_id":"EV_DESIGN","reason":"Useful."}]}'
            ))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    request = RecommendRequest.model_validate(payload())
    candidates = ScoringService().rank(request)[:5]
    strategy = SDKExplanationStrategy(client, "test-model", structured=True)
    assert asyncio.run(strategy.select(request, candidates)) == [
        {"event_id": "EV_DESIGN", "reason": "Useful."}
    ]


def test_llm_timeout_falls_back_within_budget() -> None:
    class SlowExplainer:
        async def select(self, *_args, **_kwargs):
            await asyncio.sleep(1)

    service = RecommendationService(explainer=SlowExplainer(), timeout=0.01)
    result = asyncio.run(service.recommend(RecommendRequest.model_validate(payload())))
    assert result.source == "fallback"


def test_malformed_employee_returns_validation_error() -> None:
    data = payload()
    data["employee"] = None
    data.pop("lang")
    with TestClient(create_app()) as client:
        response = client.post("/recommend", json=data)
    assert response.status_code == 422


def test_multi_skill_event_explains_the_highest_value_skill() -> None:
    data = payload()
    data["events"] = [{
        "event_id": "EV_MULTI", "title": "Mixed workshop", "type": "workshop",
        "skills": {
            "SK_PUBLIC_SPEAKING": {"gain": 1, "max_level": 5},
            "SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4},
        },
    }]
    result = recommend(data)
    factors = result["recommendations"][0]["factors"]
    assert next(factor for factor in factors if factor["type"] == "skill_gap")["skill"] == "SK_SYSTEM_DESIGN"


def test_multi_skill_score_is_fully_explained_by_factors() -> None:
    data = payload()
    data["employee"]["skills"]["SK_PYTHON"] = 3
    data["next_grade_requirements"]["SK_PYTHON"] = 4
    data["events"] = [{
        "event_id": "EV_MULTI", "title": "Mixed workshop", "type": "workshop",
        "skills": {
            "SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4},
            "SK_PYTHON": {"gain": 1, "max_level": 5},
        },
    }]
    item = recommend(data)["recommendations"][0]
    gains = [factor for factor in item["factors"] if factor["type"] == "effective_gain"]
    assert {factor["skill"] for factor in gains} == {"SK_SYSTEM_DESIGN", "SK_PYTHON"}
    assert sum(factor["weighted_gap_closed"] for factor in gains) == item["calculation"]["gap_closed"]
    assert "SK_PYTHON" in item["reason"]


def test_fallback_prefers_only_grade_gap_closing_events_when_available() -> None:
    data = payload()
    data["employee"]["skills"]["SK_PYTHON"] = 3
    data["next_grade_requirements"]["SK_PYTHON"] = 3
    data["events"] = [data["events"][0], {
        "event_id": "EV_PYTHON", "title": "Advanced Python", "type": "course",
        "skills": {"SK_PYTHON": {"gain": 1, "max_level": 5}},
    }]
    result = recommend(data)
    assert [item["event_id"] for item in result["recommendations"]] == ["EV_DESIGN"]


def test_fallback_can_offer_enrichment_when_no_grade_gap_event_exists() -> None:
    data = payload()
    data["employee"]["skills"]["SK_SYSTEM_DESIGN"] = 4
    data["events"] = [data["events"][1]]
    result = recommend(data)
    assert [item["event_id"] for item in result["recommendations"]] == ["EV_SPEAK"]


def test_malformed_starter_kit_event_returns_validation_error() -> None:
    data = payload()
    data["events"] = [{
        "event_id": "EV_BAD", "title": "Bad event", "type": "course",
        "develops_skills": None,
    }]
    with TestClient(create_app()) as client:
        response = client.post("/recommend", json=data)
    assert response.status_code == 422


# --- Review fixes -----------------------------------------------------------


def test_critical_skill_gap_outranks_equal_noncritical_gap() -> None:
    data = payload()
    data["employee"]["skills"] = {"SK_SYSTEM_DESIGN": 2, "SK_CLOUD": 2}
    data["next_grade_requirements"] = {"SK_SYSTEM_DESIGN": 4, "SK_CLOUD": 4}
    data["critical_skills"] = ["SK_SYSTEM_DESIGN"]
    data["events"] = [
        # Sorted first by event_id on a tie, so the test only passes if critical weight wins.
        {"event_id": "EV_A_CLOUD", "title": "Cloud", "type": "course",
         "skills": {"SK_CLOUD": {"gain": 1, "max_level": 4}}},
        {"event_id": "EV_B_DESIGN", "title": "Design", "type": "course",
         "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}},
    ]
    result = recommend(data)
    assert result["recommendations"][0]["event_id"] == "EV_B_DESIGN"
    gain = next(f for f in result["recommendations"][0]["factors"] if f["type"] == "effective_gain")
    assert gain["weight"] > 1.5


def test_missed_history_of_another_skill_penalizes_unrelated_event_only_weakly() -> None:
    data = payload()
    data["history"] = [{"event_id": "EV_SPEAK", "status": "no_show"} for _ in range(3)]
    result = recommend(data)
    by_id = {item["event_id"]: item for item in result["recommendations"]}
    design_history = next(f for f in by_id["EV_DESIGN"]["factors"] if f["type"] == "history")
    assert design_history["total"] == 0, "public speaking misses are not System Design history"
    assert design_history["same_type_total"] == 3
    design_engagement = by_id["EV_DESIGN"]["calculation"]["engagement"]
    speak = ScoringService().rank(RecommendRequest.model_validate(data))
    speak_engagement = next(c.engagement for c in speak if c.event.event_id == "EV_SPEAK")
    assert speak_engagement < design_engagement < 0.5


def test_in_progress_event_is_not_recommended_again() -> None:
    data = payload()
    data["history"] = [{"event_id": "EV_DESIGN", "status": "in_progress"}]
    result = recommend(data)
    assert all(item["event_id"] != "EV_DESIGN" for item in result["recommendations"])


def test_in_progress_history_does_not_lower_related_event_engagement() -> None:
    data = payload()
    data["history"] = [{"event_id": "EV_DESIGN", "status": "in_progress"}]
    data["events"].append({"event_id": "EV_DESIGN2", "title": "Design 2", "type": "workshop",
                           "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}})
    ranked = ScoringService().rank(RecommendRequest.model_validate(data))
    related = next(candidate for candidate in ranked if candidate.event.event_id == "EV_DESIGN2")
    assert related.engagement == 0.5
    history = next(factor for factor in related.factors if factor["type"] == "history")
    assert history["total"] == 0


def test_overdue_counts_as_missed_history() -> None:
    data = payload()
    data["history"] = [{"event_id": "EV_DESIGN", "status": "overdue"}]
    data["events"].append({"event_id": "EV_DESIGN2", "title": "Design 2", "type": "workshop",
                           "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}})
    result = recommend(data)
    history = next(f for f in result["recommendations"][0]["factors"] if f["type"] == "history")
    assert history["missed"] == 1


def test_recent_miss_weighs_more_than_old_miss() -> None:
    def engagement_with(dates: list[str]) -> float:
        data = payload()
        data["history"] = [{"event_id": "EV_DESIGN", "status": "completed", "date": "2026-09-01"}] + [
            {"event_id": "EV_DESIGN", "status": "no_show", "date": date} for date in dates
        ]
        data["events"][0]["recurring"] = True
        ranked = ScoringService().rank(RecommendRequest.model_validate(data))
        return next(c.engagement for c in ranked if c.event.event_id == "EV_DESIGN")

    assert engagement_with(["2024-10-15"]) > engagement_with(["2026-08-15"])


def test_fallback_result_is_not_cached() -> None:
    class FlakyExplainer:
        calls = 0

        async def select(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("provider down")
            return [{"event_id": "EV_DESIGN", "reason": (
                "For Senior, System Design is 2 against 4 and this raises it to 3. "
                "You have no similar activity history (0 of 0)."
            )}]

    data = payload()
    data["lang"] = "en"
    service = RecommendationService(explainer=FlakyExplainer())
    request = RecommendRequest.model_validate(data)
    assert asyncio.run(service.recommend(request)).source == "fallback"
    assert asyncio.run(service.recommend(request)).source == "llm"


def test_invalid_llm_item_is_dropped_but_valid_items_kept() -> None:
    class MixedExplainer:
        async def select(self, *_args, **_kwargs):
            return [
                {"event_id": "EV_DESIGN", "reason": (
                    "For Senior, System Design is 2 against 4 and this raises it to 3. "
                    "You completed 0 of 0 similar activities."
                )},
                {"event_id": "NOT_A_CANDIDATE", "reason": "invented"},
            ]

    data = payload()
    data["lang"] = "en"
    result = asyncio.run(RecommendationService(explainer=MixedExplainer()).recommend(
        RecommendRequest.model_validate(data)
    ))
    assert result.source == "llm"
    assert [item.event_id for item in result.recommendations] == ["EV_DESIGN"]


def test_reason_with_levels_but_without_history_counts_is_accepted() -> None:
    class LevelsOnlyExplainer:
        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": (
                "For Senior you need System Design 4 and you are at 2; this workshop raises it to 3. "
                "You have not attended similar activities yet."
            )}]

    data = payload()
    data["lang"] = "en"
    result = asyncio.run(RecommendationService(explainer=LevelsOnlyExplainer()).recommend(
        RecommendRequest.model_validate(data)
    ))
    assert result.source == "llm"


def test_batch_returns_primary_skill_and_gaps() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/score/batch", json={"items": [payload()]})
    result = response.json()["results"][0]
    assert result["top"][0]["primary_skill"] == "SK_SYSTEM_DESIGN"
    assert result["gaps"] == {"SK_SYSTEM_DESIGN": 2}


def test_failover_gives_second_provider_its_own_time_budget() -> None:
    from app.explain import FailoverExplanationStrategy

    class Hanging:
        async def select(self, *_args, **_kwargs):
            await asyncio.sleep(5)

    class Quick:
        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": "ok"}]

    strategy = FailoverExplanationStrategy([Hanging(), Quick()], attempt_timeout=0.05)
    request = RecommendRequest.model_validate(payload())
    candidates = ScoringService().rank(request)[:5]
    assert asyncio.run(strategy.select(request, candidates)) == [{"event_id": "EV_DESIGN", "reason": "ok"}]


def test_legacy_generate_endpoint_is_removed() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/generate", json={"prompt": "hi"})
    assert response.status_code == 404


# --- Live-audit fixes (2026-09-23) -------------------------------------------


def _capture_prompt(data: dict) -> dict:
    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content='{"recommendations":[{"event_id":"EV_DESIGN","reason":"Useful."}]}'
            ))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    request = RecommendRequest.model_validate(data)
    candidates = ScoringService().rank(request)[:5]
    asyncio.run(SDKExplanationStrategy(client, "m").select(request, candidates))
    return captured


def test_llm_prompt_hides_internal_weights_and_exposes_flags() -> None:
    data = payload()
    data["critical_skills"] = ["SK_SYSTEM_DESIGN"]
    data["events"][0]["description"] = "Hands-on design of distributed systems."
    captured = _capture_prompt(data)
    user = captured["messages"][1]["content"]
    assert "weighted_gap_closed" not in user and '"weight"' not in user
    assert '"closes_gap": true' in user
    assert '"critical": true' in user
    assert "Hands-on design" in user
    assert "System Design" in user  # skill names, not only IDs
    system = captured["messages"][0]["content"]
    assert "not critical" in system and "required" in system


def test_ungrounded_reason_is_replaced_by_template_and_flagged() -> None:
    class MixedExplainer:
        async def select(self, *_args, **_kwargs):
            return [
                {"event_id": "EV_DESIGN", "reason": "Это полезно для Senior."},  # no levels
                {"event_id": "EV_SPEAK", "reason": (
                    "Для Senior нужен уровень 4 по System Design, но публичные выступления тоже "
                    "важны: сейчас 1, после активности будет 2. Похожих активностей у вас пока не было."
                )},
            ]

    result = asyncio.run(RecommendationService(explainer=MixedExplainer()).recommend(
        RecommendRequest.model_validate(payload())
    ))
    assert result.source == "llm"
    assert [r.event_id for r in result.recommendations] == ["EV_DESIGN", "EV_SPEAK"]
    assert result.recommendations[0].reason_source == "template"
    assert "сейчас 2" in result.recommendations[0].reason
    assert result.recommendations[1].reason_source == "llm"


def test_all_reasons_ungrounded_means_fallback_source() -> None:
    class VagueExplainer:
        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": "Это полезно для Senior."}]

    result = asyncio.run(RecommendationService(explainer=VagueExplainer()).recommend(
        RecommendRequest.model_validate(payload())
    ))
    assert result.source == "fallback"
    assert result.recommendations[0].reason_source == "template"


def test_duplicate_llm_reason_is_replaced_for_second_event() -> None:
    same = ("For Senior, System Design is 2 against 4 and this raises it to 3. "
            "You have no similar activity history.")
    data = payload()
    data["lang"] = "en"
    data["events"].append({"event_id": "EV_DESIGN2", "title": "Design 2", "type": "course",
                           "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}})

    class CopyPaste:
        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": same}, {"event_id": "EV_DESIGN2", "reason": same}]

    result = asyncio.run(RecommendationService(explainer=CopyPaste()).recommend(
        RecommendRequest.model_validate(data)
    ))
    assert result.recommendations[0].reason_source == "llm"
    assert result.recommendations[1].reason_source == "template"


def test_llm_candidates_prefer_gap_closing_events() -> None:
    seen = {}

    class Recorder:
        async def select(self, _request, candidates):
            seen["ids"] = [c.event.event_id for c in candidates]
            raise RuntimeError("stop")

    data = payload()
    data["employee"]["skills"] = {"SK_SYSTEM_DESIGN": 2, "SK_PUBLIC_SPEAKING": 5, "SK_A": 0, "SK_B": 0, "SK_C": 0}
    data["next_grade_requirements"] = {"SK_SYSTEM_DESIGN": 4, "SK_A": 1, "SK_B": 1, "SK_C": 1}
    data["events"] = [
        {"event_id": f"EV_{s}", "title": s, "type": "course", "skills": {s: {"gain": 1, "max_level": 5}}}
        for s in ["SK_SYSTEM_DESIGN", "SK_A", "SK_B", "SK_C"]
    ] + [
        {"event_id": "EV_X", "title": "X", "type": "course", "skills": {"SK_X": {"gain": 1, "max_level": 5}}},
        {"event_id": "EV_Y", "title": "Y", "type": "course", "skills": {"SK_Y": {"gain": 1, "max_level": 5}}},
    ]
    asyncio.run(RecommendationService(explainer=Recorder()).recommend(RecommendRequest.model_validate(data)))
    assert set(seen["ids"]) == {"EV_SK_SYSTEM_DESIGN", "EV_SK_A", "EV_SK_B", "EV_SK_C"}


def test_completions_after_last_review_are_applied_to_skills() -> None:
    data = payload()
    data["employee"]["last_review_date"] = "2026-06-01"
    data["events"][0]["recurring"] = True
    data["history"] = [{"event_id": "EV_DESIGN", "status": "completed", "date": "2026-08-15"}]
    result = recommend(data)
    assert result["applied_progress"] == [
        {"event_id": "EV_DESIGN", "skill": "SK_SYSTEM_DESIGN", "from": 2, "to": 3}
    ]
    gap = next(f for f in result["recommendations"][0]["factors"] if f["type"] == "skill_gap")
    assert gap["current"] == 3
    assert result["gaps"] == {"SK_SYSTEM_DESIGN": 1}


def test_completion_before_last_review_is_already_in_skills() -> None:
    data = payload()
    data["employee"]["last_review_date"] = "2026-09-01"
    data["events"][0]["recurring"] = True
    data["history"] = [{"event_id": "EV_DESIGN", "status": "completed", "date": "2026-08-15"}]
    result = recommend(data)
    assert result["applied_progress"] == []


def test_scheduled_event_without_upcoming_sessions_is_not_recommended() -> None:
    data = payload()
    data["events"][0]["format"] = "offline"
    data["events"][0]["upcoming_sessions"] = []
    data["events"][1]["format"] = "self_paced"
    data["events"][1]["upcoming_sessions"] = []
    result = recommend(data)
    assert [item["event_id"] for item in result["recommendations"]] == ["EV_SPEAK"]


def test_batch_reports_participation_summary_for_hr() -> None:
    data = payload()
    data["history"] = [
        {"event_id": "EV_SPEAK", "status": "no_show", "date": "2026-08-01"},
        {"event_id": "EV_SPEAK", "status": "completed", "date": "2026-05-01"},
        {"event_id": "EV_SPEAK", "status": "in_progress", "date": "2026-09-01"},
    ]
    with TestClient(create_app()) as client:
        result = client.post("/score/batch", json={"items": [data]}).json()["results"][0]
    assert result["participation"] == {
        "completed": 1, "missed": 1, "in_progress": 1, "total": 3, "last_activity_date": "2026-09-01",
    }


def test_llm_view_gives_a_ready_made_levels_fact_per_skill() -> None:
    from app.explain import llm_view

    data = payload()
    data["critical_skills"] = ["SK_SYSTEM_DESIGN"]
    request = RecommendRequest.model_validate(data)
    view = llm_view(request, ScoringService().rank(request)[0])
    fact = view["skills"][0]["fact"]
    assert fact == "System Design: current 2, required 4 for Senior (critical), after this activity 3"
    assert "System Design: current 2, required 4 for Senior (critical), after this activity 3" in view["facts_sentence"]


# --- Provider switching --------------------------------------------------------


def test_failover_reports_which_provider_answered() -> None:
    from app.explain import FailoverExplanationStrategy

    class Down:
        name = "openai"

        async def select(self, *_args, **_kwargs):
            raise RuntimeError("provider down")

    class Up:
        name = "nvidia"

        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": "ok"}]

    strategy = FailoverExplanationStrategy([Down(), Up()])
    request = RecommendRequest.model_validate(payload())
    candidates = ScoringService().rank(request)[:5]
    proposal = asyncio.run(strategy.select(request, candidates))
    assert list(proposal) == [{"event_id": "EV_DESIGN", "reason": "ok"}]
    assert proposal.provider == "nvidia"


def test_recommend_response_names_the_llm_provider() -> None:
    from app.explain import FailoverExplanationStrategy

    class Nvidia:
        name = "nvidia"

        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": (
                "For Senior, System Design is 2 against 4 and this raises it to 3. "
                "You have no similar activity history."
            )}]

    data = payload()
    data["lang"] = "en"
    service = RecommendationService(explainer=FailoverExplanationStrategy([Nvidia()]))
    result = asyncio.run(service.recommend(RecommendRequest.model_validate(data)))
    assert result.source == "llm"
    assert result.llm_provider == "nvidia"


def test_fallback_response_has_no_provider() -> None:
    result = asyncio.run(RecommendationService().recommend(RecommendRequest.model_validate(payload())))
    assert result.source == "fallback"
    assert result.llm_provider is None


def test_providers_endpoint_lists_configured_providers_in_order(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("LLM_PROVIDERS", "nvidia,openai")
    monkeypatch.setenv("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")
    with TestClient(create_app()) as client:
        body = client.get("/providers").json()
    assert [item["name"] for item in body["providers"]] == ["nvidia", "openai"]
    assert body["providers"][0]["model"] == "nvidia/llama-3.1-nemotron-70b-instruct"
    assert body["providers"][0]["structured_output"] is False
    assert body["providers"][1]["structured_output"] is True
    assert "nvapi" not in str(body) and "sk-test" not in str(body)


def test_providers_endpoint_skips_unconfigured_and_reports_fallback_only(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    with TestClient(create_app()) as client:
        body = client.get("/providers").json()
    assert body["providers"] == []
    assert body["explanations"] == "template"


def test_failover_gives_remaining_budget_to_the_next_provider_after_a_fast_failure() -> None:
    from app.explain import FailoverExplanationStrategy

    class FailsFast:
        name = "nvidia"

        async def select(self, *_args, **_kwargs):
            raise RuntimeError("401")

    class Slow:
        name = "openai"

        async def select(self, *_args, **_kwargs):
            await asyncio.sleep(0.3)  # longer than half the budget, shorter than the whole budget
            return [{"event_id": "EV_DESIGN", "reason": "ok"}]

    strategy = FailoverExplanationStrategy([FailsFast(), Slow()], budget=0.5)
    request = RecommendRequest.model_validate(payload())
    candidates = ScoringService().rank(request)[:5]
    proposal = asyncio.run(strategy.select(request, candidates))
    assert proposal.provider == "openai"


def test_failover_caps_a_hanging_primary_so_the_secondary_still_runs() -> None:
    from app.explain import FailoverExplanationStrategy

    class Hangs:
        name = "openai"

        async def select(self, *_args, **_kwargs):
            await asyncio.sleep(5)

    class Quick:
        name = "nvidia"

        async def select(self, *_args, **_kwargs):
            return [{"event_id": "EV_DESIGN", "reason": "ok"}]

    strategy = FailoverExplanationStrategy([Hangs(), Quick()], budget=0.4)
    request = RecommendRequest.model_validate(payload())
    candidates = ScoringService().rank(request)[:5]
    proposal = asyncio.run(strategy.select(request, candidates))
    assert proposal.provider == "nvidia"
