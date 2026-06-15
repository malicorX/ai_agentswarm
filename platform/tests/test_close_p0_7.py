from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "close_p0_7.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("close_p0_7", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_close_p0_7_fails_when_pages_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    check = mod._load_check()
    monkeypatch.setattr(mod, "_load_check", lambda: check)
    monkeypatch.setattr(check, "probe_pages", lambda: (False, None))
    monkeypatch.setattr(mod.sys, "argv", ["close_p0_7.py"])

    assert mod.main() == 1


def test_close_p0_7_records_url_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    check = mod._load_check()
    monkeypatch.setattr(mod, "_load_check", lambda: check)
    monkeypatch.setattr(
        check,
        "probe_pages",
        lambda: (True, "https://malicorx.github.io/ai_agentswarm"),
    )
    monkeypatch.setattr(
        mod.sys,
        "argv",
        ["close_p0_7.py", "https://malicorx.github.io/ai_agentswarm"],
    )

    with patch.object(mod.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
        assert mod.main() == 0
    assert "record_pages_url" in run.call_args[0][0][1]
