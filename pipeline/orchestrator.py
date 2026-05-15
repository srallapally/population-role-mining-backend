# backend/pipeline/orchestrator.py
from datetime import datetime, timezone

from data import store
from pipeline.filter_population import filter_population
from pipeline.build_sparse_matrix import build_sparse_matrix
from pipeline.compute_universal import compute_universal
from pipeline.build_similarity_graph import build_similarity_graph
from pipeline.detect_communities import detect_communities
from pipeline.compose_roles import compose_roles


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stop_if_cancelled(session_id: str) -> bool:
    if not store.is_cancel_requested(session_id):
        return False
    now = _now()
    store.mark_session_cancelled(session_id, now)
    store.cleanup_cancelled_session(session_id, now)
    return True


def run_pipeline(session_id: str) -> None:
    """Entry point called in a background thread by POST /sessions/:id/run."""
    session = store.get_session(session_id)
    if not session:
        return

    params = session["parameters"]
    role_type = params["roleType"]

    try:
        # Step 1
        population_ids, population_summary = filter_population(
            params["filterCriteria"], params["maxPopulation"]
        )
        if _stop_if_cancelled(session_id):
            return

        # Step 2
        matrix, entitlement_index, dropped_count = build_sparse_matrix(
            population_ids, params["noiseFilterValue"]
        )
        if _stop_if_cancelled(session_id):
            return

        # Step 3
        layer1_roles, residual, high_residual = compute_universal(
            matrix, entitlement_index, population_ids,
            session_id, params, population_summary
        )
        if _stop_if_cancelled(session_id):
            return

        if role_type == "birthright":
            # Write Layer 1 roles only
            layer1_roles_sorted = sorted(
                layer1_roles,
                key=lambda r: (r["applications"][0]["appName"] if r["applications"] else "", r["id"])
            )
            for role in layer1_roles_sorted:
                store.put_role(role)

            session = store.get_session(session_id)
            session["status"] = "complete"
            session["completedAt"] = _now()
            session["updatedAt"] = _now()
            session["populationSize"] = len(population_ids)
            session["totalEntitlementsConsidered"] = matrix.shape[1] + dropped_count
            session["totalEntitlementsDropped"] = dropped_count
            session["layer1RoleIds"] = [r["id"] for r in layer1_roles_sorted]
            session["layer1RoleCount"] = len(layer1_roles_sorted)
            session["highResidualPrevalenceEntitlements"] = high_residual
            session["populationSummary"] = population_summary
            session["lastUpdatedBy"] = "system"
            store.put_session(session)
            return
        
        # Step 4
        adjacency, graph_metrics = build_similarity_graph(
            residual, params["similarityThreshold"]
        )
        if _stop_if_cancelled(session_id):
            return

        # Step 5
        communities, suppressed_communities, modularity = detect_communities(
            adjacency, population_ids,
            params["minGroupSize"], params["maxRoles"]
        )
        if _stop_if_cancelled(session_id):
            return

        # Step 6
        layer2_roles, suppressed_roles = compose_roles(
            communities, residual, entitlement_index, population_ids,
            modularity, session_id, params, population_summary
        )
        if _stop_if_cancelled(session_id):
            return

        all_suppressed = suppressed_communities + suppressed_roles
        population_summary["suppressedCommunities"] = all_suppressed

        # Atomic write: Layer 1 roles first, then Layer 2, then session
        layer1_roles_sorted = sorted(
            layer1_roles,
            key=lambda r: (r["applications"][0]["appName"] if r["applications"] else "", r["id"])
        )
        for role in layer1_roles_sorted:
            store.put_role(role)

        for role in layer2_roles:
            store.put_role(role)

        session = store.get_session(session_id)
        session["status"] = "complete"
        session["completedAt"] = _now()
        session["updatedAt"] = _now()
        session["populationSize"] = len(population_ids)
        session["totalEntitlementsConsidered"] = matrix.shape[1] + dropped_count
        session["totalEntitlementsDropped"] = dropped_count
        session["layer1RoleIds"] = [r["id"] for r in layer1_roles_sorted]
        session["layer1RoleCount"] = len(layer1_roles_sorted)
        session["candidateRoleIds"] = [r["id"] for r in layer2_roles]
        session["candidateRoleCount"] = len(layer2_roles)
        session["singletonCount"] = graph_metrics["singletonCount"]
        session["graphMetrics"] = graph_metrics
        session["highResidualPrevalenceEntitlements"] = high_residual
        session["populationSummary"] = population_summary
        session["lastUpdatedBy"] = "system"
        store.put_session(session)

    except Exception as exc:
        session = store.get_session(session_id)
        if session:
            if session.get("status") in {"cancelling", "cancelled"}:
                now = _now()
                store.mark_session_cancelled(session_id, now)
                store.cleanup_cancelled_session(session_id, now)
                return
            session["status"] = "failed"
            session["errorDetail"] = str(exc)
            session["updatedAt"] = _now()
            session["lastUpdatedBy"] = "system"
            store.put_session(session)
