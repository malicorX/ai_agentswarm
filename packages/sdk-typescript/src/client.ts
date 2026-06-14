import { ed } from "./noble.js";

import {
  canonicalJson,
  decodeB64Url,
  privateKeyB64,
  publicKeyB64,
} from "./crypto.js";

export type OwnerAuth = {
  ownerToken?: string;
  bootstrapToken?: string;
};

export type TaskEnvelope = {
  task_id: string;
  task_type: string;
  capability_required: string;
  status: string;
  payload: Record<string, unknown>;
  created_at: string;
  project_id?: string;
};

export class AgentClient {
  readonly baseUrl: string;
  readonly agentId: string;
  private readonly privateKey: Uint8Array;
  private readonly ownerAuth: OwnerAuth;

  constructor(
    baseUrl: string,
    agentId: string,
    privateKey: Uint8Array,
    ownerAuth: OwnerAuth = {},
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.agentId = agentId;
    this.privateKey = privateKey;
    this.ownerAuth = ownerAuth;
  }

  private ownerHeaders(): Record<string, string> {
    if (this.ownerAuth.ownerToken) {
      return { Authorization: `Bearer ${this.ownerAuth.ownerToken}` };
    }
    if (this.ownerAuth.bootstrapToken) {
      return { "X-Bootstrap-Token": this.ownerAuth.bootstrapToken };
    }
    return {};
  }

  static async generateKeypair(): Promise<{
    publicKey: Uint8Array;
    privateKey: Uint8Array;
  }> {
    const privateKey = ed.utils.randomPrivateKey();
    const publicKey = await ed.getPublicKey(privateKey);
    return { publicKey, privateKey };
  }

  static async register(params: {
    baseUrl: string;
    owner: string;
    capabilities: string[];
    publicKey: Uint8Array;
    privateKey: Uint8Array;
    versionSignature?: string;
    projectIds?: string[];
    ownerAuth?: OwnerAuth;
  }): Promise<AgentClient> {
    const ownerAuth = params.ownerAuth ?? {};
    const response = await fetch(`${params.baseUrl.replace(/\/$/, "")}/agents/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...ownerHeadersFromAuth(ownerAuth),
      },
      body: JSON.stringify({
        public_key: publicKeyB64(params.publicKey),
        owner: params.owner,
        capabilities: params.capabilities,
        version_signature: params.versionSignature ?? "phase1-v1",
        project_ids: params.projectIds,
      }),
    });
    if (!response.ok) {
      throw new Error(`register failed: ${response.status} ${await response.text()}`);
    }
    const body = (await response.json()) as { agent_id: string };
    return new AgentClient(params.baseUrl, body.agent_id, params.privateKey, ownerAuth);
  }

  async pollTasks(capability?: string): Promise<TaskEnvelope[]> {
    const url = new URL(`${this.baseUrl}/tasks/poll`);
    url.searchParams.set("agent_id", this.agentId);
    if (capability) {
      url.searchParams.set("capability", capability);
    }
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`poll failed: ${response.status}`);
    }
    return (await response.json()) as TaskEnvelope[];
  }

  async claim(taskId: string): Promise<string> {
    const response = await fetch(`${this.baseUrl}/tasks/${taskId}/claim`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: this.agentId }),
    });
    if (!response.ok) {
      throw new Error(`claim failed: ${response.status}`);
    }
    const body = (await response.json()) as { claim_token: string };
    return body.claim_token;
  }

  async signResult(taskId: string, result: Record<string, unknown>): Promise<string> {
    const message = new TextEncoder().encode(
      canonicalJson({ task_id: taskId, result }),
    );
    const signature = await ed.sign(message, this.privateKey);
    return Buffer.from(signature).toString("base64url");
  }

  async submit(
    claimToken: string,
    taskId: string,
    result: Record<string, unknown>,
  ): Promise<string> {
    const signature = await this.signResult(taskId, result);
    const response = await fetch(`${this.baseUrl}/tasks/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        claim_token: claimToken,
        result,
        signature,
      }),
    });
    if (!response.ok) {
      throw new Error(`submit failed: ${response.status}`);
    }
    const body = (await response.json()) as { submission_id: string };
    return body.submission_id;
  }

  async createTask(params: {
    taskType: string;
    capabilityRequired: string;
    payload?: Record<string, unknown>;
    projectId?: string;
  }): Promise<TaskEnvelope> {
    const response = await fetch(`${this.baseUrl}/tasks`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...this.ownerHeaders(),
      },
      body: JSON.stringify({
        task_type: params.taskType,
        capability_required: params.capabilityRequired,
        payload: params.payload ?? {},
        project_id: params.projectId,
      }),
    });
    if (!response.ok) {
      throw new Error(`create task failed: ${response.status}`);
    }
    return (await response.json()) as TaskEnvelope;
  }

  static importPrivateKey(b64: string): Uint8Array {
    return decodeB64Url(b64);
  }

  static exportPrivateKey(privateKey: Uint8Array): string {
    return privateKeyB64(privateKey);
  }
}

function ownerHeadersFromAuth(ownerAuth: OwnerAuth): Record<string, string> {
  if (ownerAuth.ownerToken) {
    return { Authorization: `Bearer ${ownerAuth.ownerToken}` };
  }
  if (ownerAuth.bootstrapToken) {
    return { "X-Bootstrap-Token": ownerAuth.bootstrapToken };
  }
  return {};
}
