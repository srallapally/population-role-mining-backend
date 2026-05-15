# Role Mining — The Pipeline

The pipeline runs asynchronously in a background thread after the analyst starts a session. For `roleType="job_roles"`, it executes all six steps. For `roleType="birthright"`, it stops after Step 3 and writes only Layer 1 birthright roles. If any step fails, the session is marked `failed` with an error message.

This document describes each step in functional terms — what it does, what it decides, and what parameters control it.

---

## Step 1 — Filter Population

**What it does:** Selects the users to mine from.

The analyst provides a set of filter criteria — key/value pairs matching identity attributes (e.g. `{"CostCenterDescription": "Ambulatory Informatics", "JobCode": "Epic Link"}`). The pipeline queries the identity data and returns the matching users.

Two hard guards are enforced before any mining begins:

- If the filter matches **zero users**, the session fails immediately with a clear error. There is nothing to mine.
- If the filter matches **more than 10,000 users**, the session fails. The pipeline is not designed to operate above this scale. The analyst must narrow the filter.

If the filter matches between 1 and 10,000 users, the pipeline proceeds with that population.

**What the analyst controls:** `filterCriteria` — required. Everything else in this step is fixed.

**Output:** A sorted list of user IDs forming the population for all subsequent steps.

---

## Step 2 — Build the Access Matrix

**What it does:** Constructs a structured representation of who has what.

For every user in the population, the pipeline looks up their current entitlement assignments. It then builds a binary matrix: rows are users, columns are entitlements, and each cell is 1 (user holds this entitlement) or 0 (they don't).

Before building the matrix, a **noise filter** removes entitlements held by very few users. An entitlement held by only 2 users out of 2,000 cannot define a meaningful role — it's either a one-off grant or an outlier. The noise filter threshold is derived automatically from the analyst's other parameters; it is never set directly.

> **Noise filter formula:** `max(2, floor(minGroupSize × coverageThreshold) - 1)`
>
> At the defaults (`minGroupSize=30`, `coverageThreshold=0.80`), this evaluates to 23. Any entitlement held by fewer than 23 users is dropped before any analysis runs. This ensures the noise floor is always consistent with the analyst's definition of a meaningful role.

**What the analyst controls:** Indirectly via `minGroupSize` and `coverageThreshold` — raising either raises the noise floor.

**Output:** A sparse binary matrix (users × surviving entitlements), plus a count of how many entitlements were dropped.

---

## Step 3 — Identify Birthright Access

**What it does:** Separates the access everyone shares from the access that differentiates people.

The pipeline scans every column (entitlement) in the matrix and computes what fraction of the population holds it. Entitlements held by a very high fraction — at or above the `universalThreshold` — are classified as **universal**.

Universal entitlements are then grouped into one or more **birthright roles**. The grouping is based on a simple question: do these entitlements travel together? If VPN and email are both held by the same 95% of users, they belong in the same birthright role. If Active Directory access is held by a slightly different 92%, it may belong in a separate birthright role.

Two entitlements are grouped together if their holder sets are sufficiently similar (controlled by `birthrightCooccurrenceThreshold`). Each resulting group becomes one `layer1_universal` role document.

After this step, all universal entitlements are removed from the matrix. What remains is the **residual matrix** — the access that differentiates users from each other. This is what the remaining steps operate on for `job_roles` sessions.

**What the analyst controls:**
- `universalThreshold` (default 0.90) — raise to make birthright roles smaller and leave more access for community detection; lower to make birthright roles larger
- `birthrightCooccurrenceThreshold` (default 0.95) — raise to split birthright roles more aggressively; lower to merge more entitlements into fewer roles

**Output:** One or more `layer1_universal` role documents (held in memory until write phase), plus the residual matrix for steps 4–6.

> **What if nothing is universal?** Zero universal entitlements is a valid outcome — the population has no shared baseline. The session still succeeds; it simply produces zero Layer 1 roles.

---

## Step 4 — Build the Similarity Graph

**What it does:** Measures how similar each pair of users is, based on their residual access.

For every pair of users, the pipeline computes a similarity score — the fraction of their combined residual entitlements that they share. Two users who hold exactly the same residual entitlements get a score of 1.0. Two users who share nothing get 0.0.

This produces a graph where each user is a node. An edge is drawn between two users if their similarity score meets or exceeds the `similarityThreshold`. Users with no edges — whose residual access is too unique to match anyone else — become **singletons** and will not appear in any candidate role.

The graph also produces four diagnostic metrics written to the session:

- **Edge count** — total number of edges
- **Graph density** — what fraction of possible edges exist
- **Singleton count** — users with no edges
- **Largest connected component** — what fraction of users are in the largest cluster

These metrics help the analyst understand whether the threshold is well-calibrated. A high singleton count means the threshold may be too strict. A low graph density means the population has highly individualised access.

**What the analyst controls:**
- `similarityThreshold` (default 0.30) — the primary tuning knob. Lower = broader roles, more users placed. Higher = tighter roles, more singletons.

**Output:** A similarity graph (adjacency matrix) and graph metrics.

---

## Step 5 — Detect Communities

**What it does:** Finds groups of users who are more similar to each other than to the rest of the population.

The pipeline runs a community detection algorithm (Leiden) on the similarity graph. Leiden partitions the graph into communities — subgraphs where internal similarity is significantly higher than what you'd expect by chance.

Two gating rules are applied to the raw communities:

**Size gate:** Any community smaller than `minGroupSize` is suppressed. A "role" held by 3 people isn't operationally useful as a managed role — it's more likely coincidental overlap or a data anomaly.

**Count gate:** If more communities survive the size gate than `maxRoles` allows, only the largest are kept. This prevents the analyst from being presented with 200 micro-roles.

Suppressed communities are recorded in the session's `populationSummary` so the analyst can see what was filtered out and why.

**What the analyst controls:**
- `minGroupSize` (default 30) — minimum community size to produce a candidate role
- `maxRoles` (default 25) — maximum number of candidate roles to produce

**Output:** A list of surviving communities (each a group of user IDs), plus a record of suppressed communities.

> **What if no communities survive?** Zero candidate roles is a valid outcome. The session still succeeds with its Layer 1 birthright roles. The analyst can lower `similarityThreshold` or `minGroupSize` and re-run.

---

## Step 6 — Compose Candidate Roles

**What it does:** Turns each community into a fully-described candidate role.

For each surviving community, the pipeline computes entitlement prevalence within that community's own membership — not against the full session population. This is important: an entitlement held by 80% of a 50-person community is a strong role signal even if it's only held by 2% of the overall population.

Entitlements are then tiered:

| Tier | Prevalence within community | Meaning |
|---|---|---|
| `role_defining` | ≥ `coverageThreshold` | Defines the role — what the role *is* |
| `common_not_universal` | ≥ `softThreshold` and < `coverageThreshold` | Common in the community but not strong enough to define it |
| Excluded | < `softThreshold` | Not characteristic of this group |

A community with zero `role_defining` entitlements is suppressed — it represents users who cluster by similarity but don't share any dominant access pattern. This is recorded in the session summary.

Each surviving community produces one `layer2_candidate` role document containing:

- **Role-defining and common entitlements** with per-entitlement prevalence
- **Application breakdown** — which applications the role spans, with counts and percentages
- **Cohesion score** — a measure of how internally similar the community is (High ≥ 0.7, Medium 0.4–0.7, Low < 0.4). A low cohesion score means the community was detected but members don't share much access — treat such roles with caution.
- **Outlier analysis** — community members whose access deviates significantly from the role profile, split into under-provisioned (missing role entitlements) and over-provisioned (holding extra entitlements outside the role)

**What the analyst controls:**
- `coverageThreshold` (default 0.80) — minimum prevalence within the community for an entitlement to define the role
- `softThreshold` (default 0.50) — minimum prevalence to appear in role metadata at all
- `outlierThreshold` (default 0.30) — how far a member must deviate to be flagged as an outlier

**Output:** Zero or more `layer2_candidate` role documents (held in memory until write phase).

---

## Write Phase

For `birthright` sessions, the pipeline writes Layer 1 roles and completes immediately after Step 3. For `job_roles` sessions, after all six steps complete, the pipeline commits all results:

1. Write Layer 1 birthright roles
2. Write Layer 2 candidate roles
3. Update the session to `complete` with all output fields

If cancellation is requested while the pipeline is running, the worker exits at the next checkpoint, marks the session `cancelled`, and triggers cleanup for generated roles. If an exception occurs outside cancellation, the session is marked `failed`.

---

## Parameter Interactions

Some parameters affect more than one step. Understanding the interactions helps when tuning:

| If you change... | It also affects... |
|---|---|
| `minGroupSize` ↑ | Noise filter threshold ↑ (more entitlements dropped in Step 2) |
| `universalThreshold` ↓ | More entitlements stripped as universal → sparser residual → fewer/looser communities |
| `similarityThreshold` ↑ | More singletons → fewer, tighter communities |
| `coverageThreshold` ↑ | Noise filter threshold ↑; harder for communities to have role-defining entitlements |

The session's `graphMetrics` and `singletonCount` are the primary feedback signals for threshold tuning. If `singletonCount` is very high, lower `similarityThreshold`. If `candidateRoleCount` is 0 but communities were detected, lower `coverageThreshold`.
