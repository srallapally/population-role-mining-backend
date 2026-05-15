# backend/routes/roles.py
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import store
from data import store
router = APIRouter()

VALID_ROLE_TYPES = {"layer1_universal", "layer2_candidate"}
TIER_ALIAS = {"layer1": "layer1_universal", "layer2": "layer2_candidate"}
VALID_STATUS_TRANSITIONS = {
    "candidate": "draft",
    "draft": "reviewed",
}
# discarded: terminal status set by merge operations — role is consumed into another role
VALID_ROLE_STATUSES = {"candidate", "draft", "reviewed", "promoted", "discarded"}


class RolePatchRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    entitlements: Optional[list[str]] = None  # analyst removal: provide surviving entitlement IDs
    mergeRoleIds: Optional[list[str]] = None  # role IDs to merge into this role (union), then discard


def _default_sort(roles: list[dict]) -> list[dict]:
    return sorted(
        roles,
        key=lambda r: (-(r.get("confidence") or 0), -r.get("memberCount", 0), r.get("name", ""))
    )

@router.get("/sessions/{session_id}/roles")
def list_roles(
    session_id: str,
    roleType: Optional[str] = Query(default=None),
    tier: Optional[str] = Query(default=None),
    minMembers: Optional[int] = Query(default=None),
    from_: int = Query(default=0, alias="from"),
    size: int = Query(default=20, le=100),
):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["status"] == "failed":
        return {"guarded": True, "reason": "Roles from a failed session are non-authoritative",
                "roles": []}

    roles = store.list_roles_for_session(session_id)

    # Resolve tier alias
    effective_role_type = roleType
    if not effective_role_type and tier:
        effective_role_type = TIER_ALIAS.get(tier)

    if effective_role_type:
        if effective_role_type not in VALID_ROLE_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid roleType: '{effective_role_type}'")
        roles = [r for r in roles if r.get("roleType") == effective_role_type]

    if minMembers is not None:
        roles = [r for r in roles if r.get("memberCount", 0) >= minMembers]

    roles = _default_sort(roles)
    return {"roles": roles[from_: from_ + size], "total": len(roles)}


@router.get("/roles/{role_id}")
def get_role(role_id: str):
    role = store.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.patch("/roles/{role_id}")
def patch_role(role_id: str, req: RolePatchRequest):
    role = store.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if req.name is not None:
        role["name"] = req.name

    if req.status is not None:
        current = role.get("status", "candidate")
        expected_next = VALID_STATUS_TRANSITIONS.get(current)
        if req.status != expected_next:
            raise HTTPException(
                status_code=409,
                detail=f"Invalid status transition: '{current}' → '{req.status}'"
            )
        role["status"] = req.status

    if req.entitlements is not None:
        # Analyst removes entitlements — keep only those in the supplied list
        surviving = set(req.entitlements)
        role["entitlements"] = " ".join(
            e for e in role.get("entitlements", "").split()
            if e in surviving
        )
        role["entitlementMetadata"] = [
            em for em in role.get("entitlementMetadata", [])
            if em["entId"] in surviving
        ]
        role["entitlementCount"] = len(role["entitlementMetadata"])

    if req.mergeRoleIds:
        _merge_roles(role, req.mergeRoleIds)

    store.put_role(role)
    return role


def _merge_roles(target: dict, source_ids: list[str]) -> None:
    """Union entitlements from source roles into target. Mark sources as discarded."""
    existing_ent_ids = set(target.get("entitlements", "").split())
    existing_meta = {em["entId"]: em for em in target.get("entitlementMetadata", [])}

    for source_id in source_ids:
        source = store.get_role(source_id)
        if not source:
            continue
        for ent_id in source.get("entitlements", "").split():
            if ent_id not in existing_ent_ids:
                existing_ent_ids.add(ent_id)
                # Carry metadata from source if available
                source_meta = {em["entId"]: em for em in source.get("entitlementMetadata", [])}
                if ent_id in source_meta:
                    existing_meta[ent_id] = source_meta[ent_id]

        source["status"] = "discarded"
        store.put_role(source)

    target["entitlements"] = " ".join(sorted(existing_ent_ids))
    target["entitlementMetadata"] = list(existing_meta.values())
    target["entitlementCount"] = len(existing_meta)