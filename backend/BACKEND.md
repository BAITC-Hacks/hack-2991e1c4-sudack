# Career Quest backend contract

## Scope

Go 1.26.1, Echo v4, SQLite/sqlc. The synthetic dataset comes from ../sudack-ai/docs/data. cmd/migrate creates the schema and imports the four files before the backend starts. There is no HTTP import endpoint. The SQLite file survives container restarts in a named volume. The command does not overwrite an existing database.

The backend exposes employee profiles, explanations and recommendations, skill previews, activity completion, grade roadmaps, and HR views. Sudack AI is stateless and receives the employee, next-grade requirements, critical skills, catalog and participation history in each request. AI failures return a structured 503/502 from Go; the AI service itself returns a deterministic fallback when no LLM provider is available.

## Data and progress

The migration keeps all six starter-kit history statuses, critical grade skills, career goals, mandatory events, prerequisites, sessions, and source metadata. Grade order is Junior, Middle, Senior, Lead. The importer uses the source employee skills as the last assessment snapshot and never replays historical completions during import.

Current level = assessment level plus gains from completed history rows dated after last_review_date, in date order. Each event gain is capped at max_level and never lowers a skill. Completion appends one history row; it does not update the assessment snapshot. This matches the Sudack AI contract and prevents double counting. The dataset snapshot date is passed as as_of, so its historical recency and future sessions are evaluated consistently.

Target grade comes from career_goal.target_grade when present, otherwise the next grade for the current role. Critical skills are sent to AI; its scoring weights critical gaps more strongly. Mandatory events are never recommendation targets. EV_036 is recurring. Go preview checks audience, prerequisites, sessions, existing progress and positive gain before showing an effect. The AI service applies its own eligibility logic to recommendations and roadmaps.

## Routes

| Route | Access | Backend behavior |
| --- | --- | --- |
| GET /healthz | Public | sqlc SELECT 1 |
| GET /api/v1/employees/:employee_id | Self or HR | Current profile, requirements, gaps, weighted readiness and history |
| GET /api/v1/employees/:employee_id/recommendations | Self or HR | AI POST /recommend; returns factors, calculation, rejected alternatives and source |
| GET /api/v1/employees/:employee_id/roadmap | Self or HR | AI POST /simulate |
| POST /api/v1/employees/:employee_id/events/:event_id/preview | Self or HR | Pure local gain/readiness projection |
| POST /api/v1/employees/:employee_id/events/:event_id/completions | Self | Transactional history write, Idempotency-Key required |
| GET /api/v1/hr/employees | HR | IDs for profile selection |
| GET /api/v1/hr/overview | HR | AI POST /score/batch plus SQL participation counts |
| POST /api/v1/hr/events/impact | HR | AI POST /events/impact for a draft event body |

The HR overview aggregates skill gap frequency, missing levels, activity participation by each of the six statuses, employees with no suggested step, and dropout-risk reasons. It is private to HR; there is no public performance ranking.

## Security and errors

Except /healthz, endpoints require a signed HS256 bearer token with subject and role=employee|hr. Employee subjects can see and change only their own records. HR can read profiles and HR views but cannot mark an employee activity completed. cmd/token creates demo tokens using AUTH_SECRET. Configure a non-default AUTH_SECRET for any deployment outside the local demo.

Errors use internal/domain/errs/errors.go: JSON contains code and message, while HTTPCode controls the status and is omitted from JSON. Internal SQL and AI errors are logged and not exposed as 500 response text.

## Run

From backend:

    docker compose up --build

Compose mounts ../sudack-ai/docs/data at /app/data and starts the AI service before Go. DB_PATH defaults to /app/.local/db/test.db in Docker and DATA_DIR to /app/data. AI_URL is http://ai:8001. Without a mounted dataset on first startup, entrypoint identifies the missing file. For direct local use:

    go run ./cmd/migrate -db .local/db/test.db -data ../sudack-ai/docs/data
    go run ./cmd

Generate tokens through cmd/token or in the container. To add extra jury profiles and history after initial startup, use cmd/migrate -append -db <DB_PATH> -data <directory>. That directory needs employees.json and activity_history.csv; existing employee snapshots remain untouched.
