# Windows VM sandbox pool (D4)

Engineering goals with `workspace_mode: windows` route **builder.compile** and **tester.run** to volunteers advertising:

- `sandbox.windows.build` — compile-check inside a Windows VM
- `sandbox.windows.test` — pytest inside the same VM pool
- `sandbox.windows` — legacy umbrella for hosts that run both roles

Codewriter still patches the local engineering-lab fixture on a trusted host; only compile/run execute in the VM. **Never run untrusted `.exe` on bare-metal volunteer OS.**

## Quick start (mock, no Hyper-V)

```powershell
$env:AGENTSWARM_REPO_ROOT = (Get-Location)
$env:AGENTSWARM_WINDOWS_SANDBOX_MOCK = "1"
.\scripts\run_windows_sandbox_engineering.ps1
```

Mock mode returns sandbox-shaped results (`windows_vm: true`, `mock: true`) for local dev and CI.

## Hyper-V pool

1. Create a Windows guest VM (e.g. `agentswarm-sandbox-win`) with Python 3.12+ and `pytest` installed.
2. Enable Hyper-V on the host and guest integration services (`Copy-VMFile` / `Invoke-Command -VMName`).
3. Configure the volunteer host:

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENTSWARM_WINDOWS_VM_NAME` | `agentswarm-sandbox-win` | Hyper-V VM to use |
| `AGENTSWARM_WINDOWS_GUEST_WORKDIR` | `C:\agentswarm\workspace` | Guest working directory |
| `AGENTSWARM_WINDOWS_SANDBOX` | — | `1` when running `start_task` / staging scripts |
| `AGENTSWARM_WINDOWS_SANDBOX_MOCK` | — | `1` to skip Hyper-V (dev/CI) |
| `AGENTSWARM_WINDOWS_SNAPSHOT_NAME` | — | Checkpoint to restore before each sandbox run |
| `AGENTSWARM_WINDOWS_NETWORK_ISOLATED` | `1` | Disable VM NICs during compile/run (re-enabled after) |

4. Register workers with `sandbox.windows.build` and `sandbox.windows.test` (or umbrella `sandbox.windows`).

```powershell
.\scripts\run_windows_sandbox_engineering.ps1
```

## Task file

```text
---
goal_kind: engineering
fixture: winhello
workspace_mode: windows
---
Build hello.exe in the Windows VM sandbox and run it natively.
```

`winhello` uses PyInstaller in the guest to produce `hello.exe`, then runs the binary in the tester step. Use `primes` for a lighter Python-only path.

```text
---
goal_kind: engineering
fixture: primes
workspace_mode: windows
---
```

## Cross-compile alternative

When the target is Windows but the build toolchain is Linux-only, prefer `workspace_mode: sandbox` (Linux Docker) for compile and reserve `windows` mode for run-only fixtures — or add `cross_compile_target: linux` in a future slice. Until then, document the split explicitly per goal.

## Coordinator chain

`codewriter.patch` → `builder.compile` (`sandbox.windows.build`) → `tester.run` (`sandbox.windows.test`) → `reviewer.approve`

High-risk goals still apply VRAM gates and N-way reviewer replication on the reviewer step.
