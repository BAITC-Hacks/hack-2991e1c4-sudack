-- Career Quest, SQLite. Apply once to a new database with PRAGMA foreign_keys=ON.
-- Imported employee skills are the current snapshot; history is not replayed.

CREATE TABLE employees (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    grade TEXT NOT NULL,
    tenure_months INTEGER NOT NULL CHECK (tenure_months >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE skills (
    id TEXT PRIMARY KEY,
    name_en TEXT NOT NULL,
    name_ru TEXT,
    name_kk TEXT,
    category TEXT NOT NULL CHECK (category IN ('hard', 'soft'))
);

-- Rank is provided by the import adapter; never infer it from alphabetical order.
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
    type TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

-- Empty audience table for a dimension means unrestricted for that dimension.
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

CREATE TABLE activity_history (
    id INTEGER PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES events(id),
    occurred_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'skipped', 'declined')),
    source TEXT NOT NULL CHECK (source IN ('import', 'app')),
    source_key TEXT UNIQUE,
    idempotency_key TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((source = 'import' AND source_key IS NOT NULL AND idempotency_key IS NULL)
        OR (source = 'app' AND source_key IS NULL AND idempotency_key IS NOT NULL)),
    UNIQUE (employee_id, idempotency_key)
);

-- Imported history may contain repeated occurrences. App completions cannot repeat.
CREATE UNIQUE INDEX ux_app_completion ON activity_history(employee_id, event_id)
    WHERE source = 'app' AND status = 'completed';
CREATE INDEX ix_history_employee_date ON activity_history(employee_id, occurred_at DESC);
CREATE INDEX ix_history_event_status ON activity_history(event_id, status);
CREATE INDEX ix_requirements_skill ON grade_requirements(skill_id, role, grade);
CREATE INDEX ix_effects_skill ON event_skill_effects(skill_id);
