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
            return [{"event_id": "EV_DESIGN", "reason": "Useful for the next grade."}]

    explainer = GoodExplainer()
    service = RecommendationService(explainer=explainer)
    first = RecommendRequest.model_validate(payload())
    assert asyncio.run(service.recommend(first)).source == "llm"
    assert asyncio.run(service.recommend(first)).source == "llm"
    assert explainer.calls == 1
    changed = deepcopy(payload())
    changed["history"] = [{"event_id": "EV_SPEAK", "status": "skipped"}]
    asyncio.run(service.recommend(RecommendRequest.model_validate(changed)))
    assert explainer.calls == 2


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


def test_malformed_starter_kit_event_returns_validation_error() -> None:
    data = payload()
    data["events"] = [{
        "event_id": "EV_BAD", "title": "Bad event", "type": "course",
        "develops_skills": None,
    }]
    with TestClient(create_app()) as client:
        response = client.post("/recommend", json=data)
    assert response.status_code == 422
