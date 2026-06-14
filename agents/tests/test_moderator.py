from agentswarm_platform.moderation_policy import build_moderation_actions


def test_quarantine_on_high_canary_failure_rate() -> None:
    summary = {
        "canary_failures_top": [
            {"agent_id": "agent_a", "failures": 3, "attempts": 4},
        ],
        "replication_groups": {},
    }
    findings, actions = build_moderation_actions(summary)
    assert findings[0]["type"] == "canary_failure_rate"
    assert actions[0]["type"] == "quarantine"


def test_flag_disputed_replications() -> None:
    summary = {
        "canary_failures_top": [],
        "replication_groups": {"disputed": 2},
    }
    findings, actions = build_moderation_actions(summary)
    assert findings[0]["type"] == "disputed_replications"
    assert actions[0]["type"] == "flag"
