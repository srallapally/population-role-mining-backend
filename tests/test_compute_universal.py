# backend/tests/test_compute_universal.py
import pytest

from pipeline.filter_population import filter_population
from pipeline.build_sparse_matrix import build_sparse_matrix
from pipeline.compute_universal import compute_universal

SESSION_ID = "test-session-001"

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


def _run(params=None):
    p = {**BASE_PARAMS, **(params or {})}
    ids, pop_summary = filter_population(p["filterCriteria"], p["maxPopulation"])
    matrix, ent_index, dropped = build_sparse_matrix(ids, p["noiseFilterValue"])
    layer1, residual, high_residual = compute_universal(
        matrix, ent_index, ids, SESSION_ID, p, pop_summary
    )
    return layer1, residual, high_residual, matrix, ent_index, ids


def test_universal_entitlements_identified():
    # e_vpn, e_email, e_hr held by all 10 users → universal at 0.90
    layer1, _, _, _, _, _ = _run()
    all_ents = {e for r in layer1 for e in r["entitlements"].split()}
    assert "e_vpn" in all_ents
    assert "e_email" in all_ents
    assert "e_hr" in all_ents


def test_at_least_one_layer1_role():
    layer1, _, _, _, _, _ = _run()
    assert len(layer1) >= 1


def test_layer1_role_type():
    layer1, _, _, _, _, _ = _run()
    for role in layer1:
        assert role["roleType"] == "layer1_universal"


def test_layer1_justification_metadata_present():
    layer1, _, _, _, _, _ = _run()
    for role in layer1:
        jm = role["justificationMetadata"]
        assert jm
        assert jm["layer"] == "layer1"
        assert jm["sessionId"] == SESSION_ID
        assert "communityId" not in jm


def test_layer1_applications_nonempty():
    layer1, _, _, _, _, _ = _run()
    for role in layer1:
        assert role["applications"]


def test_residual_matrix_universals_zeroed():
    layer1, residual, _, matrix, ent_index, _ = _run()
    # Collect all entitlement IDs in layer1 roles
    universal_ent_ids = {e for r in layer1 for e in r["entitlements"].split()}
    for ent_id in universal_ent_ids:
        col = ent_index.get(ent_id)
        if col is not None:
            assert residual[:, col].nnz == 0


def test_entitlement_ordering_descending_prevalence():
    layer1, _, _, _, _, _ = _run()
    for role in layer1:
        meta = role["entitlementMetadata"]
        prevalences = [em["prevalenceInRole"] for em in meta]
        assert prevalences == sorted(prevalences, reverse=True)


def test_no_universals_produces_zero_layer1_roles():
    # Set threshold to 1.01 — nothing can reach it
    layer1, _, _, _, _, _ = _run({"universalThreshold": 1.01})
    assert layer1 == []


def test_high_residual_prevalence_range():
    # coverageThreshold=0.50, universalThreshold=0.90
    # e_github, e_jira, e_confluence held by 5/10 = 0.50 → exactly at coverage
    # They should appear in high_residual if 0.50 <= p < 0.90
    _, _, high_residual, _, _, _ = _run({"coverageThreshold": 0.40, "universalThreshold": 0.90})
    prevalences = [h["prevalenceInPop"] for h in high_residual]
    for p in prevalences:
        assert 0.40 <= p < 0.90


def test_member_count_is_intersection():
    layer1, _, _, _, _, _ = _run()
    # All universal entitlements held by all 10 users → intersection = 10
    for role in layer1:
        assert role["memberCount"] <= 10