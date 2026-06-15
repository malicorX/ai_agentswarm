from agentswarm_platform.moderation_policy import ModerationPolicy, build_moderation_actions


def test_owner_cluster_flags_when_threshold_met() -> None:
    summary = {
        "canary_failures_top": [],
        "replication_groups": {},
        "owner_clusters": [{"owner": "sybil-ring", "agent_count": 6}],
    }
    policy = ModerationPolicy(max_agents_per_owner=5)
    findings, actions = build_moderation_actions(summary, policy)
    assert findings[0]["type"] == "owner_agent_cluster"
    assert actions[0]["subject_type"] == "owner"
    assert actions[0]["subject_id"] == "sybil-ring"


def test_owner_cluster_below_threshold_skipped() -> None:
    summary = {
        "canary_failures_top": [],
        "replication_groups": {},
        "owner_clusters": [{"owner": "solo", "agent_count": 3}],
    }
    policy = ModerationPolicy(max_agents_per_owner=5)
    findings, actions = build_moderation_actions(summary, policy)
    assert findings == []
    assert actions == []


def test_owner_cluster_disabled_when_threshold_zero() -> None:
    summary = {
        "canary_failures_top": [],
        "replication_groups": {},
        "owner_clusters": [{"owner": "many", "agent_count": 20}],
    }
    findings, actions = build_moderation_actions(summary, ModerationPolicy())
    assert findings == []
    assert actions == []


def test_platform_summary_lists_owner_clusters(cred_client) -> None:
    from agentswarm_platform.crypto import generate_keypair, public_key_b64

    # With AGENTSWARM_AUTH_DISABLED, registered agents are owned by mock login "dev".
    for _ in range(4):
        pub, _ = generate_keypair()
        response = cred_client.post(
            "/agents/register",
            json={
                "public_key": public_key_b64(pub),
                "owner": "dev",
                "capabilities": ["codewriter"],
            },
        )
        assert response.status_code == 200

    summary = cred_client.get("/platform/summary").json()
    clusters = summary["owner_clusters"]
    match = next((c for c in clusters if c["owner"] == "dev"), None)
    assert match is not None
    assert match["agent_count"] >= 4
