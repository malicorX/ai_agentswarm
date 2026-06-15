from __future__ import annotations

import sqlite3
from typing import Any

from agentswarm_platform.credibility import TIER_HIGH_MIN, TIER_MEDIUM_MIN

LEVEL_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.0, "novice"),
    (15.0, "apprentice"),
    (25.0, "journeyman"),
    (50.0, "expert"),
    (100.0, "master"),
)

BADGE_DEFINITIONS: dict[str, str] = {
    "first_accept": "First verified task accepted",
    "stake_player": "Staked credibility on a claim",
    "reviewer_mint": "Completed a review",
    "cross_project": "Imported reputation from another project",
    "medium_tier": "Eligible for medium-stake tasks",
    "high_tier": "Eligible for high-stake tasks",
    "deploy_signoff": "Signed off on a deploy request",
    "deploy_executor": "Executed an approved deploy",
}


def capability_level(score: float) -> dict[str, Any]:
    rank = 1
    label = LEVEL_THRESHOLDS[0][1]
    min_score = 0.0
    for index, (threshold, name) in enumerate(LEVEL_THRESHOLDS, start=1):
        if score >= threshold:
            rank = index
            label = name
            min_score = threshold
        else:
            break
    next_at: float | None = None
    next_label: str | None = None
    if rank < len(LEVEL_THRESHOLDS):
        next_at, next_label = LEVEL_THRESHOLDS[rank]
    return {
        "rank": rank,
        "label": label,
        "min_score": min_score,
        "next_at": next_at,
        "next_label": next_label,
    }


def _ledger_reasons(
    conn: sqlite3.Connection,
    agent_id: str,
    project_id: str,
) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT reason FROM credibility_ledger
        WHERE agent_id = ? AND project_id = ?
        """,
        (agent_id, project_id),
    ).fetchall()
    return {str(row["reason"]) for row in rows}


def badges_for_agent(
    conn: sqlite3.Connection,
    agent_id: str,
    capability: str,
    score: float,
    project_id: str,
) -> list[dict[str, str]]:
    reasons = _ledger_reasons(conn, agent_id, project_id)
    earned: list[str] = []
    if "mint.accept" in reasons:
        earned.append("first_accept")
    if "stake.lock" in reasons:
        earned.append("stake_player")
    if capability == "reviewer" and "mint.verify" in reasons:
        earned.append("reviewer_mint")
    if "import.cross_project" in reasons:
        earned.append("cross_project")
    if score >= TIER_MEDIUM_MIN:
        earned.append("medium_tier")
    if score >= TIER_HIGH_MIN:
        earned.append("high_tier")
    if conn.execute(
        "SELECT 1 FROM deploy_signoffs WHERE agent_id = ? LIMIT 1",
        (agent_id,),
    ).fetchone():
        earned.append("deploy_signoff")
    if conn.execute(
        "SELECT 1 FROM deploy_requests WHERE executed_by_agent_id = ? LIMIT 1",
        (agent_id,),
    ).fetchone():
        earned.append("deploy_executor")
    return [
        {"id": badge_id, "label": BADGE_DEFINITIONS[badge_id]}
        for badge_id in earned
    ]


def enrich_leaderboard_entry(
    conn: sqlite3.Connection,
    entry: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    score = float(entry["score"])
    return {
        **entry,
        "level": capability_level(score),
        "badges": badges_for_agent(
            conn,
            str(entry["agent_id"]),
            str(entry["capability"]),
            score,
            project_id,
        ),
    }


def build_agent_profile(
    conn: sqlite3.Connection,
    agent: dict[str, Any],
    *,
    project_id: str,
    credibility_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    agent_id = str(agent["agent_id"])
    credibility: list[dict[str, Any]] = []
    badge_map: dict[str, set[str]] = {}
    max_score = 0.0

    for row in credibility_rows:
        capability = str(row["capability"])
        score = float(row["score"])
        max_score = max(max_score, score)
        badges = badges_for_agent(conn, agent_id, capability, score, project_id)
        for badge in badges:
            badge_map.setdefault(badge["id"], set()).add(capability)
        credibility.append(
            {
                "capability": capability,
                "score": score,
                "updated_at": row["updated_at"],
                "level": capability_level(score),
                "badges": badges,
            }
        )

    return {
        "agent_id": agent_id,
        "owner": agent["owner"],
        "project_id": project_id,
        "declared_capabilities": list(agent["capabilities"]),
        "quarantined": bool(agent.get("quarantined")),
        "credibility": credibility,
        "aggregate_level": capability_level(max_score),
        "badges": [
            {
                "id": badge_id,
                "label": BADGE_DEFINITIONS[badge_id],
                "capabilities": sorted(capabilities),
            }
            for badge_id, capabilities in sorted(badge_map.items())
        ],
    }
