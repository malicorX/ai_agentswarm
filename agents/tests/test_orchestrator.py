from agentswarm_agents.workers.orchestrator import detect_gaps


def test_detect_gaps_passes_scoped_memory_key_to_planner() -> None:
    summary = {"tasks": {"created": 0}}
    backlog = {"content": {"articles": [{"id": "a1"}]}}
    gaps, enqueue = detect_gaps(summary, backlog, memory_key="hub.news-backlog")
    assert gaps[0]["type"] == "idle_pool_with_backlog"
    assert enqueue[0]["payload"]["memory_key"] == "hub.news-backlog"
