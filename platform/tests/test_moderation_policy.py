from agentswarm_platform.moderation_policy import (
    ModerationPolicy,
    build_moderation_actions,
    resolve_moderation_policy,
)


def test_resolve_moderation_policy_from_governance() -> None:
    policy = resolve_moderation_policy(
        {"moderation": {"canary_failure_rate_threshold": 0.8, "min_canary_attempts": 3}}
    )
    assert policy.canary_failure_rate_threshold == 0.8
    assert policy.min_canary_attempts == 3


def test_stricter_policy_skips_quarantine() -> None:
    summary = {
        "canary_failures_top": [
            {"agent_id": "agent_a", "failures": 3, "attempts": 4},
        ],
        "replication_groups": {},
    }
    _, default_actions = build_moderation_actions(summary)
    assert default_actions[0]["type"] == "quarantine"

    strict = ModerationPolicy(canary_failure_rate_threshold=0.8, min_canary_attempts=2)
    _, strict_actions = build_moderation_actions(summary, strict)
    assert strict_actions[0]["type"] == "flag"


def test_min_attempts_blocks_action() -> None:
    summary = {
        "canary_failures_top": [
            {"agent_id": "agent_a", "failures": 1, "attempts": 1},
        ],
        "replication_groups": {},
    }
    findings, actions = build_moderation_actions(summary)
    assert findings == []
    assert actions == []
