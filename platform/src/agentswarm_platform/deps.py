from __future__ import annotations

from agentswarm_platform.store import Store

_store: Store | None = None


def bind_store(store: Store) -> None:
    global _store
    _store = store


def get_store() -> Store:
    if _store is None:
        raise RuntimeError("platform store is not bound")
    return _store
