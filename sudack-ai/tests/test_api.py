from fastapi.testclient import TestClient

from app.api import create_app


def test_health() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_app_starts_without_provider_keys_and_serves_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    with TestClient(create_app()) as client:
        response = client.post("/recommend", json={
            "employee": {"employee_id": "E1", "role": "Backend Engineer", "grade": "Middle",
                         "skills": {"SK_SYSTEM_DESIGN": 2}},
            "next_grade": "Senior",
            "next_grade_requirements": {"SK_SYSTEM_DESIGN": 4},
            "events": [{"event_id": "EV1", "title": "Design", "type": "workshop",
                        "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}}],
        })
    assert response.status_code == 200
    assert response.json()["source"] == "fallback"
