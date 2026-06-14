from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trigger_pages_deploy.py"


def _load_trigger_module():
    spec = importlib.util.spec_from_file_location("trigger_pages_deploy", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_exits_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_trigger_module()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


def test_workflow_dispatch_via_api_posts_payload() -> None:
    mod = _load_trigger_module()
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request, timeout=30):  # noqa: ARG001
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.headers.get("Authorization")
        return FakeResponse()

    with patch("urllib.request.urlopen", fake_urlopen):
        mod.workflow_dispatch_via_api(
            repo="owner/repo",
            workflow_file="pages.yml",
            ref="main",
            token="secret",
            artifact_ref="sha-abc",
        )

    assert captured["url"] == "https://api.github.com/repos/owner/repo/actions/workflows/pages.yml/dispatches"
    assert captured["body"] == {
        "ref": "main",
        "inputs": {"artifact_ref": "sha-abc"},
    }
    assert captured["auth"] == "Bearer secret"
