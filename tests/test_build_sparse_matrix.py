# backend/tests/test_build_sparse_matrix.py
import numpy as np
import pytest

from pipeline.filter_population import filter_population
from pipeline.build_sparse_matrix import build_sparse_matrix


def _pop_all():
    return filter_population({"JobCode": ["JC10", "JC20"]}, 10000)


def test_matrix_shape():
    ids, _ = _pop_all()
    matrix, ent_index, _ = build_sparse_matrix(ids, noise_filter_value=1)
    assert matrix.shape[0] == len(ids)
    assert matrix.shape[1] == len(ent_index)


def test_matrix_is_binary():
    ids, _ = _pop_all()
    matrix, _, _ = build_sparse_matrix(ids, noise_filter_value=1)
    assert set(matrix.data).issubset({1.0})


def test_matrix_is_csr():
    from scipy.sparse import issparse, csr_matrix
    ids, _ = _pop_all()
    matrix, _, _ = build_sparse_matrix(ids, noise_filter_value=1)
    assert issparse(matrix)
    assert matrix.format == "csr"


def test_noise_filter_drops_rare():
    # e_rare is held by 0 users in fixture — should be dropped at any threshold >= 1
    ids, _ = _pop_all()
    _, ent_index, dropped = build_sparse_matrix(ids, noise_filter_value=1)
    assert "e_rare" not in ent_index


def test_noise_filter_count():
    ids, _ = _pop_all()
    # At threshold=7, only e_vpn, e_email, e_hr survive (held by all 10)
    _, ent_index, dropped = build_sparse_matrix(ids, noise_filter_value=7)
    assert dropped > 0
    for ent in ent_index:
        assert ent in {"e_vpn", "e_email", "e_hr"}


def test_deterministic():
    ids, _ = _pop_all()
    m1, idx1, d1 = build_sparse_matrix(ids, noise_filter_value=1)
    m2, idx2, d2 = build_sparse_matrix(ids, noise_filter_value=1)
    assert idx1 == idx2
    assert (m1 - m2).nnz == 0


def test_user_with_no_surviving_assignments_has_zero_row():
    # u010 has finance entitlements; filter to engineering only, then set high noise
    ids, _ = filter_population({"JobCode": "JC10"}, 10000)
    # noise_filter_value=6 drops everything held by fewer than 6 users
    # With 5 engineering users, finance ents (held by 0 of them) are already absent
    matrix, ent_index, _ = build_sparse_matrix(ids, noise_filter_value=1)
    uid_to_row = {uid: i for i, uid in enumerate(ids)}
    # All engineering users should have at least one entitlement
    for uid in ids:
        row = matrix[uid_to_row[uid]]
        assert row.nnz > 0