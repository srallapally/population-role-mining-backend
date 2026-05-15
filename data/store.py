# backend/data/store.py
import threading
from typing import Optional

_sessions: dict[str, dict] = {}
_roles: dict[str, dict] = {}
_lock = threading.Lock()
ACTIVE_SESSION_STATUSES = {"pending", "running", "cancelling"}
TERMINAL_SESSION_STATUSES = {"complete", "failed", "saved", "cancelled"}


# --- Sessions ---

def get_session(session_id: str) -> Optional[dict]:
    return _sessions.get(session_id)


def put_session(session: dict) -> None:
    with _lock:
        _sessions[session["id"]] = session


def try_put_session_with_limits(
    session: dict, max_active_sessions: int, max_total_sessions: int
) -> Optional[str]:
    """Atomically insert a session if total and active capacity are available."""
    with _lock:
        if len(_sessions) >= max_total_sessions:
            return "total"
        active_count = sum(
            1 for s in _sessions.values()
            if s.get("status") in ACTIVE_SESSION_STATUSES
        )
        if active_count >= max_active_sessions:
            return "active"
        _sessions[session["id"]] = session
        return None


def try_put_session_with_active_limit(session: dict, max_active_sessions: int) -> bool:
    """Atomically insert a session if active-session capacity is available."""
    with _lock:
        active_count = sum(
            1 for s in _sessions.values()
            if s.get("status") in ACTIVE_SESSION_STATUSES
        )
        if active_count >= max_active_sessions:
            return False
        _sessions[session["id"]] = session
        return True


def transition_pending_to_running(session_id: str, updated_at: str) -> Optional[dict]:
    with _lock:
        session = _sessions.get(session_id)
        if not session or session.get("status") != "pending":
            return None
        session["status"] = "running"
        session["updatedAt"] = updated_at
        return session


def request_session_cancel(session_id: str, updated_at: str) -> tuple[Optional[dict], str]:
    with _lock:
        session = _sessions.get(session_id)
        if not session:
            return None, "not_found"

        status = session.get("status")
        if status == "pending":
            session["status"] = "cancelled"
            session["cancelRequested"] = True
            session["cancelledAt"] = updated_at
            session["updatedAt"] = updated_at
            session["cleanupStatus"] = "pending"
            return session, "cancelled"
        if status == "running":
            session["status"] = "cancelling"
            session["cancelRequested"] = True
            session["updatedAt"] = updated_at
            session["cleanupStatus"] = "pending"
            return session, "cancelling"
        if status == "cancelling":
            return session, "cancelling"
        return session, "terminal"


def is_cancel_requested(session_id: str) -> bool:
    session = _sessions.get(session_id)
    return bool(session and session.get("cancelRequested"))


def mark_session_cancelled(session_id: str, updated_at: str) -> Optional[dict]:
    with _lock:
        session = _sessions.get(session_id)
        if not session:
            return None
        session["status"] = "cancelled"
        session["cancelRequested"] = True
        session["cancelledAt"] = updated_at
        session["updatedAt"] = updated_at
        session["cleanupStatus"] = "pending"
        return session


def list_sessions(status: Optional[str] = None, owner: Optional[str] = None,
                  from_: int = 0, size: int = 20) -> list[dict]:
    results = list(_sessions.values())
    if status:
        results = [s for s in results if s.get("status") == status]
    if owner:
        results = [s for s in results if s.get("sessionOwner") == owner]
    results.sort(key=lambda s: s.get("createdAt", ""), reverse=True)
    return results[from_: from_ + size]


def count_running_sessions() -> int:
    return sum(1 for s in _sessions.values() if s.get("status") in {"running", "cancelling"})


def count_active_sessions() -> int:
    return sum(
        1 for s in _sessions.values()
        if s.get("status") in ACTIVE_SESSION_STATUSES
    )


def count_sessions() -> int:
    return len(_sessions)


def clear_all() -> None:
    with _lock:
        _sessions.clear()
        _roles.clear()


# --- Roles ---

def get_role(role_id: str) -> Optional[dict]:
    return _roles.get(role_id)


def put_role(role: dict) -> None:
    with _lock:
        _roles[role["id"]] = role


def list_roles_for_session(session_id: str) -> list[dict]:
    return [r for r in _roles.values() if r.get("sessionId") == session_id]


def delete_roles_for_session(session_id: str) -> int:
    with _lock:
        role_ids = [
            role_id for role_id, role in _roles.items()
            if role.get("sessionId") == session_id
        ]
        for role_id in role_ids:
            del _roles[role_id]
        return len(role_ids)


def cleanup_cancelled_session(session_id: str, updated_at: str) -> Optional[dict]:
    with _lock:
        session = _sessions.get(session_id)
        if not session or session.get("status") != "cancelled":
            return session
        role_ids = [
            role_id for role_id, role in _roles.items()
            if role.get("sessionId") == session_id
        ]
        for role_id in role_ids:
            del _roles[role_id]
        session["cleanupStatus"] = "complete"
        session["cleanedUpAt"] = updated_at
        session.pop("cleanupError", None)
        session["updatedAt"] = updated_at
        return session
