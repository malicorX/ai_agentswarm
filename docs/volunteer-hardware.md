# Volunteer hardware guidance

Minimum and recommended specs for **volunteer clients** running local LLM workloads under dispatch mode. theebie.de does not run inference — all compute is on participant machines ([ROADMAP_CHANGES.md](../ROADMAP_CHANGES.md) invariant N1).

**Related:** [ADR 0007](adr/0007-model-allowlist.md) (curated models) · [deploy.md](deploy.md) (point client at staging)

---

## Role expectations

| Role | Typical capsules | Compute profile |
|------|------------------|-----------------|
| **Creative** | `creative.text` | One generation pass per assignment; moderate context |
| **Reviewer** | `reviewer.subjective` | Rubric scoring + rationale; needs reliable judgment on longer submissions |
| **Coordinator** | `coordinator.decompose` | Deterministic plan by default; optional single-shot Ollama when `AGENTSWARM_COORDINATOR_LLM=1` (ADR 0010) |
| **Coder / tester** | `codewriter.*`, pytest | CPU + disk; Docker optional (`llm-docker-worker-v1`) |

**Reviewers should run the strongest local model the machine can sustain.** Subjective quorum quality depends on reviewer capability more than creative generation does.

---

## By allowlisted model (`model_allowlist.json`)

| Model ID | Runtime | Minimum | Recommended (reviewer) | Notes |
|----------|---------|---------|------------------------|-------|
| `llm-mock-v1` | in-process | Any dev machine | — | No GPU; for CI and protocol testing only |
| `llm-docker-worker-v1` | Docker | 4 GB RAM, Docker Desktop | 8 GB RAM | Worker container runs mock executor today; reserve headroom for future weights |
| `ollama/llama3.2` | Ollama localhost | 8 GB system RAM, CPU inference OK | **8 GB VRAM** (GPU) or 16 GB RAM (CPU) | Pull `llama3.2` in Ollama; endpoint must stay `127.0.0.1` |

### Ollama quick check

```bash
ollama pull llama3.2
curl http://127.0.0.1:11434/api/tags
agentswarm-volunteer --headless --loops 0 --model-id ollama/llama3.2 \
  --base-url https://theebie.de/agentswarm/api
```

If `resolve_executor` reports Ollama unreachable, start the Ollama service before connecting.

---

## VRAM tiers (reviewer-focused)

Use these as **pilot guidance** until production telemetry defines hard gates.

| Tier | VRAM | Example local models | Reviewer suitability |
|------|------|----------------------|--------------------|
| **A — minimum** | 6–8 GB | 3B–7B quant (e.g. Llama 3.2 3B) | Acceptable for short creative text; watch latency |
| **B — recommended** | 12–16 GB | 7B–13B quant | Good default for subjective rubric work |
| **C — strong** | 24 GB+ | 13B+ or multi-sample review | Best quorum signal; prefer for high-stakes goals |

**RAM:** add **8 GB system RAM** beyond VRAM footprint when using GPU offload, or **16 GB+** for CPU-only Ollama.

**Disk:** 10–20 GB free per pulled Ollama model; Docker worker images ~1 GB.

**Network:** stable uplink for dispatch long-poll and submission; inference stays local.

---

## Platform enforcement

When `AGENTSWARM_MODEL_ALLOWLIST_ENFORCE=1`, presence heartbeats with unknown `model_id` are rejected. Volunteers must select an allowlisted model in the client UI or `--model-id` flag.

When `AGENTSWARM_HARDWARE_GATES_ENFORCE=1`, reviewer presence must include self-reported `vram_gb` at or above `hardware.reviewer_min_vram_gb` on `/platform/config` (default **6 GB**, or per-model `min_vram_gb` when higher). The dispatcher skips reviewers that do not meet the bar. Creative and coordinator roles are not VRAM-gated in v1.

Volunteer clients report `vram_gb` on heartbeat (`AGENTSWARM_VRAM_GB` env, `--vram-gb`, or **8 GB default** for reviewer capability). Staging hardening: `bash scripts/harden_staging_hardware_gates_theebie.sh`.

---

## Operator checklist

1. Volunteer installs Ollama (or Docker for `llm-docker-worker-v1`) **before** first connect.
2. Pick `model_id` matching installed runtime; creative agents can use tier A; reviewers should target tier B+.
3. Register with owner JWT or maintainer bootstrap token ([production-hardening.md](production-hardening.md)).
4. Heartbeat `model_id` on every presence update so dispatch can match capability.
