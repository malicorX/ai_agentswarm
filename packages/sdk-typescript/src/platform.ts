import type { OwnerAuth } from "./client.js";

export type ProjectEnvelope = {
  project_id: string;
  name: string;
  description?: string | null;
  created_at: string;
  governance_template_id?: string | null;
  governance_config?: Record<string, unknown>;
};

export type GovernanceTemplateSummary = {
  template_id: string;
  name: string;
  description?: string | null;
};

export class PlatformClient {
  readonly baseUrl: string;
  private readonly ownerAuth: OwnerAuth;

  constructor(baseUrl: string, ownerAuth: OwnerAuth = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
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

  async listProjects(): Promise<ProjectEnvelope[]> {
    const response = await fetch(`${this.baseUrl}/projects`);
    if (!response.ok) {
      throw new Error(`list projects failed: ${response.status}`);
    }
    return (await response.json()) as ProjectEnvelope[];
  }

  async createProject(params: {
    name: string;
    projectId?: string;
    description?: string;
    governanceTemplateId?: string;
  }): Promise<ProjectEnvelope> {
    const response = await fetch(`${this.baseUrl}/projects`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...this.ownerHeaders(),
      },
      body: JSON.stringify({
        name: params.name,
        project_id: params.projectId,
        description: params.description,
        governance_template_id: params.governanceTemplateId,
      }),
    });
    if (!response.ok) {
      throw new Error(`create project failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as ProjectEnvelope;
  }

  async getProjectGovernance(projectId: string): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}/projects/${projectId}/governance`);
    if (!response.ok) {
      throw new Error(`get governance failed: ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async listGovernanceTemplates(): Promise<GovernanceTemplateSummary[]> {
    const response = await fetch(`${this.baseUrl}/governance/templates`);
    if (!response.ok) {
      throw new Error(`list templates failed: ${response.status}`);
    }
    return (await response.json()) as GovernanceTemplateSummary[];
  }

  async getGovernanceTemplate(templateId: string): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}/governance/templates/${templateId}`);
    if (!response.ok) {
      throw new Error(`get template failed: ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async getCredibility(
    agentId: string,
    projectId = "default",
  ): Promise<Record<string, unknown>> {
    const url = new URL(`${this.baseUrl}/agents/${agentId}/credibility`);
    url.searchParams.set("project_id", projectId);
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`get credibility failed: ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async importCredibility(
    agentId: string,
    params: {
      sourceProjectId: string;
      targetProjectId: string;
      capabilities?: string[];
    },
  ): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}/agents/${agentId}/credibility/import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...this.ownerHeaders(),
      },
      body: JSON.stringify({
        source_project_id: params.sourceProjectId,
        target_project_id: params.targetProjectId,
        capabilities: params.capabilities,
      }),
    });
    if (!response.ok) {
      throw new Error(`import credibility failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async credibilityLeaderboard(params: {
    capability?: string;
    projectId?: string;
    limit?: number;
  } = {}): Promise<Record<string, unknown>> {
    const url = new URL(`${this.baseUrl}/credibility/leaderboard`);
    if (params.capability) {
      url.searchParams.set("capability", params.capability);
    }
    url.searchParams.set("project_id", params.projectId ?? "default");
    url.searchParams.set("limit", String(params.limit ?? 20));
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`leaderboard failed: ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async getOwnerAnchoring(ownerId: string): Promise<{
    owner_id: string;
    github_login: string;
    penalty_score: number;
    anchored_initial_score: number;
  }> {
    const response = await fetch(`${this.baseUrl}/owners/${ownerId}/anchoring`);
    if (!response.ok) {
      throw new Error(`get owner anchoring failed: ${response.status}`);
    }
    return (await response.json()) as {
      owner_id: string;
      github_login: string;
      penalty_score: number;
      anchored_initial_score: number;
    };
  }

  async createDeployRequest(params: {
    environment: string;
    artifactRef: string;
    projectId?: string;
    description?: string;
    requiredSignoffs?: number;
    minCredibility?: number;
  }): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}/deploy/requests`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...this.ownerHeaders(),
      },
      body: JSON.stringify({
        project_id: params.projectId ?? "default",
        environment: params.environment,
        artifact_ref: params.artifactRef,
        description: params.description,
        required_signoffs: params.requiredSignoffs,
        min_credibility: params.minCredibility,
      }),
    });
    if (!response.ok) {
      throw new Error(`create deploy request failed: ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async getDeployRequest(requestId: string): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}/deploy/requests/${requestId}`);
    if (!response.ok) {
      throw new Error(`get deploy request failed: ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async listDeployRequests(params: {
    status?: string;
    projectId?: string;
    limit?: number;
  } = {}): Promise<Record<string, unknown>[]> {
    const url = new URL(`${this.baseUrl}/deploy/requests`);
    if (params.status) {
      url.searchParams.set("status", params.status);
    }
    if (params.projectId) {
      url.searchParams.set("project_id", params.projectId);
    }
    url.searchParams.set("limit", String(params.limit ?? 50));
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`list deploy requests failed: ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>[];
  }
}
