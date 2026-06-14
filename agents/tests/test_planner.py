from unittest.mock import MagicMock

from agentswarm_agents.workers.planner import should_clear_backlog_after_plan


def test_should_clear_backlog_after_drain_plan() -> None:
    assert should_clear_backlog_after_plan("drain-news-backlog", 2) is True
    assert should_clear_backlog_after_plan("drain", 1) is True
    assert should_clear_backlog_after_plan("drain-news-backlog", 0) is False
    assert should_clear_backlog_after_plan("explore", 3) is False


def test_execute_task_clears_backlog_on_drain() -> None:
    from agentswarm_agents.workers.planner import execute_task

    client = MagicMock()
    task = {
        "project_id": "default",
        "payload": {"goal": "drain-news-backlog", "memory_key": "news-backlog"},
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
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

    import agentswarm_agents.workers.planner as planner_module

    original_get = planner_module.httpx.get
    planner_module.httpx.get = lambda *args, **kwargs: FakeResponse()
    try:
        result = execute_task(task, "http://127.0.0.1:8000", client=client)
    finally:
        planner_module.httpx.get = original_get

    assert result["planned_count"] == 1
    assert result["backlog_cleared"] is True
    client.upsert_memory.assert_called_once_with(
        "news-backlog",
        {"articles": []},
        tags=["planner", "backlog-drained"],
    )
