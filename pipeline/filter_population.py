# backend/pipeline/filter_population.py
import pandas as pd

from config import config
from data.loader import get_identities


def filter_population(filter_criteria: dict, max_population: int) -> tuple[list[str], dict]:
    """
    Filter identities by filter_criteria, enforce population cap.

    filter_criteria: {column_name: value | [value, ...]}
    Returns: (population_ids, population_summary)
    Raises: ValueError on zero matches or cap exceeded.
    """
    df = get_identities()

    mask = pd.Series([True] * len(df), index=df.index)
    for col, val in filter_criteria.items():
        if isinstance(val, list):
            mask &= df[col].isin(val)
        else:
            mask &= df[col] == val

    matched = df[mask]
    count = len(matched)

    if count == 0:
        raise ValueError(f"Population filter matched 0 users. Check filter criteria: {filter_criteria}")

    if count > max_population:
        raise ValueError(
            f"Population filter matched {count} users, exceeding cap of {max_population}. "
            "Narrow the filter criteria."
        )

    population_ids = sorted(matched[config.IDENTITY_PK_COLUMN].tolist())

    filter_description = " AND ".join(
        f"{k} IN {v}" if isinstance(v, list) else f"{k} = {v}"
        for k, v in filter_criteria.items()
    )
    population_summary = {
        "count": count,
        "filterDescription": filter_description,
        "filterCriteria": filter_criteria,
    }

    return population_ids, population_summary