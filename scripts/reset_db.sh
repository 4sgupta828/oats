#!/usr/bin/env bash

set -euo pipefail

# Simple reset script: drop and recreate the 'oats' database, then initialize schema
# Usage:
#   bash scripts/reset_db.sh
# Optional env:
#   DATABASE_URL=postgresql://user[:pass]@host:port/oats
#   DB_NAME=oats                 # defaults to 'oats'
#   PSQL_DB=postgres            # control the maintenance DB for DROP (defaults to 'postgres')
#   PYTHON_BIN="venv/bin/python"  # use project venv if present; otherwise falls back to 'python'

echo "[reset_db] Starting database reset..."

DB_NAME="${DB_NAME:-oats}"
PSQL_DB="${PSQL_DB:-postgres}"

# Choose python interpreter
if [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
  PYTHON_CMD="$PYTHON_BIN"
elif [[ -x "venv/bin/python" ]]; then
  PYTHON_CMD="venv/bin/python"
else
  PYTHON_CMD="python3"
fi

# Verify psql exists
if ! command -v psql >/dev/null 2>&1; then
  echo "[reset_db] ERROR: psql not found. Please install PostgreSQL client tools." >&2
  exit 1
fi

# Drop and recreate database
echo "[reset_db] Dropping database '$DB_NAME' (if exists)..."
psql -d "$PSQL_DB" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$DB_NAME\" WITH (FORCE);"

echo "[reset_db] Creating database '$DB_NAME'..."
createdb "$DB_NAME"

# Initialize schema
echo "[reset_db] Initializing schema..."
if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "[reset_db] Using DATABASE_URL=$DATABASE_URL"
  DATABASE_URL="$DATABASE_URL" "$PYTHON_CMD" services/backend-api/database/init_db.py
else
  # Default to local user/no password
  DEFAULT_URL="postgresql://$(whoami)@localhost:5432/$DB_NAME"
  echo "[reset_db] Using default DATABASE_URL=$DEFAULT_URL"
  DATABASE_URL="$DEFAULT_URL" "$PYTHON_CMD" services/backend-api/database/init_db.py
fi

echo "[reset_db] ✅ Reset complete."


