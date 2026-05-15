# Implementation — Key Constraints and Design Decisions

This document explains the non-obvious implementation decisions — the things that look like they could be done differently but have specific reasons behind them.

---

## Sparse Matrices Throughout

The similarity graph computation at Step 4 involves comparing every pair of users. At 10,000 users that is 50 million pairs. If done naively with dense arrays:

```python
# Do NOT do this
jaccard_matrix = np.zeros((n_users, n_users))   # 800MB at float64
for i in range(n_users):
    for j in range(n_users):
        jaccard_matrix[i][j] = compute_jaccard(...)
```

This would require ~3–4GB of memory and take minutes to compute.

Instead, the pipeline exploits the mathematical structure of Jaccard similarity:

```
J(A, B) = |A ∩ B| / |A ∪ B|
         = intersection / (|A| + |B| - intersection)
```

The intersection counts are computed via sparse matrix multiplication:

```python
intersection = (residual @ residual.T)
```

This is `O(nnz²)` where `nnz` is the number of non-zero entries — typically 1–5% of the total matrix. At 5% fill density, that's 5M non-zeros for a 10K×10K matrix, making the multiplication tractable. The result is itself sparse — only pairs of users who share at least one entitlement have non-zero intersection, and those are the only pairs worth evaluating.

The constraint is: **never call `.toarray()` on a user×user matrix**. The cohesion computation in `compose_roles.py` applies the same pattern for each community's submatrix.

---

## Noise Filter Formula

The noise filter threshold is derived from `minGroupSize` and `coverageThreshold`:

```
noiseFilterValue = max(2, floor(minGroupSize × coverageThreshold) - 1)
```

This is not arbitrary. It ensures the noise floor is always consistent with the analyst's definition of a meaningful role:

- A role requires at least `minGroupSize` members
- A role-defining entitlement must be held by ≥ `coverageThreshold` of the community
- Therefore, the minimum holder count for a role-defining entitlement is `floor(minGroupSize × coverageThreshold)`
- An entitlement held by one fewer user than this cannot be role-defining in any valid community
- The `max(2, ...)` guard prevents the threshold from being set below 2

At defaults (`minGroupSize=30`, `coverageThreshold=0.80`): `max(2, floor(24) - 1) = 23`. Any entitlement held by fewer than 23 users is impossible to be role-defining and is dropped.

The formula is also why lowering `minGroupSize` for small test populations is necessary: with `minGroupSize=3` and `coverageThreshold=0.80`, the noise filter is `max(2, floor(2.4) - 1) = max(2, 1) = 2`. This allows entitlements held by as few as 2 users to survive, which is appropriate when the population itself is only 10 users.

---

## Complete-Linkage Birthright Clustering

Universal entitlements are grouped into birthright roles using complete-linkage agglomerative clustering. The key property: two clusters are merged only if every cross-pair of entitlements meets the `birthrightCooccurrenceThreshold`.

An earlier version used connected components on a thresholded graph: draw an edge between entitlements A and B if `J(holders(A), holders(B)) >= threshold`, then take connected components. This is simpler but has a subtle flaw — **transitivity**.

With connected components:
- A and B have Jaccard = 0.96 → edge
- B and C have Jaccard = 0.96 → edge
- A and C have Jaccard = 0.60 → no edge, but they end up in the same component

A and C end up in the same birthright role despite their holder sets being only 60% similar. The `memberCount` (intersection of all holder sets in the cluster) becomes misleadingly small.

With complete-linkage, A and C cannot be in the same cluster unless they directly meet the threshold. Each cluster is a genuine set of mutually co-held entitlements.

---

## Atomic Status Transitions

The session store's `transition_session_status()` function performs a compare-and-swap under a lock:

```python
with _lock:
    if session["status"] != expected:
        return None   # reject
    session["status"] = new
    # ... update other fields
```

Without this, two concurrent `POST /sessions/:id/run` requests could both observe `status=pending` and both start the pipeline. With the atomic transition, only the first succeeds — the second finds `status=running` and returns 409.

This does not fully solve the concurrency cap race (two sessions could both pass the `count_running_sessions()` check before either transitions). That check is a separate read operation and cannot be made atomic with the transition without redesigning the store. For the POC this is acceptable — the cap may occasionally be exceeded by one session under race conditions.

---

## Monkeypatching Config in Tests

`conftest.py` uses pytest's `monkeypatch` fixture to redirect the loader to fixture CSVs:

```python
monkeypatch.setattr(config, "IDENTITIES_FILE", os.path.join(FIXTURES, "identities.csv"))
```

This only works because `loader.py` reads `config.IDENTITIES_FILE` at call time inside `load_all()`, not at import time. If `loader.py` copied the path into a module-level variable (`IDENTITIES_FILE = config.IDENTITIES_FILE` at the top of the file), the monkeypatch would have no effect — the loader would still use the original path.

The same principle applies to any module that needs to be testable with different configurations: import the config module and dereference its attributes at use time, not at import time.

---

## FastAPI Startup Event Deprecation

`main.py` uses `@app.on_event("startup")` to trigger `load_all()`:

```python
@app.on_event("startup")
def startup():
    load_all()
```

FastAPI has deprecated `on_event` in favour of the `lifespan` context manager pattern. The server works correctly with the deprecated pattern and the deprecation warning is harmless, but a future refactor should migrate to:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all()
    yield

app = FastAPI(lifespan=lifespan)
```

This also affects test isolation: the `TestClient` triggers the startup event when it is first created (at module import time in `test_api.py`). If `TestClient` is created at module level, it loads the real data before any test's monkeypatch runs. The test suite works around this by calling `load_all()` again explicitly in the `autouse` fixture after patching config — the second call overwrites the DataFrames loaded at startup.

---

## Test Fixture Population Size

The fixture CSVs contain 10 users. The default `minGroupSize=30` would cause the noise filter to set `noiseFilterValue=23`, dropping all entitlements (since no entitlement is held by 23 of the 10 fixture users). End-to-end tests that run the full pipeline must override `minGroupSize` to a value consistent with the fixture population:

```python
{"filterCriteria": FILTER, "minGroupSize": 3}
```

With `minGroupSize=3` and `coverageThreshold=0.80`, the noise filter is `max(2, 1) = 2`, and all fixture entitlements survive.

This is not a bug in the test or the formula — it reflects that the formula is designed for realistic populations (30+ users per community) and the fixture is intentionally tiny.
