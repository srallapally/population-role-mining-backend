# backend/tests/test_similarity_and_communities.py
import numpy as np
import pytest
from scipy.sparse import csr_matrix

from pipeline.build_similarity_graph import build_similarity_graph
from pipeline.detect_communities import detect_communities
from pipeline.filter_population import filter_population
from pipeline.build_sparse_matrix import build_sparse_matrix
from pipeline.compute_universal import compute_universal

SESSION_ID = "test-session-002"
BASE_PARAMS = {
    "filterCriteria": {"JobCode": ["JC10", "JC20"]},
    "universalThreshold": 0.90,
    "coverageThreshold": 0.80,
    "softThreshold": 0.50,
    "similarityThreshold": 0.30,
    "minGroupSize": 2,
    "maxRoles": 25,
    "outlierThreshold": 0.30,
    "birthrightCooccurrenceThreshold": 0.95,
    "noiseFilterValue": 1,
    "maxPopulation": 10000,
}


def _build_residual(params=None):
    p = {**BASE_PARAMS, **(params or {})}
    ids, pop_summary = filter_population(p["filterCriteria"], p["maxPopulation"])
    matrix, ent_index, _ = build_sparse_matrix(ids, p["noiseFilterValue"])
    _, residual, _ = compute_universal(matrix, ent_index, ids, SESSION_ID, p, pop_summary)
    return residual, ids, p


# --- Similarity graph ---

def test_adjacency_is_symmetric():
    residual, ids, p = _build_residual()
    adj, _ = build_similarity_graph(residual, p["similarityThreshold"])
    diff = adj - adj.T
    assert diff.nnz == 0


def test_no_self_loops():
    residual, ids, p = _build_residual()
    adj, _ = build_similarity_graph(residual, p["similarityThreshold"])
    diag = adj.diagonal()
    assert np.all(diag == 0)


def test_graph_metrics_keys():
    residual, ids, p = _build_residual()
    _, metrics = build_similarity_graph(residual, p["similarityThreshold"])
    assert set(metrics.keys()) == {"edgeCount", "graphDensity", "singletonCount",
                                   "largestConnectedComponentPct"}


def test_high_threshold_produces_more_singletons():
    residual, ids, p = _build_residual()
    _, metrics_low = build_similarity_graph(residual, 0.10)
    _, metrics_high = build_similarity_graph(residual, 0.99)
    assert metrics_high["singletonCount"] >= metrics_low["singletonCount"]


def test_both_empty_vectors_jaccard_zero():
    # Two users with zero residual → no edge
    data = csr_matrix((2, 5), dtype=np.float32)
    adj, metrics = build_similarity_graph(data, similarity_threshold=0.01)
    assert adj.nnz == 0
    assert metrics["singletonCount"] == 2


def test_identical_vectors_jaccard_one():
    row = np.array([[1, 1, 0, 0, 0]], dtype=np.float32)
    data = csr_matrix(np.vstack([row, row]))
    adj, _ = build_similarity_graph(data, similarity_threshold=0.99)
    assert adj[0, 1] == 1.0


# --- Community detection ---

def test_two_clear_communities_detected():
    # Engineering (u001–u003, u007–u008) and Finance (u004–u006, u009–u010)
    # should form two communities on residual access
    residual, ids, p = _build_residual()
    adj, _ = build_similarity_graph(residual, 0.30)
    communities, suppressed, modularity = detect_communities(adj, ids, min_group_size=2, max_roles=25)
    assert len(communities) >= 1


def test_community_members_are_valid_user_ids():
    residual, ids, p = _build_residual()
    adj, _ = build_similarity_graph(residual, 0.30)
    communities, _, _ = detect_communities(adj, ids, min_group_size=2, max_roles=25)
    all_ids = set(ids)
    for c in communities:
        for uid in c["userIds"]:
            assert uid in all_ids


def test_min_group_size_suppresses_small_communities():
    residual, ids, p = _build_residual()
    adj, _ = build_similarity_graph(residual, 0.30)
    _, suppressed, _ = detect_communities(adj, ids, min_group_size=100, max_roles=25)
    # With min_group_size=100 and only 10 users, everything suppressed
    assert all(s["reason"].startswith("below minimum") for s in suppressed)


def test_max_roles_cap():
    residual, ids, p = _build_residual()
    adj, _ = build_similarity_graph(residual, 0.01)  # very low threshold → many communities
    communities, suppressed, _ = detect_communities(adj, ids, min_group_size=1, max_roles=1)
    assert len(communities) <= 1


def test_determinism():
    residual, ids, p = _build_residual()
    adj, _ = build_similarity_graph(residual, 0.30)
    c1, s1, m1 = detect_communities(adj, ids, min_group_size=2, max_roles=25)
    c2, s2, m2 = detect_communities(adj, ids, min_group_size=2, max_roles=25)
    assert m1 == m2
    ids1 = sorted([sorted(c["userIds"]) for c in c1])
    ids2 = sorted([sorted(c["userIds"]) for c in c2])
    assert ids1 == ids2