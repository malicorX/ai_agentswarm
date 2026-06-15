import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import test from "node:test";

import {
  platformAssignmentMode,
  verifyAssignmentSignature,
  type AssignmentEnvelope,
} from "./dispatch.js";

test("platformAssignmentMode prefers assignment block", () => {
  const mode = platformAssignmentMode({
    assignment_mode: "pull",
    assignment: { mode: "dispatch" },
  });
  assert.equal(mode, "dispatch");
});

test("verifyAssignmentSignature accepts reconstructed payload", () => {
  const payload = {
    lease_id: "lease-1",
    agent_id: "agent-1",
    task_id: "task-1",
    expires_at: "2030-01-01T00:00:00+00:00",
  };
  const canonical = JSON.stringify(
    Object.fromEntries(
      Object.entries(payload).sort(([a], [b]) => a.localeCompare(b)),
    ),
  );
  const signature = createHmac("sha256", "test-secret")
    .update(canonical)
    .digest("hex");
  const assignment: AssignmentEnvelope = {
    lease_id: "lease-1",
    task_id: "task-1",
    task_type: "reviewer.subjective",
    capability_required: "reviewer",
    claim_token: "claim",
    expires_at: "2030-01-01T00:00:00+00:00",
    assignment_signature: signature,
    capsule: {},
  };
  verifyAssignmentSignature(assignment, "agent-1", "test-secret");
});

test("verifyAssignmentSignature rejects invalid signature", () => {
  const assignment: AssignmentEnvelope = {
    lease_id: "lease-1",
    task_id: "task-1",
    task_type: "reviewer.subjective",
    capability_required: "reviewer",
    claim_token: "claim",
    expires_at: "2030-01-01T00:00:00+00:00",
    assignment_signature: "deadbeef",
    capsule: {},
    signature_payload: {
      lease_id: "lease-1",
      agent_id: "agent-1",
      task_id: "task-1",
      expires_at: "2030-01-01T00:00:00+00:00",
    },
  };
  assert.throws(
    () => verifyAssignmentSignature(assignment, "agent-1", "test-secret"),
    /invalid assignment signature/,
  );
});

test("submitAssignment surfaces platform detail", async () => {
  const { AgentClient } = await import("./client.js");
  const { DispatchClient } = await import("./dispatch.js");
  const { privateKey } = await AgentClient.generateKeypair();
  const client = new DispatchClient(
    "https://example.test/api",
    "agent-1",
    privateKey,
  );
  const assignment: AssignmentEnvelope = {
    lease_id: "lease-1",
    task_id: "task-1",
    task_type: "reviewer.subjective",
    capability_required: "reviewer",
    claim_token: "bad-token",
    expires_at: "2030-01-01T00:00:00+00:00",
    assignment_signature: "sig",
    capsule: {},
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ detail: "invalid claim token" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;
  try {
    await assert.rejects(
      () =>
        client.submitAssignment(assignment, {
          scores: { quality: 8 },
          rationale: "ok",
        }),
      /invalid claim token/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
