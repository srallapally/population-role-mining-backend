# Appendix — Learning Resources

This appendix lists the key concepts and libraries used in the role mining pipeline, with annotations explaining why each is relevant and where to go to learn more.

---

## Algorithms and Concepts

### Jaccard Similarity

**What it is:** A measure of similarity between two sets. Defined as the size of the intersection divided by the size of the union: `J(A, B) = |A ∩ B| / |A ∪ B|`. Returns 0 for completely disjoint sets and 1 for identical sets.

**Why it's used here:** Jaccard is the right similarity metric for binary access vectors — it measures what fraction of the combined entitlement space two users share. Unlike cosine similarity, it is symmetric and interpretable: a Jaccard of 0.6 means 60% of the combined access is shared.

**Learn more:**
- [Wikipedia — Jaccard index](https://en.wikipedia.org/wiki/Jaccard_index) — clear definition with worked examples
- [Towards Data Science — Jaccard Similarity](https://towardsdatascience.com/overview-of-text-similarity-metrics-3397c4601f50) — practical comparison with other similarity metrics

---

### Sparse Matrices

**What they are:** A data structure for matrices where most values are zero. Instead of storing all values, only the non-zero entries are stored along with their row and column indices.

**Why they're used here:** User-entitlement access matrices are highly sparse — a typical user holds 10–50 entitlements out of thousands possible (1–5% fill density). Dense storage would waste gigabytes of memory on zeros. Sparse matrices enable matrix operations (like `R @ R.T` for intersection counts) to run on only the non-zero entries, which is orders of magnitude faster.

**Learn more:**
- [scipy.sparse documentation](https://docs.scipy.org/doc/scipy/reference/sparse.html) — official docs for the sparse matrix library used in this project
- [Real Python — NumPy and SciPy](https://realpython.com/numpy-scipy-pandas-correlation-python/) — accessible intro to scipy for data manipulation
- [Stanford CS246 — Mining Massive Datasets, Chapter 3](http://www.mmds.org/) — deep dive into sparse similarity computation at scale

---

### Community Detection

**What it is:** A family of graph algorithms that partition a graph into groups (communities) where nodes are more densely connected to each other than to the rest of the graph. Applied here to find groups of users who share more access patterns with each other than with the rest of the population.

**Why it's used here:** After building a similarity graph where edges connect similar users, community detection finds the natural clusters — the groups that correspond to functional roles.

**Learn more:**
- [Graph theory primer — Khan Academy](https://www.khanacademy.org/computing/computer-science/algorithms) — foundational graph concepts
- [Community detection overview — Fortunato (2010)](https://arxiv.org/abs/0906.0612) — comprehensive academic survey (accessible introduction in sections 1–3)
- [igraph tutorial](https://igraph.org/python/tutorial/latest/tutorial.html) — the Python library used for graph construction in this project

---

### Leiden Algorithm

**What it is:** A community detection algorithm that optimises modularity — a measure of how much better the detected community structure is compared to a random graph. Leiden improves on the older Louvain algorithm by guaranteeing that every detected community is internally connected.

**Why it's used instead of Louvain:** Louvain can produce communities containing disconnected subgraphs — users assigned to the same role who share no similarity path. This would make cohesion scores meaningless. Leiden's connectivity guarantee means every community member can reach every other member through a chain of similar users.

**Learn more:**
- [Leiden algorithm paper (Traag et al., 2019)](https://www.nature.com/articles/s41598-019-41695-z) — the original paper, readable abstract and introduction
- [leidenalg Python package documentation](https://leidenalg.readthedocs.io/) — the library used in this project
- [Louvain vs Leiden — practical comparison](https://towardsdatascience.com/louvain-algorithm-93fde589f58c) — explains the differences with diagrams

---

### Agglomerative Clustering

**What it is:** A bottom-up clustering approach that starts with each item in its own cluster and progressively merges clusters based on a linkage criterion. Complete-linkage agglomerative clustering merges two clusters only when every pair across the two clusters meets the similarity threshold.

**Why it's used for birthright clustering:** Simple graph connected components allow transitivity — A groups with C via B even when A and C are dissimilar. Complete-linkage enforces that all members of a cluster are mutually similar, which is the correct semantics for "these entitlements travel together."

**Learn more:**
- [scikit-learn — Hierarchical clustering](https://scikit-learn.org/stable/modules/clustering.html#hierarchical-clustering) — clear explanation with diagrams
- [StatQuest — Hierarchical Clustering](https://www.youtube.com/watch?v=7xHsRkOdVwo) — excellent visual explanation (YouTube, 11 min)

---

## Libraries and Frameworks

### FastAPI

**What it is:** A modern Python web framework for building REST APIs. It uses Python type hints and Pydantic models to automatically validate request bodies and generate OpenAPI documentation.

**Why it's used here:** FastAPI's Pydantic integration means request validation (field types, value ranges, cross-field rules) is declared as Python classes rather than procedural if/else checks. This keeps route handlers clean and validation errors consistent.

**Learn more:**
- [FastAPI official tutorial](https://fastapi.tiangolo.com/tutorial/) — best-in-class documentation, start here
- [FastAPI — Request Body validation](https://fastapi.tiangolo.com/tutorial/body/) — how Pydantic models work as request validators
- [FastAPI — Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) — how `Depends()` works, used for the rejected-params check

### Pydantic

**What it is:** A Python data validation library. Used by FastAPI to parse and validate request bodies.

**Why it matters here:** The `@field_validator` and `@model_validator` decorators on `SessionCreateRequest` enforce threshold bounds and cross-field constraints. Understanding how Pydantic validators run (before the route handler, in field declaration order) is important for understanding why certain validation patterns work and others don't.

**Learn more:**
- [Pydantic v2 validators](https://docs.pydantic.dev/latest/concepts/validators/) — how field and model validators work
- [Pydantic v2 migration guide](https://docs.pydantic.dev/latest/migration/) — relevant if you see v1-style validators in older code

### pandas

**What it is:** A Python data manipulation library built around the DataFrame — a tabular data structure with labelled columns.

**Why it's used here:** CSV loading, filtering, and join operations (looking up assignments for a population) are expressed concisely as DataFrame operations. The DataFrames are loaded once at startup and treated as read-only throughout the pipeline.

**Learn more:**
- [pandas getting started](https://pandas.pydata.org/docs/getting_started/index.html) — official intro
- [10 minutes to pandas](https://pandas.pydata.org/docs/user_guide/10min.html) — fast practical overview

### pytest + monkeypatch

**What it is:** pytest is the Python testing framework. `monkeypatch` is a pytest fixture that allows tests to temporarily replace attributes on modules or objects.

**Why monkeypatching matters here:** The loader reads file paths from `config` at call time. Tests use `monkeypatch.setattr(config, "IDENTITIES_FILE", ...)` to redirect the loader to fixture files. This pattern only works if the production code reads config attributes at use time, not at import time — a subtle but important distinction.

**Learn more:**
- [pytest documentation](https://docs.pytest.org/en/stable/) — official docs
- [pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) — how monkeypatching works and when to use it
- [Real Python — pytest guide](https://realpython.com/pytest-python-testing/) — practical introduction with examples

### igraph + leidenalg

**What they are:** `igraph` is a graph library with a Python interface. `leidenalg` is the Leiden community detection implementation that operates on igraph graphs.

**Why two libraries:** `leidenalg` requires an igraph graph as input. The pipeline constructs the graph from the sparse adjacency matrix using `igraph.Graph(n=n, edges=edges)`, then passes it to `leidenalg.find_partition()`.

**Learn more:**
- [igraph Python tutorial](https://igraph.org/python/tutorial/latest/tutorial.html)
- [leidenalg documentation](https://leidenalg.readthedocs.io/en/stable/reference.html)
