import importlib.util
import os
import subprocess
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "lite_full_suite.py"
SPEC = importlib.util.spec_from_file_location("lite_full_suite_under_test", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def _src_paths():
    return [os.path.join(mod.ROOT, d.replace("/", os.sep)) for d in mod.SRC_DIRS]


def _package_line(name, path):
    return f"{name} {path}"


def _inside_path(name):
    return os.path.join(mod.ROOT, "site-packages", name, "__init__.py")


def _install_fake_run(monkeypatch, responses):
    calls = []

    def fake(args, **kwargs):
        assert kwargs["cwd"] == mod.ROOT
        assert args[0] == "fake-python"
        assert tuple(args[-len(mod.PACKAGES):]) == tuple(mod.PACKAGES)
        returncode, stdout, stderr = responses[len(calls)]
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)

    monkeypatch.setattr(mod.subprocess, "run", fake)


def test_build_env_prepends_src_dirs():
    env = {"PYTHONPATH": "vorher", "X": "1"}

    result = mod.build_env(env)

    assert result["PYTHONPATH"].split(os.pathsep) == _src_paths() + ["vorher"]
    assert result["X"] == "1"
    assert result["PYTHONUTF8"] == "1"
    assert result["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env == {"PYTHONPATH": "vorher", "X": "1"}


def test_build_env_without_pythonpath():
    env = {}

    result = mod.build_env(env)
    parts = result["PYTHONPATH"].split(os.pathsep)

    assert parts == _src_paths()
    assert "" not in parts
    assert env == {}


def test_stray_reports_outside(monkeypatch):
    outside = os.path.join(
        os.path.dirname(mod.ROOT), "anderer-checkout", "agentswarm_sdk", "__init__.py"
    )
    lines = [
        _package_line(mod.PACKAGES[0], _inside_path(mod.PACKAGES[0])),
        _package_line(mod.PACKAGES[1], _inside_path(mod.PACKAGES[1])),
        _package_line(mod.PACKAGES[2], _inside_path(mod.PACKAGES[2])),
        _package_line(mod.PACKAGES[3], outside),
    ]
    _install_fake_run(monkeypatch, [(0, "\n".join(lines) + "\n", "")])

    assert mod.stray_packages("fake-python", {}) == [lines[3]]


def test_stray_reports_prefix_sibling(monkeypatch):
    sibling = os.path.join(
        mod.ROOT + "-kopie", "agentswarm_platform", "__init__.py"
    )
    line = _package_line(mod.PACKAGES[0], sibling)
    _install_fake_run(monkeypatch, [(0, line + "\n", "")])

    assert mod.stray_packages("fake-python", {}) == [line]


def test_stray_empty_when_all_inside(monkeypatch):
    lines = [
        _package_line(name, _inside_path(name)) for name in mod.PACKAGES
    ]
    _install_fake_run(monkeypatch, [(0, "\n".join(lines) + "\n", "")])

    assert mod.stray_packages("fake-python", {}) == []


def test_stray_import_failure(monkeypatch):
    _install_fake_run(
        monkeypatch,
        [
            (1, "", "ModuleNotFoundError: x"),
            (1, "", ""),
        ],
    )

    assert mod.stray_packages("fake-python", {}) == ["ModuleNotFoundError: x"]
    assert mod.stray_packages("fake-python", {}) == ["import failed"]
