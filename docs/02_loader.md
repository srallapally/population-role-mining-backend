# Implementation — data/loader.py

## Purpose

`loader.py` reads the three CSV files into memory and exposes them to the rest of the application through accessor functions. It is called once at startup and the DataFrames remain in memory for the lifetime of the server.

## What It Does

`load_all()` reads `identities.csv`, `entitlements.csv`, and `assignments.csv` using pandas. All columns are read as strings (`dtype=str`) to avoid type inference issues — numeric IDs that look like integers should remain strings throughout the pipeline. Empty cells are replaced with empty strings (`.fillna("")`).

The four public functions are:

| Function | Returns |
|---|---|
| `load_all()` | Loads all three DataFrames into module-level globals |
| `get_identities()` | The identities DataFrame |
| `get_entitlements()` | The entitlements DataFrame |
| `get_assignments()` | The assignments DataFrame |
| `get_filter_columns()` | List of column names from identities, excluding `usr_id` |

## A Critical Implementation Detail

`loader.py` imports `config` as a module — not individual values from it:

```python
# Correct
import config

def load_all():
    _identities = pd.read_csv(config.IDENTITIES_FILE, ...)
```

```python
# Wrong — breaks test monkeypatching
from config.config import IDENTITIES_FILE

def load_all():
    _identities = pd.read_csv(IDENTITIES_FILE, ...)
```

The difference matters for testing. When tests use `monkeypatch.setattr(config, "IDENTITIES_FILE", "/path/to/fixture")`, they are modifying the `config` module object. If `loader.py` has already copied `IDENTITIES_FILE` into its own namespace (the "wrong" pattern), the monkeypatch has no effect — `loader.py` uses its local copy, not the patched value.

By referencing `config.IDENTITIES_FILE` at call time (inside `load_all()`), the loader always reads the current value from the config module, which the test has already patched by the time `load_all()` is called.

## Encoding

Real-world CSV exports from HR and identity systems are often encoded in Windows-1252 (also called latin-1), not UTF-8. Windows-1252 includes characters like curly apostrophes (`'` = byte `0x92`) that are invalid UTF-8. Attempting to read such a file with `encoding="utf-8"` raises a `UnicodeDecodeError`.

The encoding is configurable via `config.CSV_ENCODING` (default `utf-8`). For production data exports from Windows systems, set `CSV_ENCODING=latin-1`.

Test fixtures are plain UTF-8, so tests run with the default encoding without any special setup.
