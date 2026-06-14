from agentswarm_agents.memory_keys import memory_key_for_project


def test_default_project_uses_legacy_backlog_key() -> None:
    assert memory_key_for_project("default") == "news-backlog"
    assert memory_key_for_project(None) == "news-backlog"


def test_scoped_project_prefixes_key() -> None:
    assert memory_key_for_project("news-hub") == "news-hub.news-backlog"


def test_explicit_key_overrides_project() -> None:
    assert memory_key_for_project("news-hub", explicit_key="custom") == "custom"
