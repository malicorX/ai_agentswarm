import { createHmac } from "node:crypto";

import { AgentClient } from "./client.js";
import { canonicalJson } from "./crypto.js";

export type AssignmentEnvelope = {
  lease_id: string;
  task_id: string;
  task_type: string;
  capability_required: string;
  project_id?: string;
  claim_token: string;
  expires_at: string;
  assignment_signature: string;
  capsule: Record<string, unknown>;
  signature_payload?: Record<string, unknown>;
};

export function platformAssignmentMode(config: Record<string, unknown>): string {
  const assignment = config.assignment;
  if (assignment && typeof assignment === "object" && "mode" in assignment) {
    return String((assignment as { mode: string }).mode);
  }
  return String(config.assignment_mode ?? "pull");
}

export async function fetchPlatformConfig(baseUrl: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/platform/config`);
  if (!response.ok) {
    throw new Error(`platform config failed: ${response.status}`);
  }
  return (await response.json()) as Record<string, unknown>;
}

export async function assertDispatchMode(baseUrl: string): Promise<void> {
  const config = await fetchPlatformConfig(baseUrl);
  const mode = platformAssignmentMode(config);
  if (mode !== "dispatch") {
    throw new Error(
      `platform assignment mode is ${mode}; DispatchClient requires dispatch`,
    );
  }
}

function canonicalAssignmentPayload(payload: Record<string, unknown>): string {
  const sorted = Object.keys(payload)
    .sort()
    .reduce<Record<string, unknown>>((acc, key) => {
      acc[key] = payload[key];
      return acc;
    }, {});
  return JSON.stringify(sorted);
}

export function verifyAssignmentSignature(
  assignment: AssignmentEnvelope,
  agentId: string,
  secret: string,
): void {
  const payload =
    assignment.signature_payload && typeof assignment.signature_payload === "object"
      ? assignment.signature_payload
      : {
          lease_id: assignment.lease_id,
          agent_id: agentId,
          task_id: assignment.task_id,
          expires_at: assignment.expires_at,
        };
  if (payload.agent_id !== agentId) {
    throw new Error("assignment agent_id mismatch");
  }
  if (!assignment.assignment_signature) {
    throw new Error("assignment missing assignment_signature");
  }
  const expected = createHmac("sha256", secret)
    .update(canonicalAssignmentPayload(payload as Record<string, unknown>))
    .digest("hex");
  if (expected !== assignment.assignment_signature) {
    throw new Error("invalid assignment signature");
  }
}

export class DispatchClient extends AgentClient {
  async heartbeat(params: {
    capabilities: string[];
    status?: string;
    modelId?: string;
    load?: number;
    clientVersion?: string;
    ttlSec?: number;
    vramGb?: number;
  }): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = {
      status: params.status ?? "idle",
      capabilities: params.capabilities,
      model_id: params.modelId,
      load: params.load ?? 0,
      client_version: params.clientVersion,
      ttl_sec: params.ttlSec ?? 120,
    };
    if (params.vramGb !== undefined) {
      body.vram_gb = params.vramGb;
    }
    const response = await fetch(`${this.baseUrl}/agents/${this.agentId}/presence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(`heartbeat failed: ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async getPendingAssignment(params?: {
    waitSec?: number;
  }): Promise<AssignmentEnvelope | null> {
    const url = new URL(`${this.baseUrl}/agents/${this.agentId}/assignments/pending`);
    if (params?.waitSec && params.waitSec > 0) {
      url.searchParams.set("wait_sec", String(params.waitSec));
    }
    const timeoutMs = params?.waitSec
      ? Math.max(30_000, params.waitSec * 1000 + 10_000)
      : 30_000;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`pending assignment failed: ${response.status}`);
      }
      return (await response.json()) as AssignmentEnvelope | null;
    } finally {
      clearTimeout(timer);
    }
  }

  async waitForAssignment(params?: {
    pollSec?: number;
    timeoutSec?: number;
    serverLongPoll?: boolean;
  }): Promise<AssignmentEnvelope | null> {
    const timeoutSec = params?.timeoutSec ?? 30;
    if (params?.serverLongPoll !== false) {
      return this.getPendingAssignment({ waitSec: timeoutSec });
    }
    const pollSec = params?.pollSec ?? 1;
    const deadline = Date.now() + timeoutSec * 1000;
    while (Date.now() < deadline) {
      const assignment = await this.getPendingAssignment();
      if (assignment) {
        return assignment;
      }
      await new Promise((resolve) => setTimeout(resolve, pollSec * 1000));
    }
    return null;
  }

  async submitAssignment(
    assignment: AssignmentEnvelope,
    result: Record<string, unknown>,
  ): Promise<string> {
    const signature = await this.signResult(assignment.task_id, result);
    const response = await fetch(`${this.baseUrl}/tasks/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        claim_token: assignment.claim_token,
        result,
        signature,
      }),
    });
    if (!response.ok) {
      let detail = await response.text();
      try {
        const body = (await JSON.parse(detail)) as { detail?: string };
        if (body.detail) {
          detail = body.detail;
        }
      } catch {
        // keep raw text
      }
      throw new Error(`task submit failed (${response.status}): ${detail}`);
    }
    const body = (await response.json()) as { submission_id: string };
    return body.submission_id;
  }
}
