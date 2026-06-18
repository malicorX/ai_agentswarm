"""Volunteer client application data directory (weights, config, caches)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def client_data_dir() -> Path:
    """Return the per-user AgentSwarm data root (created on first use)."""
    override = os.environ.get("AGENTSWARM_CLIENT_DATA_DIR", "").strip()
    if override:
        root = Path(override)
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        root = base / "AgentSwarm"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "AgentSwarm"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "").strip()
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        root = base / "agentswarm"
    root.mkdir(parents=True, exist_ok=True)
    return root


def models_dir() -> Path:
    path = client_data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path
