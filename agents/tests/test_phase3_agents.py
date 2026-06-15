from agentswarm_agents.workers.orchestrator import detect_gaps
from agentswarm_agents.workers.planner import build_enqueue_from_backlog


def test_build_enqueue_from_backlog() -> None:
    entry = {
        "content": {
            "articles": [
                {
                    "id": "a1",
                    "title": "T",
                    "summary": "S",
                    "url": "https://example.com",
                    "source": "ex",
                    "published_at": "2026-06-13T00:00:00+00:00",
                }
            ]
        }
    }
    result = build_enqueue_from_backlog(entry, "drain")
    assert result["planned_count"] == 1
    assert result["enqueue"][0]["task_type"] == "codewriter.add-article"


def test_detect_idle_pool_gap() -> None:
    summary = {"tasks": {"created": 0}, "canary_failures_top": [], "memory_keys": ["news-backlog"]}
    backlog = {"content": {"articles": [{"id": "1"}]}}
    gaps, enqueue = detect_gaps(summary, backlog, memory_key="news-backlog")
    assert gaps[0]["type"] == "idle_pool_with_backlog"
    assert enqueue[0]["task_type"] == "planner.plan"


def test_detect_pending_deploy_gaps() -> None:
    summary = {
        "tasks": {"created": 0},
        "canary_failures_top": [],
        "memory_keys": [],
        "deploy_requests": {
            "by_status": {"pending": 1, "approved": 1},
            "pending_signoff_tasks": 2,
            "pending_execute_tasks": 1,
        },
    }
    gaps, enqueue = detect_gaps(summary, None, memory_key="news-backlog")
    types = {gap["type"] for gap in gaps}
    assert "pending_deploy_signoffs" in types
    assert "pending_deploy_execute" in types
    assert enqueue == []


def test_detect_owner_cluster_gaps() -> None:
    summary = {
        "tasks": {"created": 0},
        "canary_failures_top": [],
        "memory_keys": [],
        "owner_clusters": [{"owner": "dev", "agent_count": 5}],
    }
    gaps, enqueue = detect_gaps(summary, None, memory_key="news-backlog")
    assert gaps[0]["type"] == "owner_agent_clusters"
    assert gaps[0]["clusters"][0]["agent_count"] == 5
    assert enqueue[0]["task_type"] == "moderator.scan"
