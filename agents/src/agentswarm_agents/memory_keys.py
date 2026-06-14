from __future__ import annotations

DEFAULT_BACKLOG_SUFFIX = "news-backlog"


def memory_key_for_project(
    project_id: str | None,
    *,
    suffix: str = DEFAULT_BACKLOG_SUFFIX,
    explicit_key: str | None = None,
) -> str:
    if explicit_key:
        return explicit_key
    resolved = project_id or "default"
    if resolved == "default":
        return suffix
    return f"{resolved}.{suffix}"
