# Volunteer client

Production-shaped client for **dispatch mode**: connect to the platform, pick an allowlisted model, download weights on demand, run assignments inside a **Docker worker container**, submit signed results.

**Related:** [ADR 0005](adr/0005-volunteer-client-dispatch.md) · [ADR 0007](adr/0007-model-allowlist.md) · [volunteer-hardware.md](volunteer-hardware.md) · [dispatch-migration.md](dispatch-migration.md) · [task-workflow.md](task-workflow.md)

---

## Architecture

Volunteers do **not** install Ollama or ship weights inside the `.exe`. The client manages two layers:

| Layer | Location | Purpose |
|-------|----------|---------|
| **Weights** | Per-user app data directory | Downloaded GGUF files, verified by SHA-256 |
| **Runtime** | `agentswarm-worker:dev` Docker image | Curated capsule executor + llama.cpp inference |

```text
Volunteer client (GUI or headless)
  → ensure model weights on disk (if allowlist entry has `weight`)
  → docker run --rm --network none
       -v <weights>/model.gguf:/models/weights/model.gguf:ro
       -e AGENTSWARM_MODEL_PATH=/models/weights/model.gguf
       agentswarm-worker:dev
  → stdin: signed assignment JSON
  → stdout: result JSON
  → client submits to platform
```

**Untrusted goal code** (engineering pytest, compile) still runs in a separate **sandbox** container when `workspace_mode` is `sandbox` or `git_in_container` — see [task-workflow.md](task-workflow.md) and [ROADMAP_DISTRIBUTED_CLIENTS.md](../ROADMAP_DISTRIBUTED_CLIENTS.md).

### App data directory

| OS | Default path |
|----|----------------|
| Windows | `%LOCALAPPDATA%\AgentSwarm` |
| macOS | `~/Library/Application Support/AgentSwarm` |
| Linux | `~/.local/share/agentswarm` |

Override: `AGENTSWARM_CLIENT_DATA_DIR`.

Weights live under `models/<model-id>/model.gguf` with a `manifest.json` (SHA-256, size, download time).

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| Python 3.11+ | `pip install -e agents` |
| **Docker Desktop** | Required for `docker` runtime models (`llm-docker-worker-v1`, `docker/qwen2.5-coder-3b`) |
| Disk | ~2 GB per downloaded 3B quant; worker image ~1 GB |
| Network | Stable uplink for dispatch long-poll; inference stays local |

Build the worker image once:

```powershell
.\scripts\build_worker_image.ps1
```

```bash
docker build -f docker/worker/Dockerfile -t agentswarm-worker:dev .
```

---

## Allowlisted models (v3)

Published on `GET /platform/config` → `models.allowlist` (must match `agents/src/agentswarm_agents/model_allowlist.json`).

| Model ID | Runtime | Weights | Use |
|----------|---------|---------|-----|
| `llm-mock-v1` | in-process | — | CI, protocol dev |
| `llm-docker-worker-v1` | docker | — | Docker path with mock LLM (smoke tests) |
| `docker/qwen2.5-coder-3b` | docker | ~2.1 GB GGUF | **Real** creative / reviewer / engineering LLM in container |
| `ollama/llama3.2` | ollama | host Ollama | **Dev only** — requires local Ollama on `127.0.0.1` |

Weighted models download from the URL in the allowlist entry on first **Prepare** or **Start**.

---

## GUI client

```powershell
pip install -e agents
agentswarm-volunteer
```

1. Set **Platform URL** (staging: `https://theebie.de/agentswarm/api`).
2. Pick a **Model** from the allowlist dropdown.
3. Click **Prepare model** to download weights (progress bar).
4. Set **Capabilities** (`creative`, `reviewer`, `codewriter`, etc.).
5. Click **Start**.

Task console (enqueue / watch goals): `.\scripts\serve_task_console.ps1` → http://127.0.0.1:8765

---

## Headless

```powershell
# Download weights only
agentswarm-volunteer --prepare-only --model-id docker/qwen2.5-coder-3b

# One assignment (mock)
agentswarm-volunteer --headless --loops 1 --model-id llm-docker-worker-v1 `
  --capabilities reviewer --base-url https://theebie.de/agentswarm/api
```

Staging auth: run `.\scripts\ensure_staging_env.ps1` or set `AGENTSWARM_BOOTSTRAP_TOKEN` + `AGENTSWARM_ASSIGNMENT_SECRET`.

---

## Staging verification (real LLM)

End-to-end: coordinator → **creative.text** (Qwen in Docker) → **reviewer.subjective** → `verified`.

```powershell
.\scripts\verify_docker_volunteer_staging.ps1
```

This builds the worker image, ensures weights are cached, and runs `demo_volunteer_subjective.py` with `--model-id docker/qwen2.5-coder-3b --isolate-dispatch`.

Maintainer subjective demo (mock or Ollama): `.\scripts\demo_volunteer_subjective_staging.ps1`

---

## Engineering LLM (codewriter)

Inside the worker container, `AGENTSWARM_ENGINEERING_LLM=1` is set automatically for `docker/*` models. The codewriter prompts the mounted GGUF model for implementation text, then applies the engineering-lab patch (or git push in `git` mode).

Fallback to deterministic mock on parse failure keeps demos reliable.

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `AGENTSWARM_CLIENT_DATA_DIR` | Override app data root |
| `AGENTSWARM_MODEL_SKIP_DOWNLOAD` | Require weights already on disk (`1`) |
| `AGENTSWARM_WORKER_IMAGE` | Worker Docker tag (default `agentswarm-worker:dev`) |
| `AGENTSWARM_ENGINEERING_LLM` | Enable LLM codewriter in worker (`1`) |
| `AGENTSWARM_COORDINATOR_LLM` | Optional Ollama/LLM coordinator plan |
| `AGENTSWARM_ALLOWLIST_SKIP` | Dev: skip client allowlist check |
| `AGENTSWARM_VRAM_GB` | Self-reported VRAM on heartbeat (reviewers) |

---

## Adding a model

1. Add entry to **both** `agents/.../model_allowlist.json` and `platform/.../data/model_allowlist.json` (CI checks they match).
2. For docker runtime: set `worker_image`, optional `weight` block (`url`, `filename`, `size_bytes`, `sha256`).
3. Redeploy platform if enforcement is on.
4. Ship updated client / allowlist in agent package.

See [ADR 0007](adr/0007-model-allowlist.md).

---

## Related scripts

| Script | Purpose |
|--------|---------|
| `scripts/build_worker_image.ps1` | Build + smoke-test worker image |
| `scripts/prepare_volunteer_model.ps1` | Download allowlisted weights |
| `scripts/verify_docker_volunteer_staging.ps1` | Staging creative e2e with real LLM |
| `scripts/build_volunteer_exe.ps1` | Windows `.exe` (PyInstaller) |
| `scripts/demo_connect_staging.ps1` | Quick headless connect smoke |
| `scripts/serve_task_console.ps1` | Task console web UI |
