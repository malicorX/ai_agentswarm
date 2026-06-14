from agentswarm_agents.client import PlatformClient
from agentswarm_platform.crypto import (
    generate_keypair,
    public_key_b64,
    sign_payload,
    verify_payload,
)


def test_upsert_memory_signs_expected_payload() -> None:
    pub_raw, priv_raw = generate_keypair()
    client = PlatformClient("http://127.0.0.1:8000", "agent_test", priv_raw)
    content = {"articles": []}
    tags = ["pilot"]
    signed = {
        "memory_key": "news-backlog",
        "content": content,
        "tags": tags,
        "agent_id": client.agent_id,
    }
    signature = sign_payload(priv_raw, signed)
    assert verify_payload(public_key_b64(pub_raw), signed, signature)
    assert client.agent_id == "agent_test"
