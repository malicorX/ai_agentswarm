from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_pages_ready.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_pages_ready", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_reports_not_enabled_on_404(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod.sys, "argv", ["check_pages_ready.py"])
    monkeypatch.setattr(mod, "_fetch_via_gh", lambda _repo: (404, None))

    with patch.object(mod, "_fetch_pages_api", return_value=(404, None)):
        assert mod.main() == 1
    err = capsys.readouterr().err
    assert "not enabled" in err.lower()


def test_main_succeeds_when_pages_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod.sys, "argv", ["check_pages_ready.py"])

    with patch.object(
        mod,
        "_fetch_pages_api",
        return_value=(200, {"html_url": "https://malicorx.github.io/ai_agentswarm"}),
    ):
        assert mod.main() == 0


def test_main_validates_expected_url(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(
        mod.sys,
        "argv",
        [
            "check_pages_ready.py",
            "--expected-url",
            "https://malicorx.github.io/ai_agentswarm",
        ],
    )

    with patch.object(
        mod,
        "_fetch_pages_api",
        return_value=(200, {"html_url": "https://example.github.io/other"}),
    ):
        assert mod.main() == 3
