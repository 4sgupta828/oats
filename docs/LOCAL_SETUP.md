# OATS Local Development Setup

This guide helps you run OATS backend and frontend locally with the new event-driven architecture (SSE + PostgreSQL).

## Prerequisites

1. **PostgreSQL** installed and running locally
2. **Python virtual environment** set up in `./venv`
3. **Node.js and npm** for the UI

## Quick Start

### 1. Set up PostgreSQL

Make sure PostgreSQL is running locally:

```bash
# Start PostgreSQL (if not running)
brew services start postgresql@14  # macOS with Homebrew
# OR
pg_ctl -D /usr/local/var/postgres start
```

Create the OATS database (if it doesn't exist):

```bash
createdb oats
```

### 2. Configure Environment Variables

The `.env` file should already contain:

```bash
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
DATABASE_URL=postgresql://your_username@localhost:5432/oats
```

**Note:** The `run_all.py` script will automatically use your current username for the database connection. Adjust `DATABASE_URL` in `.env` if your PostgreSQL setup differs.

### 3. Run All Services

Simply run:

```bash
python run_all.py
```

This script will:
1. **Clean up ports 8000 and 3000** (kills any existing processes)
2. Load environment variables from `.env`
3. Initialize the PostgreSQL database schema (if needed)
4. Start the Backend API on `http://localhost:8000`
5. Start the UI on `http://localhost:3000`

**Note:** The script automatically stops any existing services on ports 8000 and 3000 before starting new ones.

### 4. Access the Application

- **UI:** http://localhost:3000
- **API:** http://localhost:8000
- **API Health:** http://localhost:8000/health
- **API Docs:** http://localhost:8000/docs

## Architecture Changes

The recent refactoring introduced:

- **Event-Driven Architecture:** All agent events are stored in PostgreSQL
- **Server-Sent Events (SSE):** Real-time streaming from backend to UI
- **No WebSockets:** SSE replaced WebSocket transport for simplicity
- **PostgreSQL Event Store:** Persistent event storage and retrieval

## Troubleshooting

### Database Connection Errors

If you see `DATABASE_URL not configured`:

1. Check PostgreSQL is running: `psql -U postgres -c "SELECT 1"`
2. Verify database exists: `psql -U postgres -l | grep oats`
3. Check `.env` has correct `DATABASE_URL`

### Backend Won't Start

If the backend fails with import errors:

```bash
# Reinstall dependencies
source venv/bin/activate
pip install -r services/backend-api/requirements.txt
pip install -r services/agent/requirements.txt

# Make sure sse-starlette is installed (required for SSE streaming)
pip install sse-starlette
```

### UI Won't Start

If the UI fails to start:

```bash
cd services/ui
npm install
npm start
```

## Manual Setup (Alternative)

If `run_all.py` doesn't work for you:

### 1. Initialize Database

```bash
export DATABASE_URL="postgresql://$(whoami)@localhost:5432/oats"
source venv/bin/activate
python services/backend-api/database/init_db.py
```

### 2. Start Backend

```bash
export DATABASE_URL="postgresql://$(whoami)@localhost:5432/oats"
export PYTHONPATH="$(pwd)/services/agent:$(pwd)/services/backend-api"
source venv/bin/activate
cd services/backend-api
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Start UI (in another terminal)

```bash
cd services/ui
npm start
```

## Development Notes

- **Hot Reload:** Currently disabled on backend to prevent SSE disconnections
- **Database Schema:** Located in `services/backend-api/database/schema.sql`
- **Event Store:** Implemented in `services/backend-api/database/event_store.py`

## Recent Commits

- `e0e98e2` - Use sync in DB init
- `2c09963` - Updated to use sync, add some missing events
- `1ca1141` - Remove WebSocket code and make SSE the only transport
- `09953f7` - Implement clean event-driven architecture with SSE and PostgreSQL
