-- Career Quest SQLite schema. Imported skills are the assessment snapshot.
CREATE TABLE dataset_metadata (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL CHECK (json_valid(value_json))
);

CREATE TABLE employees (
    id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    department TEXT NOT NULL,
    role TEXT NOT NULL,
    grade TEXT NOT NULL,
    manager_id TEXT,
    hire_date TEXT NOT NULL,
    tenure_months INTEGER NOT NULL CHECK (tenure_months >= 0),
    work_format TEXT NOT NULL,
    preferred_language TEXT NOT NULL,
    career_goal_role TEXT,
    career_goal_grade TEXT,
    last_review_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE skills (
    id TEXT PRIMARY KEY,
    name_en TEXT NOT NULL,
    name_ru TEXT,
    name_kk TEXT,
    category TEXT NOT NULL CHECK (category IN ('hard', 'soft')),
    category_detail TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE grade_levels (
    role TEXT NOT NULL,
    grade TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK (rank >= 0),
    PRIMARY KEY (role, grade),
    UNIQUE (role, rank)
);

CREATE TABLE grade_requirements (
    role TEXT NOT NULL,
    grade TEXT NOT NULL,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    required_level INTEGER NOT NULL CHECK (required_level BETWEEN 0 AND 5),
    critical INTEGER NOT NULL DEFAULT 0 CHECK (critical IN (0, 1)),
    PRIMARY KEY (role, grade, skill_id),
    FOREIGN KEY (role, grade) REFERENCES grade_levels(role, grade)
);

CREATE TABLE employee_skills (
    employee_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    level INTEGER NOT NULL CHECK (level BETWEEN 0 AND 5),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (employee_id, skill_id)
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    title_en TEXT NOT NULL,
    title_ru TEXT,
    title_kk TEXT,
    description TEXT NOT NULL,
    type TEXT NOT NULL,
    format TEXT NOT NULL,
    duration_hours REAL NOT NULL CHECK (duration_hours >= 0),
    mandatory INTEGER NOT NULL CHECK (mandatory IN (0, 1)),
    upcoming_sessions_json TEXT NOT NULL CHECK (json_valid(upcoming_sessions_json)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE event_audience_roles (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    PRIMARY KEY (event_id, role)
);

CREATE TABLE event_audience_grades (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    grade TEXT NOT NULL,
    PRIMARY KEY (event_id, grade)
);

CREATE TABLE event_skill_effects (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    gain INTEGER NOT NULL CHECK (gain > 0 AND gain <= 5),
    max_level INTEGER NOT NULL CHECK (max_level BETWEEN 0 AND 5),
    PRIMARY KEY (event_id, skill_id)
);

CREATE TABLE event_prerequisites (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    required_level INTEGER NOT NULL CHECK (required_level BETWEEN 0 AND 5),
    PRIMARY KEY (event_id, skill_id)
);

CREATE TABLE activity_history (
    id INTEGER PRIMARY KEY,
    record_id TEXT UNIQUE,
    employee_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES events(id),
    occurred_at TEXT NOT NULL,
    due_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('completed', 'in_progress', 'dropped', 'no_show', 'declined', 'overdue')),
    completion_pct INTEGER NOT NULL CHECK (completion_pct BETWEEN 0 AND 100),
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    feedback_rating INTEGER CHECK (feedback_rating BETWEEN 1 AND 5),
    assigned_by TEXT NOT NULL CHECK (assigned_by IN ('self', 'manager', 'hr', 'app')),
    source TEXT NOT NULL CHECK (source IN ('import', 'app')),
    source_key TEXT UNIQUE,
    idempotency_key TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((source = 'import' AND record_id IS NOT NULL AND source_key IS NOT NULL AND idempotency_key IS NULL)
        OR (source = 'app' AND record_id IS NULL AND source_key IS NULL AND idempotency_key IS NOT NULL)),
    UNIQUE (employee_id, idempotency_key)
);

CREATE UNIQUE INDEX ux_app_completion ON activity_history(employee_id, event_id)
    WHERE source = 'app' AND status = 'completed' AND event_id != 'EV_036';
CREATE INDEX ix_history_employee_date ON activity_history(employee_id, occurred_at DESC);
CREATE INDEX ix_history_event_status ON activity_history(event_id, status);
CREATE INDEX ix_requirements_skill ON grade_requirements(skill_id, role, grade);
CREATE INDEX ix_effects_skill ON event_skill_effects(skill_id);
