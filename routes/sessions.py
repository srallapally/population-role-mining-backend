# backend/routes/sessions.py
from copy import deepcopy
import threading
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, field_validator, model_validator

import config
from data import store
from data.loader import get_filter_columns
from pipeline.orchestrator import run_pipeline

router = APIRouter()

REJECTED_PARAMS = {"noiseFilter", "noiseFilterValue", "noiseFilterFormula", "maxPopulation"}


class SessionCreateRequest(BaseModel):
    filterCriteria: dict
    roleType: Literal["birthright", "job_roles"]  # required, no default
    universalThreshold: Optional[float] = None
    coverageThreshold: Optional[float] = None
    softThreshold: Optional[float] = None
    similarityThreshold: Optional[float] = None
    minGroupSize: Optional[int] = None
    maxRoles: Optional[int] = None
    outlierThreshold: Optional[float] = None
    birthrightCooccurrenceThreshold: Optional[float] = None

    @field_validator("universalThreshold", "coverageThreshold", "softThreshold",
                     "similarityThreshold", "birthrightCooccurrenceThreshold",
                     "outlierThreshold")
    @classmethod
    def must_be_unit_interval(cls, v):
        if v is not None and not (0.0 < v <= 1.0):
            raise ValueError("must be in (0.0, 1.0]")
        return v

    @field_validator("minGroupSize")
    @classmethod
    def min_group_size_positive(cls, v):
        if v is not None and v < 1:
            raise ValueError("must be >= 1")
        return v

    @field_validator("maxRoles")
    @classmethod
    def max_roles_positive(cls, v):
        if v is not None and v < 1:
            raise ValueError("must be >= 1")
        return v

    @model_validator(mode="after")
    def cross_field_checks(self):
        ct = self.coverageThreshold
        st = self.softThreshold
        ut = self.universalThreshold

        if st is not None and ct is not None and st >= ct:
            raise ValueError("softThreshold must be less than coverageThreshold")
        if ct is not None and ut is not None and ct >= ut:
            raise ValueError("coverageThreshold must be less than universalThreshold")
        if st is not None and ut is not None and st >= ut:
            raise ValueError("softThreshold must be less than universalThreshold")
        return self


class SessionPatchRequest(BaseModel):
    status: Optional[str] = None
    lastUpdatedBy: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_params(req: SessionCreateRequest) -> dict:
    coverage = req.coverageThreshold if req.coverageThreshold is not None else config.DEFAULT_COVERAGE_THRESHOLD
    min_group = req.minGroupSize if req.minGroupSize is not None else config.DEFAULT_MIN_GROUP_SIZE
    noise_filter_value = max(2, int(min_group * coverage) - 1)

    return {
        "filterCriteria": req.filterCriteria,
        "universalThreshold": req.universalThreshold if req.universalThreshold is not None else config.DEFAULT_UNIVERSAL_THRESHOLD,
        "coverageThreshold": coverage,
        "softThreshold": req.softThreshold if req.softThreshold is not None else config.DEFAULT_SOFT_THRESHOLD,
        "similarityThreshold": req.similarityThreshold if req.similarityThreshold is not None else config.DEFAULT_SIMILARITY_THRESHOLD,
        "minGroupSize": min_group,
        "maxRoles": req.maxRoles if req.maxRoles is not None else config.DEFAULT_MAX_ROLES,
        "outlierThreshold": req.outlierThreshold if req.outlierThreshold is not None else config.DEFAULT_OUTLIER_THRESHOLD,
        "birthrightCooccurrenceThreshold": (
            req.birthrightCooccurrenceThreshold
            if req.birthrightCooccurrenceThreshold is not None
            else config.DEFAULT_BIRTHRIGHT_COOCCURRENCE_THRESHOLD
        ),
        "maxPopulation": config.MAX_POPULATION,
        "noiseFilterValue": noise_filter_value,
        "noiseFilterFormula": f"max(2, floor({min_group} * {coverage}) - 1)",
        "roleType": req.roleType,
    }


def _build_launch_config(params: dict) -> dict:
    return {
        "filterCriteria": deepcopy(params["filterCriteria"]),
        "roleType": params["roleType"],
        "thresholds": {
            "universalThreshold": params["universalThreshold"],
            "coverageThreshold": params["coverageThreshold"],
            "softThreshold": params["softThreshold"],
            "similarityThreshold": params["similarityThreshold"],
            "birthrightCooccurrenceThreshold": params["birthrightCooccurrenceThreshold"],
            "outlierThreshold": params["outlierThreshold"],
        },
        "limits": {
            "maxPopulation": params["maxPopulation"],
            "minGroupSize": params["minGroupSize"],
            "maxRoles": params["maxRoles"],
            "noiseFilterValue": params["noiseFilterValue"],
            "noiseFilterFormula": params["noiseFilterFormula"],
        },
        "dataConfig": {
            "csvDir": config.CSV_DIR,
            "csvEncoding": config.CSV_ENCODING,
            "identityPkColumn": config.IDENTITY_PK_COLUMN,
            "assignmentUserColumn": config.ASSIGNMENT_USER_COLUMN,
        },
        "algorithmVersion": config.ALGORITHM_VERSION,
    }


def _params_from_launch_config(launch_config: dict) -> dict:
    thresholds = launch_config["thresholds"]
    limits = launch_config["limits"]
    return {
        "filterCriteria": deepcopy(launch_config["filterCriteria"]),
        "roleType": launch_config["roleType"],
        "universalThreshold": thresholds["universalThreshold"],
        "coverageThreshold": thresholds["coverageThreshold"],
        "softThreshold": thresholds["softThreshold"],
        "similarityThreshold": thresholds["similarityThreshold"],
        "birthrightCooccurrenceThreshold": thresholds["birthrightCooccurrenceThreshold"],
        "outlierThreshold": thresholds["outlierThreshold"],
        "maxPopulation": limits["maxPopulation"],
        "minGroupSize": limits["minGroupSize"],
        "maxRoles": limits["maxRoles"],
        "noiseFilterValue": limits["noiseFilterValue"],
        "noiseFilterFormula": limits["noiseFilterFormula"],
    }


def _build_pending_session(session_id: str, owner: str, now: str, params: dict) -> dict:
    return {
        "id": session_id,
        "status": "pending",
        "sessionOwner": owner,
        "createdAt": now,
        "updatedAt": now,
        "parameters": params,
        "launchConfig": _build_launch_config(params),
        "cleanupStatus": None,
        "resolvedUniversalThreshold": params["universalThreshold"],
        "resolvedCoverageThreshold": params["coverageThreshold"],
        "resolvedSoftThreshold": params["softThreshold"],
        "resolvedSimilarityThreshold": params["similarityThreshold"],
        "resolvedMinGroupSize": params["minGroupSize"],
        "resolvedMaxRoles": params["maxRoles"],
        "resolvedOutlierThreshold": params["outlierThreshold"],
        "resolvedBirthrightCooccurrenceThreshold": params["birthrightCooccurrenceThreshold"],
        "resolvedNoiseFilterValue": params["noiseFilterValue"],
    }


def _put_new_session_or_raise(session: dict) -> None:
    limit_error = store.try_put_session_with_limits(
        session, config.MAX_ACTIVE_SESSIONS, config.MAX_TOTAL_SESSIONS
    )
    if limit_error == "active":
        raise HTTPException(
            status_code=429,
            detail={
                "error": (
                    f"Maximum active sessions ({config.MAX_ACTIVE_SESSIONS}) reached. "
                    "Complete or save an existing session before creating another."
                ),
                "retryAfter": 30,
            },
        )
    if limit_error == "total":
        raise HTTPException(
            status_code=429,
            detail={
                "error": (
                    f"Maximum total sessions ({config.MAX_TOTAL_SESSIONS}) reached. "
                    "Clean up old sessions before creating another."
                ),
                "retryAfter": 30,
            },
        )

async def _reject_system_params(request: Request) -> None:
    try:
        body = await request.json()
    except Exception:
        return
    for key in REJECTED_PARAMS:
        if key in body:
            raise HTTPException(status_code=400, detail=f"Parameter '{key}' is not accepted")

@router.post("/sessions", status_code=201)
async def create_session(
    req: SessionCreateRequest,
    x_analyst_id: str = Header(default=""),
    _: None = Depends(_reject_system_params),
):
    if not x_analyst_id:
        raise HTTPException(status_code=400, detail="Missing X-Analyst-Id header")

    # Validate filterCriteria
    if not req.filterCriteria:
        raise HTTPException(status_code=400, detail="filterCriteria must be non-empty")

    valid_columns = set(get_filter_columns())
    for key in req.filterCriteria:
        if key not in valid_columns:
            raise HTTPException(status_code=400, detail=f"Invalid filter key: '{key}'")

    session_id = str(uuid.uuid4())
    now = _now()
    params = _resolve_params(req)

    session = _build_pending_session(session_id, x_analyst_id, now, params)
    _put_new_session_or_raise(session)

    return {"sessionId": session_id, "status": "pending", "createdAt": now}


@router.post("/sessions/{session_id}/run", status_code=202)
def run_session(session_id: str, x_analyst_id: str = Header(default="")):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail={"sessionId": session_id, "status": session["status"],
                    "error": "Session is not in pending state."}
        )
    if store.count_running_sessions() >= config.MAX_CONCURRENT_SESSIONS:
        raise HTTPException(
            status_code=429,
            detail={"error": f"Maximum concurrent sessions ({config.MAX_CONCURRENT_SESSIONS}) reached. Retry later.",
                    "retryAfter": 30}
        )

    session = store.transition_pending_to_running(session_id, _now())
    if not session:
        latest = store.get_session(session_id)
        raise HTTPException(
            status_code=409,
            detail={"sessionId": session_id, "status": latest.get("status") if latest else None,
                    "error": "Session is not in pending state."}
        )

    threading.Thread(target=run_pipeline, args=(session_id,), daemon=True).start()

    return {"sessionId": session_id, "status": "running"}


@router.get("/sessions")
def list_sessions(
    status: Optional[str] = Query(default=None),
    owner: Optional[str] = Query(default=None),
    from_: int = Query(default=0, alias="from"),
    size: int = Query(default=20, le=100),
):
    return {"sessions": store.list_sessions(status=status, owner=owner, from_=from_, size=size)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions/{session_id}/clone", status_code=201)
def clone_session(session_id: str, x_analyst_id: str = Header(default="")):
    if not x_analyst_id:
        raise HTTPException(status_code=400, detail="Missing X-Analyst-Id header")

    source = store.get_session(session_id)
    if not source:
        raise HTTPException(status_code=404, detail="Session not found")
    if source.get("status") not in {"complete", "saved"}:
        raise HTTPException(status_code=409, detail="Only complete or saved sessions can be cloned")

    launch_config = source.get("launchConfig")
    if not launch_config:
        launch_config = _build_launch_config(source["parameters"])
    params = _params_from_launch_config(launch_config)

    new_session_id = str(uuid.uuid4())
    now = _now()
    session = _build_pending_session(new_session_id, x_analyst_id, now, params)
    session["launchConfig"] = deepcopy(launch_config)
    session["clonedFromSessionId"] = session_id
    _put_new_session_or_raise(session)

    return {"sessionId": new_session_id, "status": "pending", "createdAt": now}


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, req: SessionPatchRequest):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if req.status:
        if req.status == "saved":
            if session["status"] != "complete":
                raise HTTPException(status_code=409, detail="Only complete sessions can be saved")
            session["status"] = "saved"
        elif req.status == "cancelled":
            updated_at = _now()
            session, result = store.request_session_cancel(session_id, updated_at)
            if result == "not_found":
                raise HTTPException(status_code=404, detail="Session not found")
            if result == "terminal":
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot cancel session in status '{session.get('status')}'",
                )
            if result == "cancelled":
                store.cleanup_cancelled_session(session_id, updated_at)
                return store.get_session(session_id)
            return session
        else:
            raise HTTPException(status_code=400, detail=f"Invalid status transition to '{req.status}'")

    if req.lastUpdatedBy:
        session["lastUpdatedBy"] = req.lastUpdatedBy

    session["updatedAt"] = _now()
    store.put_session(session)
    return session
