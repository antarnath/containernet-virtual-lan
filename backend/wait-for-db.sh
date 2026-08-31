#!/usr/bin/env bash
# Wait until postgres is ready, then exec the given command.
# Usage: wait-for-db.sh <db-host> <command...>

set -e

DB_HOST="${1:-db}"
shift

echo "[wait-for-db] waiting for ${DB_HOST}:5432 ..."

for i in $(seq 1 60); do
  if pg_isready -h "${DB_HOST}" -p 5432 -U postgres >/dev/null 2>&1; then
    echo "[wait-for-db] postgres is ready after ${i}s"
    exec "$@"
  fi
  sleep 1
done

echo "[wait-for-db] ERROR: postgres not ready after 60s"
exit 1