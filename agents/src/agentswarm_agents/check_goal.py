"""CLI: collect and print per-goal run diagnostics."""

from __future__ import annotations

import argparse
import sys

from agentswarm_agents.client import platform_url
from agentswarm_agents.goal_run_log import format_goal_run_report, write_goal_run_log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentswarm-check-goal",
        description="Inspect a goal run for errors and write logs/run-logs/goal-<id>.json",
    )
    parser.add_argument("goal_id", help="Goal id, e.g. goal-0a81ebf6276c")
    parser.add_argument(
        "--base-url",
        default=platform_url(),
        help="Platform API base URL",
    )
    parser.add_argument(
        "--no-workspace-probe",
        action="store_true",
        help="Skip workspace tree checkout (faster; omits workspace_tree_failed checks)",
    )
    args = parser.parse_args(argv)

    try:
        report, paths = write_goal_run_log(
            args.base_url.rstrip("/"),
            args.goal_id,
            include_workspace_probe=not args.no_workspace_probe,
        )
    except Exception as exc:
        print(f"check-goal failed: {exc}", file=sys.stderr)
        return 1

    print(format_goal_run_report(report))
    if paths:
        print(f"\nWrote {len(paths)} log file(s).")
    return 1 if report.get("has_errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
