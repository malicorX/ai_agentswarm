from agentswarm_agents.workers.orchestrator import detect_gaps


def test_detect_gaps_passes_scoped_memory_key_to_planner() -> None:
    summary = {"tasks": {"created": 0}}
    backlog = {"content": {"articles": [{"id": "a1"}]}}
    gaps, enqueue = detect_gaps(summary, backlog, memory_key="hub.news-backlog")
    assert gaps[0]["type"] == "idle_pool_with_backlog"
    assert enqueue[0]["payload"]["memory_key"] == "hub.news-backlog"


def test_record_scan_state_writes_project_scoped_memory() -> None:
    from unittest.mock import MagicMock

    from agentswarm_agents.memory_keys import memory_key_for_project
    from agentswarm_agents.workers.orchestrator import record_scan_state

    client = MagicMock()
    result = {
        "gaps": [{"type": "idle_pool_with_backlog"}],
        "enqueue": [{"task_type": "planner.plan"}],
    }
    record_scan_state(client, "hub", result)
    client.upsert_memory.assert_called_once()
    args, kwargs = client.upsert_memory.call_args
    assert args[0] == memory_key_for_project("hub", suffix="orchestrator-state")
    assert kwargs["tags"] == ["orchestrator"]
    assert args[1]["enqueue_count"] == 1
