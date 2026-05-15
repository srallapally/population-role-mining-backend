# Population Role Mining Backend

FastAPI backend for a role-mining proof of concept. It reads identity and access data from CSV files, lets analysts define a population, and produces:

- **Birthright roles** (near-universal entitlements in that population)
- **Candidate job roles** (communities of users with similar residual access)

The API is designed for asynchronous session-based analysis and currently uses an in-memory store.

## What this service does

- Exposes REST endpoints under `/api/v1`
- Validates analyst-provided filter criteria against identity columns
- Creates and tracks role-mining sessions (`pending` → `running` → terminal state)
- Runs a multi-step pipeline in the background
- Returns discovered roles for completed sessions

## Tech stack

- Python
- FastAPI + Uvicorn
- Pandas / NumPy / SciPy
- igraph + leidenalg for community detection

See exact pinned packages in `requirements.txt`.

## Project layout

```text
.
├── main.py                # FastAPI app entrypoint
├── routes/                # API route handlers
├── pipeline/              # Role-mining pipeline steps + orchestrator
├── data/                  # CSV loader and in-memory store
├── config/                # Configuration defaults/settings
├── tests/                 # Pytest suite
└── docs/                  # Detailed design and API docs
```

## Data inputs

On startup, the backend loads CSV data via `data.loader.load_all()`:

- identities
- entitlements
- assignments

These power dynamic filter columns and session pipeline execution.

## Quick start

### 1) Create and activate a virtual environment (example)

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Run the API

```bash
python main.py
```

By default, Uvicorn starts the app from `main:app` and serves on:

- `http://0.0.0.0:8000`

## Testing

Run all tests:

```bash
pytest
```

Run a specific test module:

```bash
pytest tests/test_api.py
```

## API overview

Base prefix: `/api/v1`

- `GET /columns` — list valid identity fields for filtering
- `POST /sessions` — create a pending role-mining session
- `POST /sessions/{id}/run` — start background pipeline for a session
- `GET /sessions` — list sessions with filtering/pagination
- `GET /sessions/{id}` — fetch session details and output state
- `PATCH /sessions/{id}` — save/cancel session according to allowed transitions
- `POST /sessions/{id}/clone` — clone completed/saved session config
- `GET /sessions/{id}/roles` — list produced roles for that session

For detailed request/response schemas and validation rules, see `docs/03_api.md`.

## Current limitations (POC)

- In-memory state only (no persistent database)
- No authz enforcement beyond analyst header usage on selected endpoints
- Does not decompose a single user into multiple functional roles

## Additional documentation

- `docs/00_overview.md` — domain/problem framing and terminology
- `docs/02_pipeline.md` and `docs/04_pipeline_steps.md` — pipeline details
- `docs/03_api.md` and `docs/05_routes.md` — endpoint behavior
- `docs/06_constraints.md` and `docs/06_approach_rationale.md` — design tradeoffs

