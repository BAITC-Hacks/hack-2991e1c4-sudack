#!/bin/sh
set -eu

/app/backend/careerquest-migrate -db "$DB_PATH" -data "$DATA_DIR"
exec /app/backend/careerquest
