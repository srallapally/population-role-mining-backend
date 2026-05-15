# Implementation — config/config.py

## Purpose

`config.py` is the single source of truth for all configurable values. Every default threshold, file path, and server setting lives here. Nothing is hardcoded elsewhere in the application — all other modules import from `config`.

## Package Structure

`config/` is a Python package rather than a single file. `config/__init__.py` re-exports everything from `config/config.py` using `from config.config import *`. This means any module can write `import config` and access `config.MAX_POPULATION` regardless of whether `config` is a file or a package.

## Environment Variables

Every value in `config.py` can be overridden via environment variable. The pattern is consistent throughout:

```python
MAX_POPULATION = int(os.environ.get("MAX_POPULATION", 10000))
```

If the environment variable is not set, the default is used. This means the server works out of the box with no configuration, and can be tuned for a specific environment by setting variables before startup.

## Configuration Reference

### File Paths

| Variable | Default | Description |
|---|---|---|
| `CSV_DIR` | `./data` | Directory containing the three CSV files |
| `IDENTITIES_FILE` | `{CSV_DIR}/identities.csv` | Path to the identities CSV |
| `IDENTITY_PK_COLUMN` | `usr_id` | Primary-key column in `identities.csv` |
| `ENTITLEMENTS_FILE` | `{CSV_DIR}/entitlements.csv` | Path to the entitlements CSV |
| `ASSIGNMENTS_FILE` | `{CSV_DIR}/assignments.csv` | Path to the assignments CSV |
| `ASSIGNMENT_USER_COLUMN` | `user_id` | User foreign-key column in `assignments.csv` |
| `CSV_ENCODING` | `utf-8` | File encoding. Set to `latin-1` for Windows-1252 encoded files. |

### Server

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Port the server listens on |
| `MAX_POPULATION` | `10000` | Hard cap on session population size |
| `MAX_CONCURRENT_SESSIONS` | `5` | Maximum sessions in `running` or `cancelling` status at any time |
| `MAX_ACTIVE_SESSIONS` | `5` | Maximum sessions in `pending`, `running`, or `cancelling` status at any time |
| `MAX_TOTAL_SESSIONS` | `1000` | Maximum retained sessions, regardless of status |
| `ALGORITHM_VERSION` | `2026-05-15-001` | Version tag captured in each session's `launchConfig` |

### Pipeline Defaults

These are the values used when the analyst does not supply a parameter in the session creation request.

| Variable | Default | Corresponding parameter |
|---|---|---|
| `DEFAULT_UNIVERSAL_THRESHOLD` | `0.90` | `universalThreshold` |
| `DEFAULT_COVERAGE_THRESHOLD` | `0.80` | `coverageThreshold` |
| `DEFAULT_SOFT_THRESHOLD` | `0.50` | `softThreshold` |
| `DEFAULT_SIMILARITY_THRESHOLD` | `0.30` | `similarityThreshold` |
| `DEFAULT_MIN_GROUP_SIZE` | `30` | `minGroupSize` |
| `DEFAULT_MAX_ROLES` | `25` | `maxRoles` |
| `DEFAULT_OUTLIER_THRESHOLD` | `0.30` | `outlierThreshold` |
| `DEFAULT_BIRTHRIGHT_COOCCURRENCE_THRESHOLD` | `0.95` | `birthrightCooccurrenceThreshold` |

## Running with Real Data

```bash
export CSV_DIR=/path/to/your/data
export CSV_ENCODING=latin-1
python main.py
```

## Running Tests

Tests use `conftest.py` to monkeypatch `config.IDENTITIES_FILE`, `config.ENTITLEMENTS_FILE`, and `config.ASSIGNMENTS_FILE` to point at the small fixture CSVs in `tests/fixtures/`. The monkeypatching works because `data/loader.py` reads `config.IDENTITIES_FILE` at call time inside `load_all()` — not at import time. See `04_implementation/02_loader.md` for why this matters.
