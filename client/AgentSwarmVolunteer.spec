# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

repo_root = Path(SPECPATH).resolve().parent
agents_src = repo_root / "agents" / "src"

a = Analysis(
    [str(agents_src / "agentswarm_agents" / "volunteer_gui.py")],
    pathex=[str(agents_src), str(repo_root / "platform" / "src")],
    binaries=[],
    datas=[
        (
            str(agents_src / "agentswarm_agents" / "model_allowlist.json"),
            "agentswarm_agents",
        )
    ],
    hiddenimports=[
        "agentswarm_agents",
        "agentswarm_agents.volunteer_client",
        "agentswarm_agents.model_allowlist",
        "agentswarm_platform.assignment_signing",
        "agentswarm_platform.coordinator_plan",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
