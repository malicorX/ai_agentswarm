import math

import agentswarm_platform.credibility as credibility
from agentswarm_platform.credibility import (
    BASE_MINT,
    REVIEWER_MINT,
    burn_for_rejection,
    compute_outcome_deltas,
    decay_score,
    mint_for_acceptance,
    stake_amount,
    verifier_weight,
)


def test_high_verifier_mints_more_than_low_verifier() -> None:
    low = mint_for_acceptance(task_tier=1, verifier_score=10.0)
    high = mint_for_acceptance(task_tier=1, verifier_score=200.0)
    assert high > low


def test_verifier_weight_caps() -> None:
    assert verifier_weight(0) == 1.0
    assert verifier_weight(10_000) <= 3.0


def test_acceptance_net_positive_for_submitter() -> None:
    initial = credibility.INITIAL_SCORE
    stake = stake_amount(initial)
    deltas = compute_outcome_deltas(
        accepted=True,
        submitter_capability="codewriter",
        task_tier=1,
        stake=stake,
        verifier_score=initial,
    )
    assert deltas.submitter_delta > 0
    assert deltas.reviewer_delta == REVIEWER_MINT


def test_rejection_net_negative_for_submitter() -> None:
    initial = credibility.INITIAL_SCORE
    stake = stake_amount(initial)
    deltas = compute_outcome_deltas(
        accepted=False,
        submitter_capability="codewriter",
        task_tier=1,
        stake=stake,
        verifier_score=initial,
    )
    assert deltas.submitter_delta == -burn_for_rejection(1)
    assert deltas.submitter_delta < 0


def test_collusion_clique_grows_slowly_with_low_verifier_weight() -> None:
    production_threshold = 100.0
    initial = credibility.INITIAL_SCORE
    score = initial
    rounds = 15
    for _ in range(rounds):
        score += mint_for_acceptance(task_tier=1, verifier_score=initial)
    assert score < production_threshold
    assert score < initial + rounds * BASE_MINT * 1.25


def test_decay_halves_at_half_life() -> None:
    assert math.isclose(decay_score(100.0, 180.0), 50.0, rel_tol=1e-6)
