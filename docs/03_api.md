# Role Mining — API Reference

All endpoints are prefixed `/api/v1`. All requests and responses use `application/json`.

---

## Authentication

The API trusts the analyst identity passed in the `X-Analyst-Id` header. This header is required on session creation. It becomes the `sessionOwner` on the session document.

---

## Columns

### GET /api/v1/columns

Returns the list of identity attribute names that can be used as filter criteria keys. These are derived dynamically from the headers of `identities.csv` at server startup. The `usr_id` column is excluded.

**Response:**
```json
{
  "columns": ["user_name", "CostCenterDescription", "JobCode", "WorkLocation", ...]
}
```

Use this endpoint to build a dynamic filter form — never hardcode column names.

---

## Sessions

### POST /api/v1/sessions

Creates a new session. Validates the filter criteria, resolves all parameters to their effective values, and writes a `pending` session. Does **not** start the pipeline.

**Headers:**

| Header | Required | Description |
|---|---|---|
| `X-Analyst-Id` | Yes | Analyst identifier |
| `Content-Type` | Yes | `application/json` |

**Request body:**

| Field | Required | Default | Description |
|---|---|---|---|
| `filterCriteria` | Yes | — | `{columnName: value}` or `{columnName: [value1, value2]}`. Must be non-empty. Keys must be valid column names from `/api/v1/columns`. |
| `roleType` | Yes | — | `birthright` to produce Layer 1 roles only, or `job_roles` to run the full Layer 1 + Layer 2 pipeline |
| `universalThreshold` | No | 0.90 | Fraction of population that must hold an entitlement for it to be birthright |
| `coverageThreshold` | No | 0.80 | Fraction of a community that must hold an entitlement for it to be role-defining |
| `softThreshold` | No | 0.50 | Minimum prevalence within a community to appear in role metadata at all |
| `similarityThreshold` | No | 0.30 | Minimum similarity score for an edge in the similarity graph |
| `minGroupSize` | No | 30 | Minimum community size to produce a candidate role |
| `maxRoles` | No | 25 | Maximum number of candidate roles to produce |
| `outlierThreshold` | No | 0.30 | Deviation score above which a community member is flagged as an outlier |
| `birthrightCooccurrenceThreshold` | No | 0.95 | Minimum holder-set similarity to group two universal entitlements into the same birthright role |

**Rejected fields:** `noiseFilter`, `noiseFilterValue`, `noiseFilterFormula`, `maxPopulation` are system-computed/internal and not accepted. Submitting any of these returns 400.

**Validation rules:**
- All threshold fields must be in (0.0, 1.0]
- `softThreshold` must be less than `coverageThreshold`
- `coverageThreshold` must be less than `universalThreshold`
- `minGroupSize` must be ≥ 1
- `maxRoles` must be ≥ 1

**Response 201:**
```json
{
  "sessionId": "uuid",
  "status": "pending",
  "createdAt": "2026-05-14T21:50:32Z"
}
```

**Error responses:**

| Status | Reason |
|---|---|
| 400 | Missing `X-Analyst-Id`, empty `filterCriteria`, invalid filter key, rejected system param, threshold out of bounds, cross-field violation |
| 422 | Pydantic request validation failure, such as missing `roleType` or invalid enum value |
| 429 | Maximum active sessions or maximum total sessions reached. Includes `retryAfter: 30`. |

---

### POST /api/v1/sessions/:id/run

Starts the pipeline for a pending session. Returns immediately (202). The pipeline runs in a background thread; poll `GET /sessions/:id` for completion.

**Headers:**

| Header | Required | Description |
|---|---|---|
| `X-Analyst-Id` | No | Currently accepted by the route signature but not used for authorization/ownership checks |

**Preconditions checked synchronously (before 202):**
1. Session exists
2. Session is in `pending` status
3. Fewer than 5 sessions are currently `running`

If all preconditions pass, the session transitions to `running` and the pipeline starts.

**Response 202:**
```json
{
  "sessionId": "uuid",
  "status": "running"
}
```

**Error responses:**

| Status | Reason |
|---|---|
| 404 | Session not found |
| 409 | Session is not in `pending` status |
| 429 | Maximum concurrent sessions (5) reached. Includes `retryAfter: 30`. |

---

### GET /api/v1/sessions

Lists sessions. Supports filtering and pagination.

**Query parameters:**

| Parameter | Description |
|---|---|
| `status` | Filter by status: `pending`, `running`, `cancelling`, `cancelled`, `complete`, `saved`, `failed` |
| `owner` | Filter by `sessionOwner` |
| `from` | Pagination offset (default 0) |
| `size` | Page size (default 20, max 100) |

**Response 200:**
```json
{
  "sessions": [ ... ]
}
```

---

### GET /api/v1/sessions/:id

Returns the full session document including resolved parameters, population summary, graph metrics, and role ID lists.

A completed session includes all output fields. A failed session includes `errorDetail`. A running session includes only the fields set at creation.

**Response 404** if the session does not exist.

---

### PATCH /api/v1/sessions/:id

Updates a session. Supported status transitions are `complete → saved`, `pending → cancelled`, and `running → cancelling → cancelled` once the background worker reaches a cancellation checkpoint.

**Request body:**
```json
{
  "status": "saved",
  "lastUpdatedBy": "analyst-name"
}
```

To request cancellation:

```json
{
  "status": "cancelled"
}
```

Cancelling a pending session is immediate and triggers cleanup. Cancelling a running session returns `status="cancelling"`; the pipeline cooperatively exits at the next checkpoint, marks the session `cancelled`, and removes generated roles for that session.

**Error responses:**

| Status | Reason |
|---|---|
| 404 | Session not found |
| 409 | Save requested for a non-`complete` session, or cancel requested for a terminal session |

---

### POST /api/v1/sessions/:id/clone

Creates a new pending session from a completed or saved session's immutable `launchConfig`. Results are not copied.

**Response 201:**
```json
{
  "sessionId": "new-uuid",
  "status": "pending",
  "createdAt": "2026-05-14T21:50:32Z"
}
```

**Error responses:**

| Status | Reason |
|---|---|
| 400 | Missing `X-Analyst-Id` |
| 404 | Source session not found |
| 409 | Source session is not `complete` or `saved` |
| 429 | Maximum active sessions or maximum total sessions reached |

---

## Roles

### GET /api/v1/sessions/:id/roles

Lists all role documents produced by a session.

**Guard:** Roles from a `failed` session are non-authoritative. If the session status is `failed`, the response returns `{"guarded": true, "reason": "...", "roles": []}` rather than role documents.

**Default sort:** `confidence descending`, then `memberCount descending`, then `name ascending`. Layer 1 roles (which have no confidence score) sort after Layer 2 roles.

**Query parameters:**

| Parameter | Description |
|---|---|
| `roleType` | `layer1_universal` or `layer2_candidate` |
| `tier` | `layer1` or `layer2` — convenience alias |
| `minMembers` | Minimum `memberCount` filter |
| `from` | Pagination offset |
| `size` | Page size (default 20, max 100) |

**Response 200:**
```json
{
  "roles": [ ... ],
  "total": 7
}
```

---

### GET /api/v1/roles/:id

Returns the full role document including `entitlementMetadata` and `justificationMetadata`.

**Response 404** if the role does not exist.

---

### PATCH /api/v1/roles/:id

Updates a role. Permitted operations:

**Rename:**
```json
{ "name": "Epic Ambulatory Core Access" }
```

**Advance status** (candidate → draft → reviewed):
```json
{ "status": "draft" }
```

Status must follow the sequence. Skipping a step (e.g. `candidate → reviewed`) returns 409.

**Remove entitlements** — provide the list of entitlement IDs to keep (the rest are removed):
```json
{ "entitlements": ["ent_001", "ent_002"] }
```

After removal, `entitlements`, `entitlementMetadata`, and `entitlementCount` are updated. `applications`, `confidence`, and outlier analysis are not recomputed.

**Merge other roles into this role:**
```json
{ "mergeRoleIds": ["uuid-of-role-to-absorb"] }
```

The source roles' entitlements are unioned into this role. Source roles are marked `discarded`. The target's `entitlements`, `entitlementMetadata`, and `entitlementCount` are updated; `applications`, `confidence`, and outlier analysis are not recomputed.

Operations can be combined in a single PATCH — e.g. rename and advance status together.

---

## Session Lifecycle — Complete Example

```
1. POST /api/v1/sessions
   → 201 { sessionId, status: "pending" }

2. POST /api/v1/sessions/:id/run
   → 202 { status: "running" }

3. GET /api/v1/sessions/:id   (poll)
   → { status: "running", ... }

4. GET /api/v1/sessions/:id   (poll again)
   → { status: "complete", layer1RoleCount: 2, candidateRoleCount: 5, ... }

5. GET /api/v1/sessions/:id/roles
   → { roles: [...], total: 7 }

6. GET /api/v1/roles/:id
   → full role with entitlementMetadata and justificationMetadata

7. PATCH /api/v1/roles/:id   { name: "Epic Core Access", status: "draft" }
   → updated role

8. PATCH /api/v1/sessions/:id   { status: "saved" }
   → { status: "saved" }

9. POST /api/v1/sessions/:id/clone
   → 201 { sessionId, status: "pending" }
```

---

## Parameter Resolution

All optional parameters are resolved to their effective defaults at session creation time. The resolved values are written to the session document and never changed. The pipeline reads only from `session.parameters` — it never applies defaults or re-resolves values.

The same resolved launch information is also stored in immutable form as `session.launchConfig`. Cloning uses this launch config to create a fresh pending session without copying results.

The `noiseFilterValue` is computed from the analyst's other parameters:

```
noiseFilterValue = max(2, floor(minGroupSize × coverageThreshold) - 1)
```

This value is stored on the session as `resolvedNoiseFilterValue` for auditability.
