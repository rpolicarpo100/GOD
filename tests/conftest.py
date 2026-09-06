"""Test configuration — isolate test runs from stale cached state."""


def pytest_configure(config):
    """Flush cache once at session start to avoid stale state from prior runs."""
    try:
        from superai.store import store
        with store._lock, store._conn() as c:
            c.execute("DELETE FROM cache")
    except Exception:
        pass
