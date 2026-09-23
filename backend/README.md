# Career Quest backend

Go 1.26.1 + Echo + SQLite/sqlc. The backend stores the synthetic starter kit, enforces employee/HR access, records completed activities, and sends context to Sudack AI for explainable recommendations and HR insights.

## Start

From the backend directory:

    docker compose up --build

Compose starts the AI service, mounts ../sudack-ai/docs/data read-only, initializes the SQLite database on first start, and starts the Go API on port 8080. SQLite persists in the career_quest_db volume. The AI service uses its deterministic explanation fallback when no provider key is configured. To use a provider, set OPENAI_API_KEY or NVIDIA_API_KEY in the shell before starting Compose. Set AUTH_SECRET to a private value outside the local demo.

The initial import command can also be run locally:

    go run ./cmd/migrate -db .local/db/test.db -data ../sudack-ai/docs/data

The default importer preserves an existing database. To add judge profiles and history later, use:

    go run ./cmd/migrate -append -db .local/db/test.db -data /path/to/additional-data

The additional directory needs employees.json and activity_history.csv in the starter-kit schema. Existing employee snapshots are preserved.

## Demo tokens

The API uses signed bearer tokens. Generate tokens in the running backend container; the CLI reads the same AUTH_SECRET as the server:

    docker compose exec backend ./careerquest-token -role hr
    docker compose exec backend ./careerquest-token -role employee -employee E0028

Use the printed value as the Authorization header: Bearer <token>. An employee token accesses only its own data; HR can read any profile and the HR endpoints. /healthz is public.

## Main API

| Method | Path | Role | Result |
| --- | --- | --- | --- |
| GET | /healthz | public | SQLite readiness |
| GET | /api/v1/employees/:employee_id | self or HR | Profile, current skills, gaps, participation |
| GET | /api/v1/employees/:employee_id/recommendations | self or HR | AI recommendations and counterfactual rejected alternatives |
| GET | /api/v1/employees/:employee_id/roadmap | self or HR | AI grade roadmap and blocked skills |
| POST | /api/v1/employees/:employee_id/events/:event_id/preview | self or HR | Deterministic skill and readiness change |
| POST | /api/v1/employees/:employee_id/events/:event_id/completions | self | Record completion; requires Idempotency-Key |
| GET | /api/v1/hr/employees | HR | Employee IDs |
| GET | /api/v1/hr/overview | HR | Skill gaps, activity participation, dropout risk, employees with no step |
| POST | /api/v1/hr/events/impact | HR | AI estimate for a draft event; JSON body is the event object |

Use lang=ru, lang=kk, or lang=en on employee read endpoints. Error responses have the shared shape {"code":"...","message":"..."}.

A completion appends a completed history row. The assessment snapshot in employee_skills stays unchanged; current skills are derived by applying completions after last_review_date, exactly as the AI service does. Duplicate Idempotency-Key requests return replayed=true and do not apply growth twice.

## Architecture

cmd/migrate imports the four starter-kit files into SQLite. internal/repository/sqlite reconstructs the AI request from the normalized database. internal/service calculates deterministic progress and calls Sudack AI /recommend, /simulate, /score/batch and /events/impact. The AI service ranks activities and supplies grounded reasons; Go owns access control and persistence. See BACKEND.md for the full data and route contract.

The AI response includes source and llm_provider, so the UI can tell an LLM explanation from the deterministic fallback. No real employee data is used.
