#!/bin/sh
set -eu

db_path=/app/.local/db/test.db
schema_path=/app/backend/internal/migrations/1_init.sql
version=$(sqlite3 "$db_path" 'PRAGMA user_version;')

case "$version" in
    0)
        sqlite3 -bail "$db_path" <<SQL
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;
.read $schema_path
PRAGMA user_version = 1;
COMMIT;
SQL
        ;;
    1)
        ;;
    *)
        echo "unsupported SQLite schema version: $version" >&2
        exit 1
        ;;
esac

exec /app/backend/careerquest
