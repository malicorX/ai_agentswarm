from __future__ import annotations

import os


def owner_auth_headers() -> dict[str, str]:
    """Headers for owner-authenticated platform calls (register, create task)."""
    owner_token = os.environ.get("AGENTSWARM_OWNER_TOKEN", "")
    if owner_token:
        return {"Authorization": f"Bearer {owner_token}"}
    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "")
    if bootstrap:
        return {"X-Bootstrap-Token": bootstrap}
    return {}
