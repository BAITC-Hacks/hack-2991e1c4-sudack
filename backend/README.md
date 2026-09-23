# Career Quest backend

Go 1.26.1 + Echo + SQLite/sqlc. The backend stores the synthetic starter kit, enforces employee/HR access, records completed activities, lets HR upload the jury's extra profiles, and sends context to Sudack AI for explainable recommendations, roadmaps and HR insights.

## Start

The whole stack starts from the repository root with `docker compose up --build` (frontend on 3000, this API on 8080, AI on 8001). From this directory alone:

    docker compose up --build

Compose mounts ../sudack-ai/docs/data read-only, initializes the SQLite database on first start, and starts the Go API on port 8080. SQLite persists in a named volume. The AI service uses its deterministic explanation fallback when no provider key is configured; set OPENAI_API_KEY to get LLM-written explanations. Set AUTH_SECRET to a private value and DEMO_AUTH=false outside the local demo.

Local without Docker:

    go run ./cmd/migrate -db .local/db/test.db -data ../sudack-ai/docs/data
    go run ./cmd
    go test ./...

## Access

Every route except /healthz needs a signed bearer token with a role. The login screen gets one from `POST /api/v1/auth/demo-token` (`{"role":"employee","employee_id":"E0028"}` or `{"role":"hr"}`), enabled by DEMO_AUTH=true. The same tokens can be minted from the CLI:

    docker compose exec backend ./careerquest-token -role hr
    docker compose exec backend ./careerquest-token -role employee -employee E0028

An employee token accesses only its own data; HR can read any profile, the HR views, upload data and estimate draft events, but cannot complete activities for employees.

## Main API

| Method | Path | Role | Result |
| --- | --- | --- | --- |
| GET | /healthz | public | SQLite readiness |
| POST | /api/v1/auth/demo-token | public (demo) | Signed role token |
| GET | /api/v1/employees/:employee_id | self or HR | Profile, current skills, gaps table, readiness, history |
| GET | /api/v1/employees/:employee_id/recommendations | self or HR | AI recommendations with factors, calculation, "why not" alternatives, provider |
| GET | /api/v1/employees/:employee_id/roadmap | self or HR | AI grade roadmap, coverage and blocked skills |
| POST | /api/v1/employees/:employee_id/events/:event_id/preview | self or HR | Deterministic skill and readiness change |
| POST | /api/v1/employees/:employee_id/events/:event_id/completions | self | Record completion; requires Idempotency-Key |
| GET | /api/v1/hr/employees | HR | Employee IDs |
| GET | /api/v1/hr/overview | HR | Weak skills, employees without a step, participation, dropout risk |
| POST | /api/v1/hr/events/impact | HR | AI estimate for a draft event; JSON body is the event object |
| POST | /api/v1/imports | HR | Upload employees.json and/or activity_history.csv in the kit format |

Use lang=ru, lang=kk, or lang=en on employee read endpoints. Error responses have the shared shape {"code":"...","message":"..."}. Field-level shapes are in BACKEND.md.

A completion appends a completed history row. The assessment snapshot in employee_skills stays unchanged; current skills are derived by applying completions after last_review_date, exactly as the AI service does. Duplicate Idempotency-Key requests return replayed=true and do not apply growth twice.

## Architecture

cmd/migrate imports the four starter-kit files into SQLite. internal/repository/sqlite reconstructs the AI request from the normalized database and appends uploaded profiles. internal/service calculates deterministic progress and calls Sudack AI /recommend, /simulate, /score/batch and /events/impact; batch calls send the event catalog once. The AI service ranks activities and supplies grounded reasons; Go owns access control and persistence.

The AI response includes source and llm_provider, so the UI can tell an LLM explanation from the deterministic fallback. No real employee data is used.
