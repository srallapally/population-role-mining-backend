# Implementation — Pipeline Scripts

All pipeline scripts live in `pipeline/`. They are pure functions — they take inputs and return outputs, with no side effects on the store or the filesystem. The orchestrator is the only pipeline file that touches the store.

---

## filter_population.py

**Entry point:** `filter_population(filter_criteria, max_population)`

Queries the identities DataFrame using the analyst's filter criteria. Criteria values can be a single string (exact match) or a list of strings (any-of match). Multiple criteria are ANDed together.

Returns a tuple of:
- `population_ids` — sorted list of matching `usr_id` values
- `population_summary` — dict containing count, filter description, and raw criteria

Raises `ValueError` (causing session failure) if:
- Zero users match the filter
- More than `max_population` users match

The population IDs are sorted lexicographically. This sort order is preserved through matrix construction to ensure deterministic row assignment.

---

## build_sparse_matrix.py

**Entry point:** `build_sparse_matrix(population_ids, noise_filter_value)`

Looks up assignments for the population from the assignments DataFrame, then constructs a binary CSR (Compressed Sparse Row) matrix.

**Why sparse?** A dense matrix for 2,678 users × 153 entitlements would be manageable, but at 10,000 users × 10,000 entitlements (the maximum scale) a dense matrix would be ~800MB. Sparse format stores only the non-zero entries, typically 1–5% of the total cells. The matrix stays in scipy sparse format throughout — it is never converted to a dense array.

**Noise filtering:** Before building the matrix, entitlements held by fewer than `noise_filter_value` users are dropped. The surviving entitlement IDs are sorted lexicographically before column assignment (same determinism guarantee as row assignment).

Returns:
- `matrix` — CSR binary matrix (users × surviving entitlements)
- `entitlement_index` — dict mapping `ent_id → column index`
- `dropped_count` — number of entitlements removed by the noise filter

---

## compute_universal.py

**Entry point:** `compute_universal(matrix, entitlement_index, population_ids, session_id, parameters, population_summary)`

This script does three things:

**1. Compute prevalence.** For each column (entitlement), sum the column and divide by the population size. This gives the fraction of users holding each entitlement.

**2. Cluster universal entitlements.** Entitlements at or above `universalThreshold` are candidates for birthright roles. They are grouped using complete-linkage agglomerative clustering: two entitlements are placed in the same cluster only if their holder sets are sufficiently similar (`birthrightCooccurrenceThreshold`) with every other member of the cluster already. This prevents transitivity — A grouping with C via B even when A and C themselves are dissimilar.

For each cluster, a `layer1_universal` role document is constructed in memory. The `memberCount` is the intersection of holder sets (users who hold every entitlement in the cluster), not the union.

**3. Build the residual matrix.** Universal entitlement columns are zeroed out. What remains is the residual matrix — the access that differentiates users — which is passed to the next steps.

Also identifies `highResidualPrevalenceEntitlements` — entitlements between `coverageThreshold` and `universalThreshold` that are near-universal but didn't qualify. These are surfaced on the session as a diagnostic.

Returns:
- `layer1_roles` — list of role dicts (not yet written to store)
- `residual` — CSR matrix with universal columns zeroed
- `high_residual_prevalence` — list of near-universal entitlement metadata

---

## build_similarity_graph.py

**Entry point:** `build_similarity_graph(residual, similarity_threshold)`

Computes pairwise Jaccard similarity between all users based on their residual entitlement vectors, then builds a thresholded adjacency matrix.

**The Jaccard computation stays sparse throughout.** The key operations:

```python
intersection = (residual @ residual.T)   # sparse matrix multiply — gives intersection counts
row_sums = residual.sum(axis=1)          # cardinality of each user's residual set
# For each non-zero entry (i, j):
#   union(i, j) = |A| + |B| - intersection(i, j)
#   jaccard(i, j) = intersection / union
```

Only non-zero intersection entries need to be evaluated — if two users share no entitlements, their Jaccard is 0 and they won't get an edge regardless of threshold.

After thresholding, graph metrics are computed directly from the sparse adjacency matrix using scipy's `connected_components` function.

Returns:
- `adjacency` — sparse symmetric adjacency matrix
- `graph_metrics` — dict with `edgeCount`, `graphDensity`, `singletonCount`, `largestConnectedComponentPct`

---

## detect_communities.py

**Entry point:** `detect_communities(adjacency, population_ids, min_group_size, max_roles)`

Builds an igraph `Graph` from the adjacency matrix and runs the Leiden community detection algorithm using `ModularityVertexPartition`.

**Why Leiden over Louvain?** Leiden guarantees that every detected community is internally connected — Louvain can produce communities containing disconnected subgraphs. A disconnected community would mean users assigned to the same role who share no access similarity with each other, which would make the cohesion score and outlier analysis meaningless.

The random seed is fixed (`LEIDEN_SEED = 42`) and edges are added in deterministic order (sorted by node index pair). This ensures identical inputs produce identical outputs within the same execution environment.

After detection, two gating rules are applied:
- **Size gate:** communities below `min_group_size` are suppressed
- **Count gate:** if more than `max_roles` survive, only the largest are kept

Returns:
- `communities` — list of `{communityId, userIds[]}` dicts
- `suppressed` — list of `{communityId, size, reason}` dicts
- `modularity` — float, the Leiden partition quality score

---

## compose_roles.py

**Entry point:** `compose_roles(communities, residual, entitlement_index, population_ids, modularity, session_id, parameters, population_summary)`

For each surviving community, computes entitlement prevalence within that community's own membership (not the full population), applies the two-tier threshold, computes cohesion, builds the application breakdown, and runs outlier analysis.

**Two-tier thresholding** is applied per community:
- `role_defining`: prevalence ≥ `coverageThreshold`
- `common_not_universal`: `softThreshold` ≤ prevalence < `coverageThreshold`

A community with zero `role_defining` entitlements is suppressed with reason `"no entitlement met role-defining coverage threshold"`.

**Cohesion** is mean pairwise Jaccard across all community members, computed on their residual vectors. The computation mirrors `build_similarity_graph` but only over the community's rows. It stays sparse — no dense matrix allocation.

**Outlier analysis** computes two independent scores per community member:
- `underProvisioningScore` — fraction of role-defining entitlements the user is missing
- `overProvisioningScore` — fraction of the user's residual access that is outside the role definition

Users exceeding `outlierThreshold` on either score are included in `justificationMetadata.outliers` with a plain-language explanation.

Roles are sorted in canonical order (confidence descending, memberCount descending, name ascending) before being returned.

Returns:
- `layer2_roles` — list of role dicts in canonical order
- `suppressed_roles` — list of communities suppressed by the role-defining entitlement gate

---

## orchestrator.py

**Entry point:** `run_pipeline(session_id)`

Called by the background thread spawned when `POST /sessions/:id/run` succeeds. Wires together all six pipeline steps and handles the atomic write phase.

**Error handling:** The entire function body is wrapped in a try/except. Any exception from any step causes the session to be marked `failed` with `errorDetail` set to the exception message. No partial results are written.

**Write ordering:**
1. Write Layer 1 roles (sorted by first app name, then role UUID)
2. Write Layer 2 roles (in canonical order)
3. Update session to `complete` with all output fields

The session is only marked `complete` after all role writes succeed. This ensures the API never returns a `complete` session that has missing roles.

**What gets written to the session on completion:**

```python
session["status"] = "complete"
session["populationSize"] = len(population_ids)
session["totalEntitlementsConsidered"] = matrix.shape[1] + dropped_count
session["totalEntitlementsDropped"] = dropped_count
session["layer1RoleIds"] = [r["id"] for r in layer1_roles]
session["layer1RoleCount"] = len(layer1_roles)
session["candidateRoleIds"] = [r["id"] for r in layer2_roles]
session["candidateRoleCount"] = len(layer2_roles)
session["singletonCount"] = graph_metrics["singletonCount"]
session["graphMetrics"] = graph_metrics
session["highResidualPrevalenceEntitlements"] = high_residual
session["populationSummary"] = population_summary
session["completedAt"] = _now()
session["lastUpdatedBy"] = "system"
```
