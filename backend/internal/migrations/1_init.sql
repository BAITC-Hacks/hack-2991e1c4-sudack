CREATE TABLE employees
(
    id            TEXT PRIMARY KEY,
    role          TEXT,
    grade         TEXT,
    tenure_months INT,
    skills        JSON -- {"SK_PYTHON":3,...}
);

CREATE TABLE events
(
    id       TEXT PRIMARY KEY,
    title    TEXT,
    type     TEXT,
    audience JSON, -- {"roles":[...],"grades":[...]}
    skills   JSON  -- {"SK_X":{"gain":1,"max_level":4}}
);

CREATE TABLE skills
(
    id           TEXT PRIMARY KEY,
    name_en      TEXT,
    name_ru      TEXT,
    name_kk      TEXT,
    category     TEXT,
    requirements JSON -- {"Backend Engineer":{"Senior":4}} — по факту кита
);

CREATE TABLE history
(
    employee_id TEXT,
    event_id    TEXT,
    date        TEXT,
    status      TEXT -- completed | skipped | declined
);

CREATE TABLE rec_cache
(
    employee_id TEXT PRIMARY KEY,
    payload     JSON,
    created_at  TIMESTAMP
);
