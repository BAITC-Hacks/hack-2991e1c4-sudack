# Career Quest backend contract

## Scope

Go 1.26.1, Echo v4, SQLite/sqlc. The synthetic starter kit comes from ../sudack-ai/docs/data. cmd/migrate creates the schema and imports the four files before the backend starts; the entrypoint runs it on first start. Additional profiles and history in the same format are uploaded by HR through POST /api/v1/imports (this is how the jury's check profiles are loaded), or appended with cmd/migrate -append. The SQLite file survives container restarts in a named volume. Existing employees and history rows are never overwritten.

The backend exposes employee profiles, explanations and recommendations, skill previews, activity completion, grade roadmaps, and HR views. Sudack AI is stateless and receives the employee, next-grade requirements, critical skills, catalog and participation history in each request. AI failures return a structured 503/502 from Go; the AI service itself returns a deterministic fallback when no LLM provider is available.

## Data and progress

The migration keeps all six starter-kit history statuses, critical grade skills, career goals, mandatory events, prerequisites, sessions, and source metadata. Grade order is Junior, Middle, Senior, Lead. The importer uses the source employee skills as the last assessment snapshot and never replays historical completions during import.

Current level = assessment level plus gains from completed history rows dated after last_review_date, in date order. Each event gain is capped at max_level and never lowers a skill. Completion appends one history row; it does not update the assessment snapshot. This matches the Sudack AI contract and prevents double counting. The dataset snapshot date (employees.json meta.as_of_date) is passed as as_of, so recency and future sessions are evaluated consistently; app completions are dated no earlier than as_of.

Target grade comes from career_goal.target_grade when present, otherwise the next grade for the current role. Critical skills are sent to AI; its scoring weights critical gaps 2.5 versus 1.5, and Go's readiness uses the same weights. Mandatory events are never recommendation targets. EV_036 is recurring. Go preview checks audience, prerequisites, sessions, existing progress and positive gain before showing an effect. The AI service applies its own eligibility logic to recommendations and roadmaps.

## Routes

| Route | Access | Backend behavior |
| --- | --- | --- |
| GET /healthz | Public | sqlc SELECT 1 |
| POST /api/v1/auth/demo-token | Public when DEMO_AUTH=true | Body `{"role":"employee"|"hr","employee_id":"E0028"}`; returns a signed 24 h token for the login screen |
| GET /api/v1/employees/:employee_id | Self or HR | Profile: current skills, `gaps` table (skill_id, name, current, required, gap, critical; critical first), `readiness` 0–1 and `readiness_percent`, `applied_progress`, `history` newest first |
| GET /api/v1/employees/:employee_id/recommendations | Self or HR | AI POST /recommend, forwarded as is plus `type`, `format`, `duration_hours`, `upcoming_sessions` on each recommendation. Includes factors, calculation, `rejected`, `source`, `llm_provider` |
| GET /api/v1/employees/:employee_id/roadmap | Self or HR | AI POST /simulate; 409 NO_NEXT_GRADE at the top grade |
| POST /api/v1/employees/:employee_id/events/:event_id/preview | Self or HR | Pure local gain/readiness projection |
| POST /api/v1/employees/:employee_id/events/:event_id/completions | Self | Transactional history write, Idempotency-Key required; replays return `replayed: true` |
| GET /api/v1/hr/employees | HR | IDs for profile selection |
| GET /api/v1/hr/overview | HR | AI POST /score/batch (catalog sent once) plus SQL participation counts, in the frontend shape below |
| POST /api/v1/hr/events/impact | HR | AI POST /events/impact for a draft event body (compact or starter-kit shape) |
| POST /api/v1/imports | HR | multipart/form-data with `employees` (employees.json) and/or `history` (activity_history.csv); returns `imported` and `unchanged` counts; 422 with the offending row on invalid data |

HR overview fields: `employee_count`, `event_count`, `employees_scored`, `weak_skills[]` (skill_id, name, employee_count, missing_levels; sorted by employee_count), `no_recommendation[]` (employee_id, full_name, role, grade, reason), `participation[]` (event_id, title, completed, skipped = no_show+dropped+overdue, declined, in_progress, completion_rate; lowest completion first), `risks[]` (employee_id, full_name, role, grade, readiness, participation, risk; medium and high only, highest score first), `ai` (true when the AI batch ran). It is private to HR; there is no public performance ranking.

## Security and errors

Except /healthz and the demo-token endpoint, routes require a signed HS256 bearer token with subject and role=employee|hr. Employee subjects can see and change only their own records. HR can read profiles and HR views, upload data and estimate events, but cannot mark an employee activity completed. Tokens come from the demo login (DEMO_AUTH=true) or cmd/token, both signed with AUTH_SECRET. Set DEMO_AUTH=false and a private AUTH_SECRET outside the local demo.

Errors use internal/domain/errs/errors.go: JSON contains code and message, while HTTPCode controls the status and is omitted from JSON. Internal SQL and AI errors are logged and not exposed as 500 response text. The AI client timeout is 12 s, above the AI service's 9 s LLM budget, so a slow but valid explanation is not cut off.

## Run

From the repository root, `docker compose up --build` starts the AI service, this API and the frontend (see ../README.md). From backend alone:

    docker compose up --build

For direct local use:

    go run ./cmd/migrate -db .local/db/test.db -data ../sudack-ai/docs/data
    go run ./cmd

Tests (`go test ./...`) initialize a temporary SQLite from the starter kit, run against a fake AI, and cover the profile shape, recommendation enrichment, the HR overview, the jury import (including idempotent re-upload) and idempotent completion.
