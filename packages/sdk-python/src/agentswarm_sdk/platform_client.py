from __future__ import annotations

import os
from typing import Any

import httpx


class PlatformClient:
    """Owner-authenticated platform operations (projects, governance, credibility)."""

    def __init__(
        self,
        base_url: str,
        *,
        owner_token: str | None = None,
        bootstrap_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owner_token = owner_token or os.environ.get("AGENTSWARM_OWNER_TOKEN")
        self._bootstrap_token = bootstrap_token or os.environ.get(
            "AGENTSWARM_BOOTSTRAP_TOKEN"
        )
        self._http = httpx.Client(base_url=self.base_url, timeout=30.0)

    def _owner_headers(self) -> dict[str, str]:
        if self._owner_token:
            return {"Authorization": f"Bearer {self._owner_token}"}
        if self._bootstrap_token:
            return {"X-Bootstrap-Token": self._bootstrap_token}
        return {}

    def list_projects(self) -> list[dict[str, Any]]:
        response = self._http.get("/projects")
        response.raise_for_status()
        return response.json()

    def create_project(
        self,
        name: str,
        *,
        project_id: str | None = None,
        description: str | None = None,
        governance_template_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if project_id is not None:
            body["project_id"] = project_id
        if description is not None:
            body["description"] = description
        if governance_template_id is not None:
            body["governance_template_id"] = governance_template_id
        response = self._http.post("/projects", json=body, headers=self._owner_headers())
        response.raise_for_status()
        return response.json()

    def get_project_governance(self, project_id: str) -> dict[str, Any]:
        response = self._http.get(f"/projects/{project_id}/governance")
        response.raise_for_status()
        return response.json()

    def list_governance_templates(self) -> list[dict[str, Any]]:
        response = self._http.get("/governance/templates")
        response.raise_for_status()
        return response.json()

    def get_governance_template(self, template_id: str) -> dict[str, Any]:
        response = self._http.get(f"/governance/templates/{template_id}")
        response.raise_for_status()
        return response.json()

    def get_credibility(
        self, agent_id: str, *, project_id: str = "default"
    ) -> dict[str, Any]:
        response = self._http.get(
            f"/agents/{agent_id}/credibility",
            params={"project_id": project_id},
        )
        response.raise_for_status()
        return response.json()

    def import_credibility(
        self,
        agent_id: str,
        *,
        source_project_id: str,
        target_project_id: str,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "source_project_id": source_project_id,
            "target_project_id": target_project_id,
        }
        if capabilities is not None:
            body["capabilities"] = capabilities
        response = self._http.post(
            f"/agents/{agent_id}/credibility/import",
            json=body,
            headers=self._owner_headers(),
        )
        response.raise_for_status()
        return response.json()

    def credibility_leaderboard(
        self,
        *,
        capability: str | None = None,
        project_id: str = "default",
        limit: int = 20,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"project_id": project_id, "limit": limit}
        if capability:
            params["capability"] = capability
        response = self._http.get("/credibility/leaderboard", params=params)
        response.raise_for_status()
        return response.json()

    def get_agent_profile(
        self, agent_id: str, *, project_id: str = "default"
    ) -> dict[str, Any]:
        response = self._http.get(
            f"/agents/{agent_id}/profile",
            params={"project_id": project_id},
        )
        response.raise_for_status()
        return response.json()

    def get_owner_anchoring(self, owner_id: str) -> dict[str, Any]:
        response = self._http.get(f"/owners/{owner_id}/anchoring")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PlatformClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
