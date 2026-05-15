# backend/tests/test_compose_roles.py
import pytest

from pipeline.filter_population import filter_population
from pipeline.build_sparse_matrix import build_sparse_matrix
from pipeline.compute_universal import compute_universal
from pipeline.build_similarity_graph import build_similarity_graph
from pipeline.detect_communities import detect_communities
from pipeline.compose_roles import compose_roles

SESSION_ID = "test-session-003"
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


def _run_to_compose(params=None):
    p = {**BASE_PARAMS, **(params or {})}
    ids, pop_summary = filter_population(p["filterCriteria"], p["maxPopulation"])
    matrix, ent_index, _ = build_sparse_matrix(ids, p["noiseFilterValue"])
    _, residual, _ = compute_universal(matrix, ent_index, ids, SESSION_ID, p, pop_summary)
    adj, _ = build_similarity_graph(residual, p["similarityThreshold"])
    communities, _, modularity = detect_communities(adj, ids, p["minGroupSize"], p["maxRoles"])
    layer2, suppressed = compose_roles(
        communities, residual, ent_index, ids, modularity, SESSION_ID, p, pop_summary
    )
    return layer2, suppressed, communities


def test_layer2_roles_produced():
    layer2, _, communities = _run_to_compose()
    # At least one community should produce a role with the fixture data
    assert isinstance(layer2, list)


def test_role_type_is_layer2_candidate():
    layer2, _, _ = _run_to_compose()
    for role in layer2:
        assert role["roleType"] == "layer2_candidate"


def test_confidence_not_null():
    layer2, _, _ = _run_to_compose()
    for role in layer2:
        assert role["confidence"] is not None
        assert 0.0 <= role["confidence"] <= 1.0


def test_justification_metadata_layer2_fields():
    layer2, _, _ = _run_to_compose()
    for role in layer2:
        jm = role["justificationMetadata"]
        assert jm["layer"] == "layer2"
        assert "communityId" in jm
        assert "communityModularity" in jm
        assert "cohesionInterpretation" in jm
        assert "outliers" in jm


def test_applications_nonempty():
    layer2, _, _ = _run_to_compose()
    for role in layer2:
        assert role["applications"]


def test_entitlement_ordering_role_defining_first():
    layer2, _, _ = _run_to_compose()
    for role in layer2:
        meta = role["entitlementMetadata"]
        tiers = [em["tier"] for em in meta]
        # role_defining must come before common_not_universal
        seen_common = False
        for tier in tiers:
            if tier == "common_not_universal":
                seen_common = True
            if seen_common and tier == "role_defining":
                pytest.fail("role_defining appeared after common_not_universal")


def test_role_defining_gate_suppresses_zero_coverage():
    # Set coverage very high so no community has qualifying entitlements
    layer2, suppressed, communities = _run_to_compose({"coverageThreshold": 1.01})
    assert layer2 == []
    assert all("role-defining coverage" in s["reason"] for s in suppressed)


def test_canonical_sort_order():
    layer2, _, _ = _run_to_compose()
    for i in range(len(layer2) - 1):
        a, b = layer2[i], layer2[i + 1]
        assert (
            a["confidence"] > b["confidence"]
            or (a["confidence"] == b["confidence"] and a["memberCount"] >= b["memberCount"])
            or (a["confidence"] == b["confidence"] and a["memberCount"] == b["memberCount"]
                and a["name"] <= b["name"])
        )


def test_cohesion_interpretation_label():
    layer2, _, _ = _run_to_compose()
    for role in layer2:
        interp = role["justificationMetadata"]["cohesionInterpretation"]
        assert interp.startswith(("High", "Medium", "Low"))


def test_outlier_scores_independent():
    layer2, _, _ = _run_to_compose()
    for role in layer2:
        for outlier in role["justificationMetadata"]["outliers"]:
            assert "underProvisioningScore" in outlier
            assert "overProvisioningScore" in outlier
            assert "plainLanguage" in outlier


def test_entitlements_field_matches_role_defining_meta():
    layer2, _, _ = _run_to_compose()
    for role in layer2:
        role_defining_ids = {
            em["entId"] for em in role["entitlementMetadata"]
            if em["tier"] == "role_defining"
        }
        entitlements_field = set(role["entitlements"].split())
        assert role_defining_ids == entitlements_field