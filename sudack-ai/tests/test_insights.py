"""Killer features: why-not explanations, grade simulator, dropout risk, event impact."""

import asyncio

from fastapi.testclient import TestClient

from app.api import create_app
from app.models import RecommendRequest
from app.recommendation import RecommendationService


def payload() -> dict:
    return {
        "employee": {"employee_id": "E1", "role": "Backend Engineer", "grade": "Middle",
                     "skills": {"SK_SYSTEM_DESIGN": 2, "SK_PUBLIC_SPEAKING": 0}},
        "next_grade": "Senior",
        "next_grade_requirements": {"SK_SYSTEM_DESIGN": 4, "SK_PUBLIC_SPEAKING": 2},
        "critical_skills": ["SK_SYSTEM_DESIGN"],
        "skills_meta": {"SK_SYSTEM_DESIGN": {"name": "System Design"},
                        "SK_PUBLIC_SPEAKING": {"name": "Public Speaking"}},
        "history": [],
        "events": [
            {"event_id": "EV_DESIGN", "title": "Design workshop", "type": "workshop",
             "format": "offline", "duration_hours": 8,
             "upcoming_sessions": ["2026-10-10", "2026-11-10"],
             "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}},
            {"event_id": "EV_SPEAK", "title": "Public speaking", "type": "meetup",
             "format": "offline", "duration_hours": 2, "recurring": True,
             "upcoming_sessions": ["2026-10-05", "2026-10-19"],
             "skills": {"SK_PUBLIC_SPEAKING": {"gain": 1, "max_level": 4}}},
        ],
        "lang": "ru",
    }


def recommend(data: dict) -> dict:
    return asyncio.run(RecommendationService().recommend(RecommendRequest.model_validate(data))).model_dump()


# --- 1. Why not the lowest skill ----------------------------------------------


def test_rejected_explains_why_lowest_skill_event_lost() -> None:
    data = payload()
    data["history"] = [{"event_id": "EV_SPEAK", "status": "no_show", "date": f"2026-0{m}-01"} for m in (6, 7, 8)]
    result = recommend(data)
    assert result["recommendations"][0]["event_id"] == "EV_DESIGN"
    rejected = result["rejected"][0]
    assert rejected["event_id"] == "EV_SPEAK"
    assert rejected["skill"] == "SK_PUBLIC_SPEAKING"
    assert rejected["current"] == 0 and rejected["required"] == 2
    assert "3 из 3" in rejected["reason"]
    assert "критич" in rejected["reason"]


def test_rejected_reports_lowest_skill_with_no_eligible_event() -> None:
    data = payload()
    data["events"] = [data["events"][0]]  # nothing develops Public Speaking
    result = recommend(data)
    rejected = result["rejected"][0]
    assert rejected["event_id"] is None
    assert rejected["skill"] == "SK_PUBLIC_SPEAKING"
    assert "нет доступных" in rejected["reason"]


def test_rejected_is_empty_when_lowest_skill_is_recommended() -> None:
    data = payload()
    data["critical_skills"] = ["SK_PUBLIC_SPEAKING"]
    result = recommend(data)
    assert result["recommendations"][0]["event_id"] == "EV_SPEAK"
    assert all(item["event_id"] != "EV_SPEAK" for item in result["rejected"])


# --- 2. Grade simulator --------------------------------------------------------


def simulate(data: dict) -> dict:
    with TestClient(create_app()) as client:
        response = client.post("/simulate", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_simulate_builds_ordered_roadmap_to_next_grade() -> None:
    data = payload()
    data["events"] = [
        {"event_id": "EV_D1", "title": "Design 1", "type": "course", "format": "self_paced",
         "duration_hours": 6, "upcoming_sessions": [],
         "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 3}}},
        {"event_id": "EV_D2", "title": "Design 2", "type": "workshop", "format": "offline",
         "duration_hours": 8, "upcoming_sessions": ["2026-10-20", "2026-12-01"],
         "prerequisites": {"SK_SYSTEM_DESIGN": 3},
         "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}},
        data["events"][1],
    ]
    data["as_of"] = "2026-10-01"
    result = simulate(data)
    ids = [step["event_id"] for step in result["steps"]]
    assert ids[:2] == ["EV_D1", "EV_D2"], "prerequisite forces the order"
    assert ids.count("EV_SPEAK") == 2, "recurring club repeats until the requirement is met"
    assert result["reachable"] is True
    assert result["remaining_gaps"] == {}
    assert result["total_hours"] == 6 + 8 + 2 + 2
    assert result["steps"][1]["date"] == "2026-10-20"
    assert result["readiness_path"][0] < result["readiness_path"][-1] == 1.0
    assert result["estimated_completion"] >= "2026-10-20"


def test_simulate_reports_unreachable_requirements() -> None:
    data = payload()
    data["events"][0]["skills"]["SK_SYSTEM_DESIGN"]["max_level"] = 3
    result = simulate(data)
    assert result["reachable"] is False
    assert result["remaining_gaps"] == {"SK_SYSTEM_DESIGN": 1}
    assert result["blocked"][0]["skill"] == "SK_SYSTEM_DESIGN"


# --- 3. Dropout risk -----------------------------------------------------------


def batch(items: list[dict]) -> list[dict]:
    with TestClient(create_app()) as client:
        response = client.post("/score/batch", json={"items": items})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def test_risk_is_high_for_repeated_recent_misses_and_low_for_completer() -> None:
    risky = payload()
    risky["as_of"] = "2026-10-01"
    risky["history"] = [
        {"event_id": "EV_SPEAK", "status": "completed", "date": "2025-01-10"},
        {"event_id": "EV_SPEAK", "status": "no_show", "date": "2026-07-01"},
        {"event_id": "EV_SPEAK", "status": "no_show", "date": "2026-08-01"},
        {"event_id": "EV_DESIGN", "status": "declined", "date": "2026-09-01"},
    ]
    steady = payload()
    steady["employee"]["employee_id"] = "E2"
    steady["as_of"] = "2026-10-01"
    steady["history"] = [
        {"event_id": "EV_SPEAK", "status": "completed", "date": "2026-06-01"},
        {"event_id": "EV_SPEAK", "status": "completed", "date": "2026-08-01"},
    ]
    results = batch([risky, steady])
    assert results[0]["risk"]["level"] == "high"
    codes = {reason["code"] for reason in results[0]["risk"]["reasons"]}
    assert "recent_misses" in codes
    assert results[1]["risk"]["level"] == "low"
    assert results[0]["risk"]["score"] > results[1]["risk"]["score"]


def test_risk_flags_inactivity_and_suggests_working_format() -> None:
    data = payload()
    data["as_of"] = "2026-10-01"
    data["events"].append({"event_id": "EV_SELF", "title": "Self course", "type": "course",
                           "format": "self_paced", "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}})
    data["history"] = [
        {"event_id": "EV_SPEAK", "status": "no_show", "date": "2025-10-01"},
        {"event_id": "EV_DESIGN", "status": "no_show", "date": "2025-11-01"},
        {"event_id": "EV_SELF", "status": "completed", "date": "2025-12-01"},
        {"event_id": "EV_SELF", "status": "completed", "date": "2026-01-15"},
    ]
    risk = batch([data])[0]["risk"]
    codes = {reason["code"] for reason in risk["reasons"]}
    assert "inactive" in codes
    assert risk["suggested_format"] == "self_paced"


# --- 4. Event impact for HR ----------------------------------------------------


def test_event_impact_counts_gap_closers_and_ranks_against_catalog() -> None:
    first = payload()
    second = payload()
    second["employee"]["employee_id"] = "E2"
    second["employee"]["skills"]["SK_SYSTEM_DESIGN"] = 4  # already meets the requirement
    third = payload()
    third["employee"]["employee_id"] = "E3"
    third["employee"]["role"] = "Data Analyst"  # outside the draft audience
    draft = {"event_id": "EV_NEW", "title": "Architecture clinic", "type": "workshop",
             "format": "online", "duration_hours": 4,
             "audience": {"roles": ["Backend Engineer"], "grades": []},
             "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}}
    with TestClient(create_app()) as client:
        response = client.post("/events/impact", json={"event": draft, "items": [first, second, third]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["audience_count"] == 2
    assert result["gap_closing_count"] == 1
    assert result["gap_closing_employees"] == ["E1"]
    assert result["by_skill"] == {"SK_SYSTEM_DESIGN": 1}
    assert 0 < result["expected_completions"] <= 1
    assert result["hours_per_gap_level"] == 4.0
    assert result["catalog_rank"] == 3  # EV_SPEAK (3 closers) and EV_DESIGN (2) both beat the draft (1)
    assert {item["event_id"] for item in result["catalog_top"]} >= {"EV_DESIGN"}


def test_simulate_classifies_blocked_skills_and_reports_coverage() -> None:
    data = payload()
    data["employee"]["skills"] = {"SK_SYSTEM_DESIGN": 2, "SK_PUBLIC_SPEAKING": 0, "SK_SQL": 1, "SK_CLOUD": 0}
    data["next_grade_requirements"] = {"SK_SYSTEM_DESIGN": 4, "SK_PUBLIC_SPEAKING": 2, "SK_SQL": 3, "SK_CLOUD": 2}
    data["events"][0]["skills"]["SK_SYSTEM_DESIGN"]["max_level"] = 3  # ceiling below the requirement
    data["events"].append({"event_id": "EV_SQL", "title": "SQL for analysts", "type": "course",
                           "format": "self_paced", "audience": {"roles": ["Data Analyst"], "grades": []},
                           "skills": {"SK_SQL": {"gain": 2, "max_level": 5}}})
    # nothing develops SK_CLOUD at all
    result = simulate(data)
    reasons = {item["skill"]: item["reason"] for item in result["blocked"]}
    assert reasons == {
        "SK_SYSTEM_DESIGN": "ceiling",
        "SK_SQL": "audience",
        "SK_CLOUD": "no_event_for_skill",
    }
    # gap levels: SD 2 (1 closable) + PS 2 (2 closable) + SQL 2 (0) + CLOUD 2 (0) = 8 total, 3 closed
    assert result["coverage"] == {"gap_levels_total": 8, "gap_levels_closed": 3, "ratio": 0.375}
