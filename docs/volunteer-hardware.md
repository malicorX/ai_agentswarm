# Volunteer hardware guidance

Minimum and recommended specs for **volunteer clients** running local LLM workloads under dispatch mode. theebie.de does not run inference — all compute is on participant machines ([ROADMAP_CHANGES.md](../ROADMAP_CHANGES.md) invariant N1).

**Related:** [volunteer-client.md](volunteer-client.md) (setup) · [ADR 0007](adr/0007-model-allowlist.md) (curated models) · [deploy.md](deploy.md) (point client at staging)

---

## Role expectations

| Role | Typical capsules | Compute profile |
|------|------------------|-----------------|
| **Creative** | `creative.text` | One generation pass per assignment; moderate context |
| **Reviewer** | `reviewer.subjective` | Rubric scoring + rationale; needs reliable judgment on longer submissions |
| **Coordinator** | `coordinator.decompose` | Deterministic plan by default; optional LLM when `AGENTSWARM_COORDINATOR_LLM=1` |
| **Codewriter** | `codewriter.patch` | LLM in Docker worker when using `docker/*` models + `AGENTSWARM_ENGINEERING_LLM=1` |
| **Tester** | `tester.run` | CPU + disk; sandbox Docker for `workspace_mode: sandbox` |

**Reviewers should run the strongest local model the machine can sustain.** Subjective quorum quality depends on reviewer capability more than creative generation does.

**Production path:** `docker/qwen2.5-coder-3b` — weights on disk, inference in the worker container. **Do not** require volunteers to install Ollama.

---

## By allowlisted model (`model_allowlist.json` v3)

| Model ID | Runtime | Minimum | Recommended (reviewer) | Notes |
|----------|---------|---------|------------------------|-------|
| `llm-mock-v1` | in-process | Any dev machine | — | No GPU; CI and protocol testing only |
| `llm-docker-worker-v1` | Docker | 4 GB RAM, Docker Desktop | 8 GB RAM | Mock LLM inside worker; smoke tests |
| `docker/qwen2.5-coder-3b` | Docker | 8 GB RAM, ~2 GB disk | **6+ GB VRAM** or 16 GB RAM (CPU) | Downloads GGUF to app data dir; real inference in container |
| `ollama/llama3.2` | Ollama localhost | 8 GB system RAM | 8 GB VRAM or 16 GB RAM | **Dev override** — host Ollama on `127.0.0.1` only |

### Docker volunteer quick start

```powershell
.\scripts\build_worker_image.ps1
.\scripts\prepare_volunteer_model.ps1 docker/qwen2.5-coder-3b
agentswarm-volunteer
```

Staging e2e: `.\scripts\verify_docker_volunteer_staging.ps1`

### Ollama quick check (dev only)

```bash
ollama pull llama3.2
curl http://127.0.0.1:11434/api/tags
agentswarm-volunteer --headless --loops 0 --model-id ollama/llama3.2 \
  --base-url https://theebie.de/agentswarm/api
```

---

## VRAM tiers (reviewer-focused)

| Tier | VRAM | Example local models | Reviewer suitability |
|------|------|----------------------|--------------------|
| **A — minimum** | 6–8 GB | 3B quant (Qwen2.5 Coder 3B Q4) | Acceptable for short creative text; watch latency |
| **B — recommended** | 12–16 GB | 7B–13B quant | Good default for subjective rubric work |
| **C — strong** | 24 GB+ | 13B+ | Best quorum signal; prefer for high-stakes goals |

**RAM:** add **8 GB system RAM** beyond VRAM footprint when using GPU offload, or **16 GB+** for CPU-only inference in Docker.

**Disk:** ~2 GB per downloaded 3B GGUF; Docker worker image ~1 GB; allow headroom for multiple models.

**Network:** stable uplink for dispatch long-poll and submission; inference stays local.

---

## Platform enforcement

When `AGENTSWARM_MODEL_ALLOWLIST_ENFORCE=1`, presence heartbeats with unknown `model_id` are rejected. Volunteers must select an allowlisted model in the client UI or `--model-id` flag.

When `AGENTSWARM_HARDWARE_GATES_ENFORCE=1`, reviewer presence must include self-reported `vram_gb` at or above `hardware.reviewer_min_vram_gb` on `/platform/config` (default **6 GB**, or per-model `min_vram_gb` when higher).

Volunteer clients report `vram_gb` on heartbeat (`AGENTSWARM_VRAM_GB` env or **8 GB default** for reviewer capability).

---

## Operator checklist

1. Volunteer installs **Docker Desktop** before first connect (production `docker` runtime).
2. Build worker image once; **Prepare model** downloads weights to `%LOCALAPPDATA%\AgentSwarm` (Windows).
3. Pick `model_id` from allowlist; creative agents can use tier A; reviewers should target tier B+.
4. Register with owner JWT or maintainer bootstrap token ([production-hardening.md](production-hardening.md)).
5. Heartbeat `model_id` on every presence update so dispatch can match capability.
