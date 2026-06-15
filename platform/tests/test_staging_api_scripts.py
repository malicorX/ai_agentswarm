from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_SCRIPT = REPO_ROOT / "scripts" / "record_staging_api_url.py"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_staging_api.py"
DISPATCH_VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_dispatch_staging.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_staging_api_url_updates_docs(tmp_path: Path) -> None:
    mod = _load_module(RECORD_SCRIPT, "record_staging_api_url")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.md").write_text(
        "| **P6.9** | Git-backed coder capsule | Done |\n"
        "  - [ ] Optional: platform on VPS with HTTPS\n",
        encoding="utf-8",
    )
    (docs / "deploy.md").write_text(
        "- [ ] Platform runs on VPS with systemd\n"
        "- [ ] HTTPS via reverse proxy\n"
        '- [ ] `GET /health` returns `{"status":"ok"}` on public URL\n'
        "| Platform API | _TBD_ | |\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("| **Public pilot** | pending |\n", encoding="utf-8")
    (docs / "execution-plan.md").write_text("→  P6.10 Staging API on theebie.de\n", encoding="utf-8")

    url = "https://theebie.de/agentswarm/api"
    mod.record_staging_api_url(tmp_path, url, recorded_at="2026-06-15")

    status = (docs / "status.md").read_text(encoding="utf-8")
    assert "P6.10" in status and "Done" in status and url in status
    deploy = (docs / "deploy.md").read_text(encoding="utf-8")
    assert "[x] Platform runs on VPS" in deploy
    assert url in deploy
    assert (docs / "execution-plan.md").read_text(encoding="utf-8").startswith("✅ P6.10")


def test_verify_staging_api_success() -> None:
    mod = _load_module(VERIFY_SCRIPT, "verify_staging_api")
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    health_resp = MagicMock()
    health_resp.json.return_value = {"status": "ok"}
    health_resp.raise_for_status = MagicMock()
    config_resp = MagicMock()
    config_resp.json.return_value = {"assignment_mode": "dispatch"}
    config_resp.raise_for_status = MagicMock()
    mock_client.get.side_effect = [health_resp, config_resp]

    with patch.object(httpx, "Client", return_value=mock_client):
        result = mod.verify_staging_api("https://theebie.de/agentswarm/api")

    assert result == {"health": "ok", "assignment_mode": "dispatch"}


def test_verify_staging_api_rejects_pull_mode() -> None:
    mod = _load_module(VERIFY_SCRIPT, "verify_staging_api")
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    health_resp = MagicMock()
    health_resp.json.return_value = {"status": "ok"}
    health_resp.raise_for_status = MagicMock()
    config_resp = MagicMock()
    config_resp.json.return_value = {"assignment_mode": "pull"}
    config_resp.raise_for_status = MagicMock()
    mock_client.get.side_effect = [health_resp, config_resp]

    with patch.object(httpx, "Client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="dispatch"):
            mod.verify_staging_api("https://theebie.de/agentswarm/api")


def test_verify_dispatch_staging_success() -> None:
    mod = _load_module(DISPATCH_VERIFY_SCRIPT, "verify_dispatch_staging")
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    health_resp = MagicMock()
    health_resp.json.return_value = {"status": "ok"}
    health_resp.raise_for_status = MagicMock()
    config_resp = MagicMock()
    config_resp.json.return_value = {
        "assignment_mode": "dispatch",
        "auth": {"enforced": False},
        "dispatch": {"long_poll_max_sec": 60.0, "long_poll_interval_sec": 0.25},
    }
    config_resp.raise_for_status = MagicMock()
    register_resp = MagicMock()
    register_resp.json.return_value = {"agent_id": "agent_dispatch"}
    register_resp.raise_for_status = MagicMock()
    presence_resp = MagicMock()
    presence_resp.json.return_value = {"status": "idle"}
    presence_resp.raise_for_status = MagicMock()
    pending_resp = MagicMock()
    pending_resp.json.return_value = None
    pending_resp.raise_for_status = MagicMock()
    credits_resp = MagicMock()
    credits_resp.json.return_value = {"balance": 100.0, "enabled": True}
    credits_resp.raise_for_status = MagicMock()

    mock_client.get.side_effect = [health_resp, config_resp, pending_resp, credits_resp]
    mock_client.post.side_effect = [register_resp, presence_resp]

    with patch.object(httpx, "Client", return_value=mock_client):
        result = mod.verify_dispatch_staging("https://theebie.de/agentswarm/api")

    assert result["assignment_mode"] == "dispatch"
    assert result["register"] == "agent_dispatch"
    assert result["assignments_pending"] == "empty"
    assert result["credits_balance"] == "100.0"
