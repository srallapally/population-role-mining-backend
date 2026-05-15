# backend/pipeline/build_sparse_matrix.py
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

import config
from data.loader import get_assignments

import config.config

def build_sparse_matrix(
    population_ids: list[str], noise_filter_value: int
) -> tuple[csr_matrix, dict[str, int], int]:
    """
    Build a binary CSR matrix (users x entitlements) from assignments.

    Rows: population_ids sorted lexicographically (already sorted by filter_population).
    Columns: entitlement IDs sorted lexicographically.
    Noise filter: drop entitlements held by fewer than noise_filter_value users.

    Returns: (matrix, entitlement_index, dropped_count)
    entitlement_index: {ent_id -> column_index}
    """
    assignments = get_assignments()

    # Restrict to population
    pop_set = set(population_ids)
    user_column = config.ASSIGNMENT_USER_COLUMN
    relevant = assignments[assignments[user_column].isin(pop_set)]

    # Count holders per entitlement
    holder_counts = relevant.groupby("ent_id")[user_column].nunique()
    surviving_ents = sorted(holder_counts[holder_counts >= noise_filter_value].index.tolist())
    dropped_count = int((holder_counts < noise_filter_value).sum())

    entitlement_index = {ent_id: idx for idx, ent_id in enumerate(surviving_ents)}
    user_index = {uid: idx for idx, uid in enumerate(population_ids)}

    # Build COO data
    relevant_surviving = relevant[relevant["ent_id"].isin(entitlement_index)]
    rows = relevant_surviving[user_column].map(user_index)
    cols = relevant_surviving["ent_id"].map(entitlement_index)
    data = np.ones(len(rows), dtype=np.float32)

    matrix = csr_matrix(
        (data, (rows, cols)),
        shape=(len(population_ids), len(surviving_ents))
    )
    # Clip to binary (deduplicate duplicate grants)
    matrix.data[:] = 1.0

    return matrix, entitlement_index, dropped_count
