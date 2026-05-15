# Implementation — data/store.py

## Purpose

`store.py` is the in-memory database for the POC. It holds all session and role state in two Python dictionaries and exposes helper functions for session lifecycle transitions, cancellation, cleanup, and role storage.

## Structure

```python
_sessions: dict[str, dict] = {}   # keyed by session UUID
_roles: dict[str, dict] = {}      # keyed by role UUID
_lock = threading.Lock()
```

Writes and lifecycle transitions acquire the lock. Reads currently return the stored dict objects directly, so route and pipeline code must treat returned sessions and roles as live mutable objects and call store helpers consistently when changing lifecycle state.

## Live Dict Caveat

Because reads return live dicts, this mutates stored state immediately:

```python
session = store.get_session(sid)
session["status"] = "running"       # mutates the live stored dict directly
```

For simple fields this is acceptable in the current POC, but lifecycle-sensitive changes should use the atomic helper functions below.

## Atomic Lifecycle Helpers

The store provides specific atomic helpers instead of a generic transition function:

| Function | Purpose |
|---|---|
| `try_put_session_with_limits(session, max_active, max_total)` | Atomically creates a session if both active and total capacity are available |
| `transition_pending_to_running(session_id, updated_at)` | Atomically starts a pending session |
| `request_session_cancel(session_id, updated_at)` | Requests cancellation for pending/running sessions |
| `mark_session_cancelled(session_id, updated_at)` | Marks a running/cancelling session as terminal `cancelled` |
| `cleanup_cancelled_session(session_id, updated_at)` | Deletes generated roles for cancelled sessions and marks cleanup complete |

These helpers check the current status and apply the new state inside the same lock acquisition. This prevents the following race condition:

```
Thread A: reads status="pending" ✓
Thread B: reads status="pending" ✓
Thread A: writes status="running"
Thread B: writes status="running"  ← both threads start the pipeline
```

With `transition_pending_to_running`, only one thread can successfully transition from `pending` to `running`. The second call finds the status is already `running` and returns `None`, which the route handler treats as a 409 conflict.

## Concurrency Cap

`count_running_sessions()` counts sessions currently in `running` or `cancelling` status. This is used by the route handler to enforce `MAX_CONCURRENT_SESSIONS`.

Session creation uses `try_put_session_with_limits()` to enforce `MAX_ACTIVE_SESSIONS` and `MAX_TOTAL_SESSIONS` atomically. Active sessions are `pending`, `running`, and `cancelling`.

## Public API

| Function | Description |
|---|---|
| `get_session(id)` | Returns the session dict, or `None` |
| `put_session(session)` | Stores the session dict |
| `try_put_session_with_limits(session, max_active, max_total)` | Atomic session creation with active and total caps |
| `transition_pending_to_running(id, updated_at)` | Atomic `pending -> running` transition |
| `request_session_cancel(id, updated_at)` | Requests cancellation and returns the transition result |
| `is_cancel_requested(id)` | Returns whether cancellation has been requested |
| `mark_session_cancelled(id, updated_at)` | Marks a session terminal `cancelled` |
| `cleanup_cancelled_session(id, updated_at)` | Deletes roles for a cancelled session and marks cleanup complete |
| `count_running_sessions()` | Returns count of sessions with `running` or `cancelling` status |
| `count_active_sessions()` | Returns count of `pending`, `running`, and `cancelling` sessions |
| `count_sessions()` | Returns total retained session count |
| `list_sessions(status, owner, from_, size)` | Filtered, paginated list of sessions |
| `get_role(id)` | Returns the role dict, or `None` |
| `put_role(role)` | Stores the role dict |
| `list_roles_for_session(session_id)` | Returns all roles for a given session |
| `delete_roles_for_session(session_id)` | Deletes generated roles for a given session |

## POC Limitations

- State is lost on server restart — there is no persistence layer
- Retention is capped by `MAX_TOTAL_SESSIONS`, but there is no automatic old-session eviction policy
- The lock is global — all reads and writes contend on the same lock regardless of which session they concern

These are acceptable constraints for a proof of concept. A production implementation would replace this with a database (e.g. PostgreSQL or Elasticsearch) and remove the need for application-level locking entirely.
