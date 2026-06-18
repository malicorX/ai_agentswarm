# Distributed clients — architecture & roadmap

**Status:** design / pre-implementation  
**Date:** 2026-06-17 (updated)  
**North star:** Volunteers spread worldwide collaborate on the **same goal**, without sharing disks, without reading each other’s unrelated tasks, with **verifiable compile → run → test** results — **without compromising volunteer machines**.

This document answers: *How do remote clients share code? How do we compile, run, and test safely? What else must the platform solve?*

---

## 0. Non-negotiable requirements

These are **project requirements**, not future nice-to-haves:

| # | Requirement |
|---|-------------|
| N1 | **Coding** — source changes are handed off between roles (git ref per goal). |
| N2 | **Compiling** — produce binaries/artifacts from that source in a **controlled toolchain**. |
| N3 | **Running** — execute produced artifacts to observe behaviour. |
| N4 | **Testing** — assert outputs (exit code, files, stdout digest) against `verification_spec`. |
| N5 | **Safety** — untrusted code from other volunteers must **not** run on the host OS outside an isolation boundary. Volunteers must not get hacked by malicious submissions. |

**Corollary:** `engineering-lab` local fixtures (`AGENTSWARM_REPO_ROOT` on one laptop) remain **demos only**. Production-shaped engineering goals use **git workspace + sandbox execution**.

**Corollary:** “Subprocess with a timeout on the host” is **not** an acceptable security model for global untrusted code. Acceptable boundaries: **OCI container** (Linux v1), **VM / microVM** (Windows and high-assurance v2).

---

## 1. Supported task classes

Restricting scope **does** help — but only if “coding” is defined precisely.

### Class A — `creative` (writing)

Poems, documentation, books (chapter-per-goal), marketing copy.

| Chain | `coordinator → creative.text → reviewer.subjective` |
| Handoff | Text on platform (`artifact_text`) — **no git, no sandbox** |
| Distributed | **Easy** — works today in principle; polish dispatch + trace UI |

Creative tasks do **not** satisfy N1–N4; they are a parallel track, not a substitute for engineering.

### Class B — `engineering` (coding + compile + run + test)

The **definitive** product path. Full pipeline:

`coordinator → codewriter → builder → tester (sandbox run) → reviewer`

| Step | Where it runs | Isolation |
|------|---------------|-----------|
| codewriter | Any volunteer | Git push only — **no compile/run on host** |
| builder | **Sandbox-capable host only** | Inside container/VM |
| tester | **Sandbox-capable host only** | Inside container/VM |
| reviewer | Any volunteer | Reads hashes/logs/spec — **no execution** |

### Class C — deferred

| Class | Why deferred |
|-------|----------------|
| Production deploy on every task | Separate `deploy.approve` / `deploy.execute` after verified `artifact_ref` |
| Arbitrary language/toolchain | Start with fixed images (Python, Rust on Linux) |
| Windows `.exe` on random home PCs | Requires **Windows VM pool** or trusted sandbox hosts (Phase D4) |

---

## 2. Recommendation (read this first)

**Do not rely on a single private monorepo that every client clones.** That couples all tasks and leaks context across goals.

**Do not rely on “everyone patches `AGENTSWARM_REPO_ROOT` on one laptop.”** Local demos only.

### Preferred model: **goal-scoped git + sandbox execution + platform artifact ledger**

| Layer | Responsibility |
|-------|----------------|
| **Platform (theebie)** | Goals, dispatch, leases, audit, **artifact metadata** (git SHA, blob hash, log digests). Mint scoped forge tokens. |
| **Per-goal git workspace** | Private branch namespace `agentswarm/goal-<id>/*`. Codewriter pushes; builder/tester clone **at `workspace_ref` inside sandbox**. |
| **Sandbox worker** | **Only** hosts with `sandbox.linux` (etc.) run compile/run. Ephemeral container per task; destroyed after submit. |
| **Submitted results** | `git_artifact`, `build_artifact`, `run_artifact` — hashes + bounded logs + exit codes. |

**Private git:** Per goal or per project branch, credentials scoped at claim time. Volunteers never see other goals’ repos.

**Deploy (two meanings):**

| Meaning | Role |
|---------|------|
| **Verification run** | Tester runs artifact in sandbox → N3, N4, N5. **Required.** |
| **Production deploy** | `deploy.approve` / `deploy.execute` after quorum. **Later.**

### Volunteer safety model

```
┌─────────────────────────────────────────────────────────────┐
│  Volunteer host (Docker installed, opted in)                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  ephemeral container  (--network=none, memory/cpu cap)│  │
│  │    git clone @ workspace_ref                          │  │
│  │    compile → run tests → collect outputs              │  │
│  └───────────────────────────────────────────────────────┘  │
│  Host never executes untrusted binary directly.              │
└─────────────────────────────────────────────────────────────┘
```

Volunteers **without** sandbox capability may still run: `coordinator`, `codewriter` (git only), `reviewer`, `creative`. They never receive compile/run assignments.

### Alternatives considered

| Approach | Verdict |
|----------|---------|
| Shared NFS / SMB | Bad for global untrusted volunteers |
| Docker-only, no git | Poor multi-step code handoff |
| Host subprocess “MVP” | **Rejected** for untrusted code — fails N5 |
| **Git per goal + OCI sandbox + artifact attestations** | **Required architecture** |

---

## 3. What exists today (baseline)

### Works locally (single machine — not the target model)

- `start_task` / `run_task_staging`: four threads, one `AGENTSWARM_REPO_ROOT`.
- Engineering-lab: patch `pilot/engineering-lab/<fixture>/`; `pytest` on host filesystem.
- Platform: goals, dispatch, trace API, assignment leases.
- `git_capsule.py`: clone → patch → push (v1, not wired as default engineering path).
- `demo_distributed_engineering_goal.py`: multi-host SSH sketch (local_fixture).
- `demo_distributed_engineering_git.py`: sparky1=coordinator+tester, sparky2=codewriter (git handoff).
- `demo_distributed_engineering_git.py --git-in-container`: D6 — sandbox tester on sparky1, codewriter git on sparky2.

### Missing for N1–N5 globally

- Per-goal git provisioning + scoped credentials
- **Sandbox executor** (container lifecycle on worker)
- `builder` role in coordinator plan (compile separated from codewriter)
- `build_artifact` / `run_artifact` schemas + blob upload
- Capability `sandbox.linux` + dispatch routing
- Trace UI: workspace ref, build/run phase, sandbox host
- No execution of untrusted code on volunteer host OS

---

## 4. Problem taxonomy

### 4.1 Workspace & code visibility

| Problem | Requirement |
|---------|-------------|
| Same problem, many machines | Converge on **one `workspace_ref` (commit SHA)** per goal |
| Task isolation | Scoped forge creds per goal |
| Untrusted codewriters | Signed submits; reviewer quorum; canaries |

### 4.2 Compile (N2)

| Problem | Requirement |
|---------|-------------|
| Toolchain control | Pinned OCI images: `ghcr.io/agentswarm/builder-rust:…` |
| Reproducibility | Image digest + input SHA + output hashes in submit |
| Where it runs | **Inside sandbox only**, on `sandbox.linux` agents |
| Limits | Lease TTL, max duration, max artifact size |

### 4.3 Run & test (N3, N4)

| Problem | Requirement |
|---------|-------------|
| Malicious binary | **Never on host** — run inside same or fresh container |
| Capture | exit code, stdout/stderr digests, output file hashes (bounded) |
| Spec | `verification_spec` on goal: expected exit code, file hashes, pytest |
| Flaky tests | Retry policy; full log digest for reviewer |

### 4.4 Safety (N5)

| Threat | Mitigation |
|--------|------------|
| RCE via submitted binary | Container/VM, no host exec |
| Network exfil | `--network=none` default; allowlist egress only if spec requires |
| Resource exhaustion | CPU/RAM/disk/time limits; OOM kill |
| Forge token theft | Inject at claim into container env; revoke after lease |
| Supply chain in image | Pin digests; periodic image rebuild |
| Escaped container | v2: microVM; route high-risk goals to hardened pool |

### 4.5 Platform & UX

| Problem | Requirement |
|---------|-------------|
| Handoff | `workspace_ref` + `artifact_ref` chain in payloads |
| Live visibility | Trace: active role, client, phase (code / build / run / review) |
| Opt-in execution | Presence advertises `sandbox.linux`; dispatch respects it |

---

## 5. Target architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Platform (theebie)                        │
│  goals · dispatch · leases · audit · artifact registry (meta)   │
│  mint scoped forge tokens · route sandbox tasks to capable agents │
└───────────────┬───────────────────────────────┬─────────────────┘
                │                               │
     claim (git creds)                 claim (workspace_ref + sandbox)
                │                               │
    ┌───────────▼──────────┐        ┌───────────▼──────────┐
    │ codewriter           │        │ builder + tester      │
    │ anywhere · git only  │        │ sandbox.linux ONLY    │
    └───────────┬──────────┘        └───────────┬──────────┘
                │         per-goal git           │
                └──────────────┬─────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │ OCI container (ephemeral)    │
                │  clone · compile · run · test│
                │  submit hashes · destroy     │
                └─────────────────────────────┘
                ┌──────────────▼──────────────┐
                │ reviewer · anywhere        │
                │ approves against spec      │
                └────────────────────────────┘
```

### 5.1 Per-goal git workspace

1. Goal created with `workspace: { mode: git, … }`.
2. Branch `agentswarm/goal-<goal_id>` (or dedicated private repo).
3. Codewriter pushes; each submit returns `git_artifact.commit_sha`.
4. Builder/tester receive `workspace_ref`; clone **inside container**.

### 5.2 Build + run inside sandbox (single executor module)

Builder and tester may be **one sandbox invocation** for v1 (compile then `pytest` in same container) or **two tasks** for clearer trace (builder → tester).

**Build submit:**

```json
{
  "git_artifact": { "commit_sha": "…" },
  "build_artifact": {
    "image_digest": "sha256:…",
    "outputs": [{ "path": "target/release/foo", "sha256": "…", "bytes": 12345 }],
    "log_digest": "sha256:…"
  }
}
```

**Run/test submit:**

```json
{
  "run_artifact": {
    "artifact_ref": "sha256:…",
    "passed": true,
    "exit_code": 0,
    "stdout_digest": "sha256:…",
    "output_files": [{ "name": "out.json", "sha256": "…" }]
  }
}
```

Large blobs → `POST /artifacts` → store hash + URL; platform never holds unbounded binary in SQLite.

### 5.3 Example: compile, run, verify (Linux v1)

| Step | Role | Sandbox? |
|------|------|----------|
| 1 | coordinator | No |
| 2 | codewriter | No (git push only) |
| 3 | builder | **Yes** — `cargo build --release` |
| 4 | tester | **Yes** — run binary + collect outputs |
| 5 | reviewer | No |

Windows `.exe`: Phase D4 (VM pool), not home PCs.

---

## 6. Phased roadmap (reordered for N1–N5)

Phases are sequential. **D2 is the safety milestone** — do not treat sandbox as optional.

### Phase D0 — Git workspace handoff

**Goal:** Two+ machines share code via git, not shared folder. **No sandbox yet** (trusted hosts only during D0 dev).

- [x] Goal field: `workspace: { mode: git, repo_url, branch_prefix }`
- [x] Platform: `workspace_ref` on goal after each submit
- [x] Coordinator: pass `parent_git_artifact` / `workspace_ref` in payloads
- [x] Codewriter: `git_capsule` for engineering goals (replace default fixture path)
- [x] Trace API: `workspace_ref` per step
- [x] Demo: sparky1 + sparky2 on same private branch (`demo_distributed_engineering_git.ps1`; seed via `init_git_workspace_staging.ps1`; forge deploy keys + `forge_git_shell.sh` verified staging)

**Exit:** Distributed **source** handoff works. Compile/run still trusted-environment only.

### Phase D1 — Scoped secrets

- [x] Per-goal deploy keys (optional `AGENTSWARM_FORGE_MINT_KEYS=1`; ed25519 in `forge_store.py`)
- [x] Creds in claim response only (`forge_credentials` on `AssignmentEnvelope`; TTL via lease `expires_at`)
- [x] Branch ACL: client enforces `branch_prefix` on push (`commit_and_push`)
- [x] Install forge public keys on bare repo host (`install_forge_deploy_keys_staging.ps1` + `forge_git_shell.sh`; optional auto via `AGENTSWARM_FORGE_AUTO_INSTALL_KEYS=1` in `forge_deploy_keys.py`)

**Exit:** Volunteers cannot access other goals’ repos.

### Phase D2 — Linux sandbox: compile + run + test (CORE)

**This phase satisfies N2, N3, N4, N5 for Linux engineering goals.**

- [x] Capabilities `sandbox.build` + `sandbox.test` (legacy umbrella `sandbox.linux` for single-worker hosts)
- [x] Dispatch: `builder.compile` → `sandbox.build`; `tester.run` (sandbox) → `sandbox.test`
- [x] Worker module: `sandbox_executor.py` — create container, mount/ephemeral workspace, run command graph, collect outputs, destroy
- [x] Container defaults: `--network=none`, memory/CPU/pids limits, read-only root where feasible
- [x] Pinned builder images (Python pytest, Rust cargo)
- [x] `build_artifact` + `run_artifact` submit schemas (partial: `run_artifact` digest in sandbox result)
- [x] Blob upload API for outputs + log bundles (`POST /artifacts`, `GET /artifacts/{sha256:…}`)
- [x] Coordinator plan: codewriter → builder → tester → reviewer (sandbox: `builder.compile` in Docker before `tester.run`)
- [x] Trace UI: phase labels, sandbox host owner, artifact hashes (phase badges, sandbox host, log bundle link in console)
- [x] Engineering-lab fixtures: run **inside container** for CI parity, or retire as default

**Exit:** Malicious code in a goal cannot escape container on a Linux sandbox volunteer; platform records hashes; goal reaches `verified` through full chain.

### Phase D3 — Hardening & operator scale

- [x] seccomp / AppArmor profiles for containers (`seccomp-sandbox.json`, `cap-drop=ALL`, workspace `:ro` mount + `/tmp` tmpfs; opt-in AppArmor via `AGENTSWARM_SANDBOX_APPARMOR`)
- [x] Content-addressed blob cache (`store_artifact_blob` dedupe + `cached` on `POST /artifacts`)
- [x] Lease recovery + idempotent sandbox runs (`maintain_dispatch_pool` on idle heartbeat; named containers per `task_id` for reclaim-safe reruns)
- [x] Optional platform-hosted Gitea + MinIO on theebie (`install_optional_gitea_minio_staging.ps1` + compose; localhost-only demo stack)
- [x] Log bundle download in task console (view link + **Download** in modal)
- [x] Reviewer hardware gates for high-risk goals (`verification_spec.risk_level: high` → `min_reviewer_vram_gb` 12 GB default)
- [x] N-way reviewer replication for high-risk engineering goals (`replication: {slots: 2, quorum: 2}` on deferred reviewer pool needs; goal resolves on quorum/dispute)

**Exit:** Production-grade ops, not just demo security.

### Phase D4 — Windows / VM execution

- [x] `sandbox.windows` capability family (`sandbox.windows.build`, `sandbox.windows.test`, legacy umbrella)
- [x] Coordinator routing for `workspace_mode: windows` (codewriter → builder → tester → reviewer)
- [x] `windows_sandbox_executor.py` — Hyper-V guest sessions + `AGENTSWARM_WINDOWS_SANDBOX_MOCK` for dev/CI
- [x] Task file + `run_windows_sandbox_engineering.ps1` + `docs/infra/windows-vm-sandbox.md`
- [x] Snapshot revert before runs (`AGENTSWARM_WINDOWS_SNAPSHOT_NAME`)
- [x] Guest network isolation during runs (`AGENTSWARM_WINDOWS_NETWORK_ISOLATED`, default on)
- [x] `winhello` fixture — PyInstaller `hello.exe` build + native run in VM

**Exit:** N1–N5 on Windows targets without asking random volunteers to run `.exe` on their laptop.

### Phase D5 — Production deploy (separate track)

- [x] Verified goals snapshot `artifact_refs` + `primary_artifact_ref` on `resolve_goal(verified)`
- [x] `POST /creative/goals/{goal_id}/deploy-request` → sign-off quorum → `deploy.execute` (reuses deploy pipeline)
- [x] `POST /deploy/requests` accepts optional `goal_id`; validates sha256 blobs when `AGENTSWARM_DEPLOY_REQUIRE_ARTIFACT_BLOB=1`
- [x] Deploy requests link back to source goal (`goal_id` column)
- [x] `scripts/request_deploy_from_goal.ps1` for staging operators

**Exit:** Production deploy is decoupled from verification sandbox but shares the artifact registry.

### Phase D6 — Git-in-container

- [x] `git_in_container: true` with `workspace_mode: git` — codewriter patch + tester clone in sandbox image
- [x] `git_sandbox_executor.py` mounts agents source + `file://` bare repos; network `bridge` for remote forges
- [x] `AGENTSWARM_GIT_SANDBOX_MOCK=1` for dev/CI; task file `example-primes-git-sandbox.txt`

**Exit:** Host orchestrates Docker only; git never runs on volunteer OS for git-in-container goals.

---

## 7. Component map (codebase)

| Area | Status |
|------|--------|
| `git_capsule.py` + forge keys | Git handoff across machines (D0/D1) |
| `git_sandbox_executor.py` | Git clone/patch/test inside Linux sandbox (D6) |
| `sandbox_executor.py` | Linux Docker compile/test (D2) |
| `windows_sandbox_executor.py` | Windows VM compile/test scaffold (D4) |
| `coordinator_plan.py` | codewriter → builder → tester → reviewer; sandbox/windows/git modes |
| `goal_artifacts.py` | Verified goal `artifact_refs` → deploy (D5) |
| `deploy_store.py` | Sign-off quorum → `deploy.execute` (separate from verification) |
| Task console | Phase, sandbox host, log bundles, deploy artifact panel |
| Blob registry | `POST/GET /artifacts` shared by sandbox logs and deploy refs |

---

## 8. Open decisions

| # | Question | Lean |
|---|----------|------|
| 1 | Forge default? | Gitea on theebie for demos; GitHub for teams |
| 2 | Blob store? | MinIO (S3-compatible) on theebie |
| 3 | Builder + tester: one container or two? | **One container** for v1; split for trace clarity in v2 |
| 4 | Branch per goal vs repo per goal? | Branch per goal on project repo |
| 5 | Who must install Docker? | Only volunteers opting into `sandbox.linux` |
| 6 | Windows strategy? | VM pool (D4), not bare-metal volunteers |

---

## 9. What not to do

- Run untrusted compile/run on volunteer **host OS** (fails N5).
- Monolithic private repo for all users.
- Ship large binaries inside JSON submits.
- Skip `workspace_ref` in handoffs.
- Conflate verification sandbox with production deploy.

---

## 10. Success criteria

1. Three continents, one engineering goal, **no shared disk** between volunteers.
2. Full chain: **code → compile → run → test → review** with platform `verified`.
3. Malicious submission in test goal **does not compromise** sandbox host (container escape = out of scope for v1 but host exec = in scope).
4. Volunteers without Docker never receive compile/run assignments.
5. Task console shows live role, client, **phase**, `workspace_ref`, output hashes.
6. Creative/writing goals continue to work without sandbox (Class A).

---

## 11. Related docs

- `docs/task-workflow.md` — create/start task (local team today)
- `docs/api.md` — goals, dispatch, deploy requests
- `agents/src/agentswarm_agents/git_capsule.py` — git patch v1
- `scripts/demo_distributed_engineering_goal.py` — multi-host sketch
- `ROADMAP_20260603_153456.md` — historical review (repo has evolved since)

---

## 12. Staging verification

D0–D6 are **complete**. Use these checks after platform deploy:

| Check | Command |
|-------|---------|
| Deploy-from-goal bridge | `.\scripts\deploy_platform_theebie.ps1 -VerifyDeployFromGoal` |
| Full engineering → deploy sign-off e2e | `.\scripts\run_staging_deploy_e2e.ps1 -SignoffChain` |

**Verified on theebie (2026-06):** engineering goal `verified` → `deploy-request` → reviewer sign-off → `approved` in ~30s via `verify_staging_deploy_e2e.py`, using **production** deploy policy (default `min_credibility` / high stake tier). Engineering reviewers receive `mint.engineering_verify` so they can sign deploy requests after verifying a goal.

Weekly CI (`verify-staging-full.yml`) runs engineering verify with deploy sign-off when `AGENTSWARM_ASSIGNMENT_SECRET` is configured.
