# backend/data/loader.py
import pandas as pd
import config

_identities: pd.DataFrame = None
_entitlements: pd.DataFrame = None
_assignments: pd.DataFrame = None


def load_all() -> None:
    global _identities, _entitlements, _assignments
    _identities = pd.read_csv(config.IDENTITIES_FILE, dtype=str, encoding=config.CSV_ENCODING).fillna("")
    _entitlements = pd.read_csv(config.ENTITLEMENTS_FILE, dtype=str, encoding=config.CSV_ENCODING).fillna("")
    _assignments = pd.read_csv(config.ASSIGNMENTS_FILE, dtype=str, encoding=config.CSV_ENCODING).fillna("")

def get_identities() -> pd.DataFrame:
    return _identities


def get_entitlements() -> pd.DataFrame:
    return _entitlements


def get_assignments() -> pd.DataFrame:
    return _assignments


def get_filter_columns() -> list[str]:
    """Returns identity columns usable as filter criteria keys.
    Excludes the primary key column (usr_id)."""
    return [c for c in _identities.columns if c != config.IDENTITY_PK_COLUMN]