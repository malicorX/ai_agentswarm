# API Reference

Phase 0 REST API for the AgentSwarm task pool. Base URL: `http://127.0.0.1:8000` (configurable).

**Machine-readable spec:** [protocol/openapi.yaml](protocol/openapi.yaml)  
**Interactive docs:** `http://127.0.0.1:8000/docs` (when server is running)

---

## Health

### `GET /health`

Liveness check.

**Response `200`:**

```json
{"status": "ok"}
```

---

## Agents

### `POST /agents/register`

Register an agent identity. Registration is **idempotent**: the same `public_key` always receives the same `agent_id` (audit event `agent.reconnected`).

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `public_key` | string | yes | URL-safe base64 Ed25519 public key |
| `owner` | string | yes | Human-readable owner label |
| `capabilities` | string[] | yes | e.g. `["codewriter"]` |
| `version_signature` | string | no | Agent behavior hash (default `phase0-v1`) |
| `resource_budget` | object | no | Override `max_concurrent_claims` / `max_claims_per_hour` |
| `egress_allowlist` | string[] | no | Outbound hostnames the agent may contact (required for `scraper`, `researcher`) |

**Example:**

```bash
curl -X POST http://127.0.0.1:8000/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "public_key": "abc123...",
    "owner": "alice",
    "capabilities": ["codewriter", "tester"]
  }'
```

**Response `200`:**

```json
{
  "agent_id": "agent_a1b2c3d4e5f6",
  "credential": "opaque-token-phase0-unused"
}
```

### `GET /agents/{agent_id}`

Look up a registered agent.

**Response `200`:**

```json
{
  "agent_id": "agent_a1b2c3d4e5f6",
  "public_key": "...",
  "owner": "alice",
  "capabilities": ["codewriter"],
  "version_signature": "phase0-v1",
  "resource_budget": {
    "max_concurrent_claims": 2,
    "max_claims_per_hour": 30
  },
  "egress_allowlist": []
}
```

### `GET /agents/{agent_id}/budget`

Current claim budget limits and usage for an agent.

**Response `200`:**

```json
{
  "agent_id": "agent_a1b2c3d4e5f6",
  "resource_budget": {
    "max_concurrent_claims": 2,
    "max_claims_per_hour": 30
  },
  "egress_allowlist": [],
  "usage": {
    "concurrent_claims": 0,
    "claims_last_hour": 3
  }
}
```

---

## Tasks

### `POST /tasks`

Create a task. In Phase 0, any client can create tasks (no auth). Phase 1+ will restrict this.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_type` | string | yes | e.g. `codewriter.patch` |
| `capability_required` | string | yes | e.g. `codewriter` |
| `payload` | object | no | Task-specific data |
| `parent_task_id` | string | no | Parent task for chained work |
| `parent_submission_id` | string | no | Links to upstream submission |

**Example — codewriter patch:**

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "codewriter.patch",
    "capability_required": "codewriter",
    "payload": {
      "file": "index.html",
      "insert": "<p id=\"demo\">Hello swarm</p>"
    }
  }'
```

**Response `200`:**

```json
{
  "task_id": "task_4f6534da0602",
  "task_type": "codewriter.patch",
  "capability_required": "codewriter",
  "status": "created",
  "payload": { "file": "index.html", "insert": "..." },
  "created_at": "2026-06-13T12:00:00+00:00",
  "parent_task_id": null
}
```

### `GET /tasks/poll`

Poll claimable tasks for an agent. Returns tasks in `created` status where the agent has the required capability.

**Query parameters:**

| Param | Required | Description |
|-------|----------|-------------|
| `agent_id` | yes | Registered agent ID |
| `capability` | no | Filter to one capability |

**Example:**

```bash
curl "http://127.0.0.1:8000/tasks/poll?agent_id=agent_abc&capability=codewriter"
```

**Response `200`:** array of task envelopes (may be empty).

### `GET /tasks/{task_id}`

Get a single task by ID.

### `POST /tasks/{task_id}/claim`

Claim a task. Transitions `created` → `claimed`.

**Request body:**

```json
{"agent_id": "agent_abc"}
```

**Response `200`:**

```json
{
  "claim_token": "secret-token-for-submit",
  "deadline": "2026-06-13T13:00:00+00:00"
}
```

**Errors `400`:** unknown agent, task not claimable, capability mismatch.  
**Errors `429`:** concurrent or hourly claim budget exceeded.

### `POST /tasks/checkpoint`

Optional progress checkpoint while task is claimed.

**Request body:**

```json
{
  "claim_token": "...",
  "partial_state": {"step": 2, "note": "half done"}
}
```

**Response `200`:** `{"status": "ack"}`

### `POST /tasks/submit`

Submit a signed result. Transitions `claimed` → `submitted` (or `verified`/`rejected` for reviewer tasks).

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `claim_token` | string | yes | From claim response |
| `result` | object | yes | Task-specific result |
| `signature` | string | yes | Ed25519 signature (base64) over `{"task_id","result"}` |

**Example result payloads:**

Codewriter:

```json
{"file": "index.html", "applied": true, "bytes_written": 1024}
```

Tester:

```json
{"passed": true, "returncode": 0, "stdout": "...", "stderr": ""}
```

Reviewer:

```json
{"approved": true, "notes": "auto-approved after passing tests"}
```

**Response `200`:**

```json
{"submission_id": "sub_7a8b9c0d1e2f"}
```

**Errors `400`:** invalid claim token, invalid signature, wrong state.

---

## Verifications

Phase 0 primarily uses **chained tasks** (`tester.run`, `reviewer.approve`) rather than the standalone verification table. These endpoints exist for protocol completeness and Phase 2 expansion.

### `GET /verifications/poll`

Poll pending verifications for reviewer-capable agents.

```bash
curl "http://127.0.0.1:8000/verifications/poll?agent_id=agent_reviewer"
```

### `POST /verifications/{verification_id}/claim`

Claim a verification work item.

### `POST /verifications/verify`

Submit a signed verdict on a verification claim.

**Request body:**

```json
{
  "claim_token": "...",
  "verdict": "approve",
  "notes": "LGTM",
  "signature": "..."
}
```

Signed payload: `{"verification_id"|task context, "verdict", "notes"}`.

---

## Audit

### `GET /audit`

Read the append-only audit log (most recent last in array; stored newest-first internally).

**Query:** `limit` (default 50, max 200)

**Response `200`:**

```json
[
  {
    "seq": 1,
    "timestamp": "2026-06-13T12:00:01+00:00",
    "event_type": "task.created",
    "actor_id": null,
    "details": {"task_id": "task_...", "task_type": "codewriter.patch"},
    "prev_hash": "000...000",
    "entry_hash": "a1b2c3..."
  }
]
```

---

## Signing (client-side)

Python example using the platform crypto module:

```python
from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload

pub, priv = generate_keypair()
task_id = "task_abc"
result = {"applied": True}
signature = sign_payload(priv, {"task_id": task_id, "result": result})
```

Canonical JSON rules: sorted keys, no extra whitespace, UTF-8 encoded before signing.

---

## Error responses

HTTP `400` — business rule violation (invalid signature, wrong state):

```json
{"detail": "invalid submission signature"}
```

HTTP `404` — agent or task not found.

---

## Related

- [Architecture](architecture.md) — state machine and enqueue rules
- [Reference agents](agents.md) — working client implementation
- [OpenAPI](protocol/openapi.yaml)
