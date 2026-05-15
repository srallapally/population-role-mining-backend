# Implementation — data/store.py

## Purpose

`store.py` is the in-memory database for the POC. It holds all session and role state in two Python dictionaries and exposes a thread-safe interface for reading and writing them.

## Structure

```python
_sessions: dict[str, dict] = {}   # keyed by session UUID
_roles: dict[str, dict] = {}      # keyed by role UUID
_lock = threading.Lock()
```

All writes acquire the lock. All reads return copies of the stored data — never references to the live dicts. This means callers cannot accidentally mutate stored state by modifying the returned object.

## Why Copies Matter

Without copying, this would be unsafe:

```python
session = store.get_session(sid)
session["status"] = "running"       # mutates the live stored dict directly
```

With copying, `get_session` returns a new dict each time. The caller can modify it freely. To persist changes, the caller must call `put_session()` explicitly. This makes the write intention explicit and prevents silent state corruption from concurrent modifications.

## Atomic Status Transitions

The most important function is `transition_session_status()`:

```python
def transition_session_status(session_id, expected, new, updates=None):
    with _lock:
        s = _sessions.get(session_id)
        if not s or s["status"] != expected:
            return None          # transition rejected
        s = dict(s)
        s["status"] = new
        if updates:
            s.update(updates)
        _sessions[session_id] = s
        return dict(s)
```

This function checks the current status and sets the new status **inside the same lock acquisition**. This prevents the following race condition:

```
Thread A: reads status="pending" ✓
Thread B: reads status="pending" ✓
Thread A: writes status="running"
Thread B: writes status="running"  ← both threads start the pipeline
```

With `transition_session_status`, only one thread can successfully transition from `pending` to `running`. The second call finds the status is already `running` (not `pending`) and returns `None`, which the route handler treats as a 409 conflict.

## Concurrency Cap

`count_running_sessions()` counts sessions currently in `running` status. This is used by the route handler to enforce the `MAX_CONCURRENT_SESSIONS` limit. Because the count check and the status transition are separate operations, there is a narrow race window where two sessions could both pass the count check before either transitions. For the POC this is acceptable. A production implementation would fold the cap check into `transition_session_status` under the same lock.

## Public API

| Function | Description |
|---|---|
| `get_session(id)` | Returns a copy of the session dict, or `None` |
| `put_session(session)` | Stores a copy of the session dict |
| `transition_session_status(id, expected, new, updates)` | Atomic status transition — returns updated session or `None` on mismatch |
| `count_running_sessions()` | Returns count of sessions with `status="running"` |
| `list_sessions(status, owner, from_, size)` | Filtered, paginated list of session copies |
| `get_role(id)` | Returns a copy of the role dict, or `None` |
| `put_role(role)` | Stores a copy of the role dict |
| `list_roles_for_session(session_id)` | Returns copies of all roles for a given session |

## POC Limitations

- State is lost on server restart — there is no persistence layer
- Memory grows unboundedly as sessions accumulate — no eviction policy
- The lock is global — all reads and writes contend on the same lock regardless of which session they concern

These are acceptable constraints for a proof of concept. A production implementation would replace this with a database (e.g. PostgreSQL or Elasticsearch) and remove the need for application-level locking entirely.
