# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for standalone AgentSwarm Volunteer (Windows)."""
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

repo_root = Path(SPECPATH).resolve().parent
agents_src = repo_root / "agents" / "src"

datas: list[tuple[str, str]] = [
    (
        str(agents_src / "agentswarm_agents" / "model_allowlist.json"),
        "agentswarm_agents",
    )
]
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = [
    "agentswarm_agents",
    "agentswarm_agents.volunteer_client",
    "agentswarm_agents.volunteer_work",
    "agentswarm_agents.capsule_executor",
    "agentswarm_agents.model_allowlist",
    "agentswarm_platform.assignment_signing",
    "agentswarm_platform.coordinator_plan",
    "_tkinter",
    "tkinter",
    "tkinter.ttk",
    "tkinter.scrolledtext",
    "tkinter.messagebox",
]

for pkg in ("tkinter", "_tkinter"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Conda-based venvs keep Tcl/Tk DLLs under Library/bin; PyInstaller often misses them.
base = Path(sys.base_prefix)
conda_bin = base / "Library" / "bin"
for dll_name in ("tcl86t.dll", "tk86t.dll", "zlib.dll"):
    dll_path = conda_bin / dll_name
    if dll_path.is_file():
        binaries.append((str(dll_path), "."))

tkinter_pyd = base / "DLLs" / "_tkinter.pyd"
if tkinter_pyd.is_file():
    binaries.append((str(tkinter_pyd), "."))

a = Analysis(
    [str(agents_src / "agentswarm_agents" / "volunteer_gui.py")],
    pathex=[str(agents_src), str(repo_root / "platform" / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tensorflow",
        "torch",
        "torchvision",
        "sklearn",
        "scipy",
        "pandas",
        "matplotlib",
        "notebook",
        "IPython",
        "pytest",
        "test",
        "tests",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AgentSwarmVolunteer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
