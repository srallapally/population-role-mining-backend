# backend/routes/columns.py
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import config
from data.loader import get_filter_columns, get_identities

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /columns
# ---------------------------------------------------------------------------

@router.get("/columns")
def list_columns():
    return {"columns": get_filter_columns()}


# ---------------------------------------------------------------------------
# GET /columns/{column}/values  — type-ahead
# ---------------------------------------------------------------------------

@router.get("/columns/{column}/values")
def get_column_values(
    column: str,
    q: str = Query(default="", description="Prefix to match, case-insensitive"),
    limit: int = Query(default=20, le=100),
):
    """Return distinct values for a filter column matching a prefix.

    Used by the filter builder for type-ahead suggestions. Returns up to
    `limit` values sorted alphabetically. An empty `q` returns the first
    `limit` distinct values (useful for initial dropdown population).
    """
    valid_columns = set(get_filter_columns())
    if column not in valid_columns:
        raise HTTPException(status_code=400, detail=f"Invalid column: '{column}'")

    df = get_identities()
    series = df[column].dropna()

    if q:
        q_lower = q.lower()
        series = series[series.str.lower().str.startswith(q_lower)]

    values = sorted(series.unique().tolist())[:limit]
    return {"column": column, "values": values}


# ---------------------------------------------------------------------------
# POST /preview  — population preview
# ---------------------------------------------------------------------------

class PreviewRequest(BaseModel):
    filterCriteria: dict
    page: Optional[int] = 1      # 1-based
    pageSize: Optional[int] = 10


@router.post("/preview")
def preview_population(req: PreviewRequest):
    """Apply filter criteria and return matched identities paginated.

    Returns all identity columns. Sorted by the primary key column ascending.
    Page is 1-based. pageSize capped at 100.
    """
    if not req.filterCriteria:
        raise HTTPException(status_code=400, detail="filterCriteria must be non-empty")

    valid_columns = set(get_filter_columns())
    for key in req.filterCriteria:
        if key not in valid_columns:
            raise HTTPException(status_code=400, detail=f"Invalid filter key: '{key}'")

    page_size = min(req.pageSize or 10, 100)
    page = max(req.page or 1, 1)

    df = get_identities()

    import pandas as pd
    mask = pd.Series([True] * len(df), index=df.index)
    for col, val in req.filterCriteria.items():
        if isinstance(val, list):
            mask &= df[col].isin(val)
        else:
            mask &= df[col] == val

    matched = df[mask].sort_values(config.IDENTITY_PK_COLUMN)
    total = len(matched)

    from_idx = (page - 1) * page_size
    page_rows = matched.iloc[from_idx: from_idx + page_size]

    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": (total + page_size - 1) // page_size if total > 0 else 0,
        "identities": page_rows.to_dict(orient="records"),
    }