#!/bin/sh
set -eu

if [ ! -f "$DB_PATH" ]; then
    for filename in skills.json events.json employees.json activity_history.csv; do
        if [ ! -r "$DATA_DIR/$filename" ]; then
            echo "missing dataset file: $DATA_DIR/$filename" >&2
            echo "start with: docker compose up --build" >&2
            exit 1
        fi
    done
fi

/app/backend/careerquest-migrate -db "$DB_PATH" -data "$DATA_DIR"
exec /app/backend/careerquest
