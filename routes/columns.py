# backend/routes/columns.py
from fastapi import APIRouter
from data.loader import get_filter_columns

router = APIRouter()


@router.get("/columns")
def list_columns():
    return {"columns": get_filter_columns()}