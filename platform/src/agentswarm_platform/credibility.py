from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass
from typing import Any

INITIAL_SCORE = float(os.environ.get("AGENTSWARM_CRED_INITIAL", "10"))
BASE_MINT = float(os.environ.get("AGENTSWARM_CRED_BASE_MINT", "5"))
BASE_BURN = float(os.environ.get("AGENTSWARM_CRED_BASE_BURN", "3"))
REVIEWER_MINT = float(os.environ.get("AGENTSWARM_CRED_REVIEWER_MINT", "2"))
STAKE_RATE = float(os.environ.get("AGENTSWARM_CRED_STAKE_RATE", "0.05"))
STAKE_MIN = 0.5
STAKE_MAX = 10.0
VERIFIER_WEIGHT_CAP = 3.0
DECAY_HALF_LIFE_DAYS = 180.0


def credibility_enabled() -> bool:
    return os.environ.get("AGENTSWARM_CREDIBILITY_ENABLED", "").lower() in (
        "1",
        "true",
        "yes",
    )


def task_stake_tier(payload: dict[str, Any]) -> int:
    tier = str(payload.get("stake_tier", "low")).lower()
    return {"low": 1, "medium": 2, "high": 3}.get(tier, 1)


def verifier_weight(verifier_score: float) -> float:
    return min(
        VERIFIER_WEIGHT_CAP,
        1.0 + math.log1p(max(0.0, verifier_score) / 50.0),
    )


def stake_amount(score: float) -> float:
    if score <= 0:
        return STAKE_MIN
    return max(STAKE_MIN, min(STAKE_MAX, score * STAKE_RATE))


def mint_for_acceptance(task_tier: int, verifier_score: float) -> float:
    return BASE_MINT * task_tier * verifier_weight(verifier_score)


def burn_for_rejection(task_tier: int) -> float:
    return BASE_BURN * task_tier


def decay_score(score: float, days_inactive: float) -> float:
    if days_inactive <= 0:
        return score
    return score * math.pow(0.5, days_inactive / DECAY_HALF_LIFE_DAYS)


@dataclass(frozen=True)
class OutcomeDeltas:
    submitter_capability: str
    submitter_delta: float
    reviewer_delta: float
    stake: float
    mint: float
    burn: float


def compute_outcome_deltas(
    *,
    accepted: bool,
    submitter_capability: str,
    task_tier: int,
    stake: float,
    verifier_score: float,
) -> OutcomeDeltas:
    if accepted:
        mint = mint_for_acceptance(task_tier, verifier_score)
        submitter_delta = stake + mint
        reviewer_delta = REVIEWER_MINT
        burn = 0.0
    else:
        mint = 0.0
        burn = burn_for_rejection(task_tier)
        submitter_delta = -burn
        reviewer_delta = REVIEWER_MINT
    return OutcomeDeltas(
        submitter_capability=submitter_capability,
        submitter_delta=submitter_delta,
        reviewer_delta=reviewer_delta,
        stake=stake,
        mint=mint,
        burn=burn,
    )


def new_ledger_entry_id() -> str:
    return f"cred_{uuid.uuid4().hex[:12]}"
