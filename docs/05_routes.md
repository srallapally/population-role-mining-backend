# Implementation — Routes

All route files live in `routes/`. They are registered in `main.py` under the `/api/v1` prefix. Routes handle HTTP concerns — request validation, status code selection, error responses — and delegate business logic to the store or pipeline.

---

## routes/columns.py

Single endpoint: `GET /api/v1/columns`.

Calls `get_filter_columns()` from `data/loader.py` and returns the result. No logic — pure pass-through. The column list is derived once at startup when `load_all()` runs, and is stable for the lifetime of the server.

---

## routes/sessions.py

Handles all session lifecycle endpoints.

### Request Models

`SessionCreateRequest` is a Pydantic model that handles both parsing and validation of the request body.

**Field-level validation** (via `@field_validator`) enforces:
- All threshold floats must be in (0.0, 1.0]
- `minGroupSize` must be ≥ 1
- `maxRoles` must be ≥ 1

**Cross-field validation** (via `@model_validator`) enforces:
- `softThreshold` < `coverageThreshold`
- `coverageThreshold` < `universalThreshold`

These validators run before any route handler code executes. If validation fails, FastAPI returns a 422 automatically with the error details.

### Rejected System Parameters

Some parameters are system-computed/internal and must not be accepted from clients (`noiseFilter`, `noiseFilterValue`, `noiseFilterFormula`, `maxPopulation`). Pydantic strips unknown fields before the route handler runs, so checking `hasattr(req, key)` would always be `False` — a dead check.

The fix is a FastAPI `Depends` function that reads the raw request body before Pydantic processes it:

```python
async def _reject_system_params(request: Request) -> None:
    body = await request.json()
    for key in REJECTED_PARAMS:
        if key in body:
            raise HTTPException(status_code=400, ...)
```

This dependency runs before the route handler and operates on the original JSON, so it catches any rejected key regardless of whether Pydantic would have stripped it.

### Parameter Resolution

`_resolve_params()` converts the (partially filled) `SessionCreateRequest` into a complete parameters dict. It uses explicit `is not None` checks — not `or` — to determine whether a value was supplied:

```python
# Correct
coverage = req.coverageThreshold if req.coverageThreshold is not None else config.DEFAULT_COVERAGE_THRESHOLD

# Wrong — treats 0.0 as "not supplied"
coverage = req.coverageThreshold or config.DEFAULT_COVERAGE_THRESHOLD
```

The `or` pattern fails for any threshold value of `0.0` — it would silently replace a legitimate analyst-supplied zero with the default. Using `is not None` is explicit about intent.

### POST /sessions/:id/run

Uses `transition_pending_to_running()` from the store for the `pending → running` transition. If the transition returns `None` (another thread already transitioned it), a 409 is returned. See `03_store.md` for the threading rationale.

### Header Handling on `POST /sessions/:id/run`

The handler signature currently accepts `X-Analyst-Id`, but the value is not used by route logic. The endpoint enforces only session existence/state and concurrent-run limits before transitioning to `running`.

### Session Limits, Cancellation, and Clone

Session creation uses `try_put_session_with_limits()` to enforce both `MAX_ACTIVE_SESSIONS` and `MAX_TOTAL_SESSIONS`. Active sessions are `pending`, `running`, and `cancelling`.

`PATCH /sessions/:id` supports saving complete sessions and cancelling pending/running sessions. Pending sessions transition directly to `cancelled` and cleanup runs immediately. Running sessions transition to `cancelling`; the orchestrator marks them `cancelled` at the next cancellation checkpoint and runs cleanup.

`POST /sessions/:id/clone` creates a new pending session from a complete or saved session's `launchConfig`. Results and role IDs are not copied.

---

## routes/roles.py

Handles role retrieval and editing.

### Default Sort

`_default_sort()` sorts roles by confidence descending, then memberCount descending, then name ascending. Layer 1 roles have `confidence: None` — the sort guard coerces None to 0 before negating:

```python
key=lambda r: (-(r.get("confidence") or 0), -r.get("memberCount", 0), r.get("name", ""))
```

Without the `or 0`, negating `None` raises a `TypeError`. Layer 1 roles sort after Layer 2 roles with real confidence scores, which is the correct behaviour.

### Failed Session Guard

`GET /sessions/:id/roles` checks the session status before returning roles. If the session is `failed`, the response is:

```json
{
  "guarded": true,
  "reason": "Roles from a failed session are non-authoritative",
  "roles": []
}
```

This is a 200 response, not a 404 — the session exists and the request is valid. The guard is informational: any role documents that may have been written before the failure are not returned, since they may be incomplete.

### Role Editing

PATCH operations can rename, advance status, remove entitlements, and merge roles. Entitlement removal updates `entitlements`, `entitlementMetadata`, and `entitlementCount`. Merge unions source entitlements into the target, carries metadata for newly added entitlements, updates `entitlementCount`, and marks source roles `discarded`.

The current implementation does not recompute `applications`, `confidence`, or `justificationMetadata.outliers`, and it does not set `analystEdited`.

### Status Constants vs Transitions

`VALID_ROLE_STATUSES` includes `promoted` and `discarded`, but transition enforcement only allows `candidate → draft → reviewed`. `discarded` is applied by merge operations; there is no PATCH transition path to `promoted` in the current implementation.

### Role Merge — `_merge_roles()`

Merges one or more source roles into a target role by unioning their entitlement sets. Source roles are marked `discarded` in the store. The target's entitlement metadata is updated with entries from the sources for any newly added entitlements.

`discarded` is a terminal status — a discarded role cannot be transitioned further. The valid status progression for non-discarded roles is `candidate → draft → reviewed`.
