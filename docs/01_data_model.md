# Role Mining — Data Model

## Input Data

The pipeline reads from three CSV files. The file paths are configurable via environment variables (see `config.py`). All three files are loaded into memory at server startup.

---

### identities.csv

One row per user. Contains identity attributes used to define the population filter.

| Column | Description |
|---|---|
| `usr_id` | Primary key — unique user identifier. Used internally; not a valid filter key. |
| `user_name` | Login name |
| `usr_manager_id` | Manager's user ID |
| `CostCenterNumber` | Cost centre code |
| `CostCenterDescription` | Cost centre name (e.g. "Ambulatory Informatics") |
| `JobCode` | Job code identifier (e.g. "Epic Link") |
| `JobCodeDescription` | Human-readable job title |
| `IsManager` | Boolean — whether the user is a manager |
| `ManagementLevel` | Numeric management level |
| `ManagementLevelDescription` | Text description of management level |
| `WorkLocation` | Physical work location |
| `OrgRelation` | Employment relationship (e.g. EMP, CON) |
| `OrgCode` | Organisation unit code |
| `EmployeeTypeID` | Numeric employee type |
| `EmployeeTypeName` | Employee type label (e.g. Employee, Contractor) |
| `managerjobcode` | Job code of the user's manager |

All columns except `usr_id` are valid filter keys. The system derives the list of valid filter keys dynamically from the CSV headers at load time — no column names are hardcoded.

**Filter behaviour:** A filter criterion `{"JobCode": "Epic Link"}` selects all rows where `JobCode == "Epic Link"`. Multiple criteria are ANDed together. A criterion value can be a single string or a list of strings (OR within the field).

---

### entitlements.csv

One row per entitlement in the catalogue. Used at role composition time to enrich role output with display names and application metadata.

| Column | Description |
|---|---|
| `ent_id` | Primary key — unique entitlement identifier |
| `ent_name` | Human-readable entitlement name |
| `ent_owner_id` | Owner identifier |
| `app_id` | Application identifier — used to group entitlements by application in role output |
| `EntitlementTypeID` | Numeric type identifier |
| `EntitlementTypeName` | Type label (e.g. "Active Directory Groups", "Role") |

---

### assignments.csv

One row per (user, entitlement) grant. This is the primary input to matrix construction.

| Column | Description |
|---|---|
| `user_id` | Foreign key to `identities.csv.usr_id` |
| `ent_id` | Foreign key to `entitlements.csv.ent_id` |
| `ent_name` | Entitlement name (denormalised from entitlements) |

The pipeline joins assignments to the filtered population by `user_id`, then constructs a binary matrix where each cell indicates whether a user holds a given entitlement.

---

## Output Data

Results are held in an in-memory store (two dictionaries — one for sessions, one for roles). They are accessible via the REST API while the server is running, and are lost on restart.

---

### Session

A session represents one pipeline run. It is created by the analyst, transitions through a lifecycle, and accumulates output fields as the pipeline progresses.

**Lifecycle states:**

```
pending → running → complete
                 → failed
complete → saved
```

**Key fields:**

| Field | Set by | Description |
|---|---|---|
| `id` | API | UUID — session identifier |
| `status` | API + Pipeline | Current lifecycle state |
| `sessionOwner` | API | Analyst ID from `X-Analyst-Id` header |
| `parameters` | API | Fully resolved input parameters — set at creation, never modified |
| `populationSize` | Pipeline | Number of users matched by the filter |
| `totalEntitlementsConsidered` | Pipeline | Entitlements surviving the noise filter |
| `totalEntitlementsDropped` | Pipeline | Entitlements removed by the noise filter |
| `layer1RoleCount` | Pipeline | Number of birthright roles produced |
| `layer1RoleIds` | Pipeline | List of birthright role document IDs |
| `candidateRoleCount` | Pipeline | Number of candidate roles produced |
| `candidateRoleIds` | Pipeline | List of candidate role document IDs |
| `singletonCount` | Pipeline | Users not placed in any candidate role community |
| `graphMetrics` | Pipeline | Similarity graph diagnostics (see below) |
| `highResidualPrevalenceEntitlements` | Pipeline | Entitlements just below the universal threshold |
| `populationSummary` | Pipeline | Filter description and suppressed community list |
| `errorDetail` | Pipeline | Error message if status is `failed` |
| `completedAt` | Pipeline | Timestamp of pipeline completion |

**Graph metrics** (nested object on the session):

| Field | Description |
|---|---|
| `edgeCount` | Number of edges in the similarity graph |
| `graphDensity` | Fraction of possible edges that exist |
| `singletonCount` | Users with no edges above the similarity threshold |
| `largestConnectedComponentPct` | Fraction of users in the largest connected cluster |

These are diagnostic signals for threshold tuning. A high `singletonCount` means `similarityThreshold` may be too aggressive. A low `graphDensity` means users in this population have highly individualised access.

---

### Role

A role document represents either a birthright role (`layer1_universal`) or a candidate role (`layer2_candidate`). Both share a common structure but differ in which fields are populated.

**Key fields:**

| Field | Applies to | Description |
|---|---|---|
| `id` | Both | UUID — role identifier |
| `status` | Both | `candidate` → `draft` → `reviewed` → `promoted`. Also `discarded` (merged into another role) |
| `roleType` | Both | `layer1_universal` or `layer2_candidate` |
| `sessionId` | Both | ID of the producing session |
| `name` | Both | System-generated name. Analyst can rename. |
| `memberCount` | Both | Number of users in this role |
| `entitlementCount` | Both | Number of role-defining entitlements |
| `entitlements` | Both | Space-delimited list of role-defining entitlement IDs |
| `confidence` | Layer 2 only | Cohesion score — mean pairwise similarity of community members (0–1) |
| `applications` | Both | Breakdown of entitlements by application |
| `entitlementMetadata` | Both | Per-entitlement detail including prevalence and tier |
| `justificationMetadata` | Both | Explainability payload — why this role was produced |
| `analystEdited` | Both | Set to `true` when an analyst has modified the role after creation |

**Entitlement tiers** (within `entitlementMetadata`):

| Tier | Meaning |
|---|---|
| `universal` | Layer 1 only — held by ≥ `universalThreshold` of the population |
| `role_defining` | Layer 2 — held by ≥ `coverageThreshold` of the community |
| `common_not_universal` | Layer 2 — held by ≥ `softThreshold` but < `coverageThreshold` of the community |

**Justification metadata** explains why the role was produced. For Layer 1 roles it contains the session context and thresholds. For Layer 2 roles it additionally contains the community ID, modularity score, cohesion interpretation, and a list of outlier users whose access deviates significantly from the role profile.

---

## How the Data Flows

```
identities.csv ──┐
                 ├──▶ filter_population ──▶ population IDs
assignments.csv ─┘
                      population IDs ──▶ build_sparse_matrix ──▶ binary matrix
entitlements.csv ────────────────────────────────────────────▶ (enrichment at step 6)

binary matrix ──▶ compute_universal ──▶ layer1 roles + residual matrix
residual matrix ──▶ build_similarity_graph ──▶ adjacency matrix
adjacency matrix ──▶ detect_communities ──▶ communities
communities + residual matrix ──▶ compose_roles ──▶ layer2 roles

layer1 roles + layer2 roles + session metadata ──▶ in-memory store
```
