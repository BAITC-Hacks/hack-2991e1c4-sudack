import csv
import json
from collections import defaultdict
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from app.api import create_app
from app.recommendation import RecommendationService


DATA = Path(__file__).resolve().parents[1] / "docs" / "data"
GRADES = ["Junior", "Middle", "Senior", "Lead"]


def dataset_payloads() -> list[dict]:
    skills = json.loads((DATA / "skills.json").read_text(encoding="utf-8"))
    employees = json.loads((DATA / "employees.json").read_text(encoding="utf-8"))["employees"]
    events = json.loads((DATA / "events.json").read_text(encoding="utf-8"))["events"]
    profiles = {(p["role"], p["grade"]): p for p in skills["role_profiles"]}
    metadata = {s["skill_id"]: {"name": s["name"], "category": s["category"]}
                for s in skills["skills"]}
    history = defaultdict(list)
    with (DATA / "activity_history.csv").open(encoding="utf-8", newline="") as file:
        for entry in csv.DictReader(file):
            history[entry["employee_id"]].append({
                "event_id": entry["event_id"], "date": entry["date"], "status": entry["status"]
            })
    requests = []
    for employee in employees:
        grade = GRADES[min(GRADES.index(employee["grade"]) + 1, len(GRADES) - 1)]
        profile = profiles[(employee["role"], grade)]
        requests.append({
            "employee": employee,
            "next_grade": grade,
            "next_grade_requirements": profile["required_skills"],
            "critical_skills": profile["critical_skills"],
            "skills_meta": metadata,
            "history": history[employee["employee_id"]],
            "events": events,
            "lang": employee["preferred_language"],
        })
    return requests


def test_full_starter_kit_batch_and_recommendation() -> None:
    requests = dataset_payloads()
    assert len(requests) == 200
    with TestClient(create_app(recommendation_service=RecommendationService())) as client:
        start = perf_counter()
        batch = client.post("/score/batch", json={"items": requests})
        elapsed = perf_counter() - start
        assert batch.status_code == 200, batch.text
        assert len(batch.json()["results"]) == 200
        # CI has variable speed; the operational target is around one second.
        assert elapsed < 3.0

        recommendation = client.post("/recommend", json=requests[1])
        assert recommendation.status_code == 200, recommendation.text
        assert recommendation.json()["source"] == "fallback"
        assert len(recommendation.json()["recommendations"]) <= 3
