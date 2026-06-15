#!/usr/bin/env python3
"""Cancel stale pending pool needs on the platform host (P14.0)."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform" / "src"))

from agentswarm_platform.dispatch_store import (  # noqa: E402
    ensure_dispatch_schema,
    expire_stale_pending_pool_needs,
)

DB = os.environ.get("AGENTSWARM_DB", "/var/lib/agentswarm/agentswarm.db")


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    ensure_dispatch_schema(conn)
    pending_before = conn.execute(
        "SELECT COUNT(*) AS count FROM pool_needs WHERE status = 'pending'"
    ).fetchone()["count"]
    cancelled = expire_stale_pending_pool_needs(conn)
    conn.commit()
    pending_after = conn.execute(
        "SELECT COUNT(*) AS count FROM pool_needs WHERE status = 'pending'"
    ).fetchone()["count"]
    print(
        f"pending_before={pending_before} cancelled={len(cancelled)} pending_after={pending_after}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
