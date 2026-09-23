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


def test_cors_allows_the_frontend_origin(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    with TestClient(create_app()) as client:
        response = client.options("/recommend", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_batch_accepts_a_shared_event_catalog_and_skills_meta() -> None:
    events = [{"event_id": "EV1", "title": "Design", "type": "workshop",
               "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}}]
    item = {"employee": {"employee_id": "E1", "role": "Backend Engineer", "grade": "Middle",
                         "skills": {"SK_SYSTEM_DESIGN": 2}},
            "next_grade": "Senior", "next_grade_requirements": {"SK_SYSTEM_DESIGN": 4}}
    with TestClient(create_app()) as client:
        response = client.post("/score/batch", json={
            "events": events, "skills_meta": {"SK_SYSTEM_DESIGN": {"name": "System Design"}}, "items": [item],
        })
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["top"][0]["event_id"] == "EV1"


def test_event_impact_accepts_a_shared_event_catalog() -> None:
    events = [{"event_id": "EV1", "title": "Design", "type": "workshop",
               "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}}]
    item = {"employee": {"employee_id": "E1", "role": "Backend Engineer", "grade": "Middle",
                         "skills": {"SK_SYSTEM_DESIGN": 2}},
            "next_grade": "Senior", "next_grade_requirements": {"SK_SYSTEM_DESIGN": 4}}
    draft = {"event_id": "EV_NEW", "title": "Clinic", "type": "workshop",
             "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}}
    with TestClient(create_app()) as client:
        response = client.post("/events/impact", json={"event": draft, "events": events, "items": [item]})
    assert response.status_code == 200, response.text
    assert response.json()["gap_closing_count"] == 1
