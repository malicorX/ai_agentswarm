from fastapi.testclient import TestClient

from agentswarm_agents.federation_demo import run_federation_demo


def test_federation_demo_invariants(client: TestClient) -> None:
    run_federation_demo(client)
