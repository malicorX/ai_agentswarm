import math

from agentswarm_platform.credibility import (
    BASE_MINT,
    INITIAL_SCORE,
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
    stake = stake_amount(INITIAL_SCORE)
    deltas = compute_outcome_deltas(
        accepted=True,
        submitter_capability="codewriter",
        task_tier=1,
        stake=stake,
        verifier_score=INITIAL_SCORE,
    )
    assert deltas.submitter_delta > 0
    assert deltas.reviewer_delta == REVIEWER_MINT


def test_rejection_net_negative_for_submitter() -> None:
    stake = stake_amount(INITIAL_SCORE)
    deltas = compute_outcome_deltas(
        accepted=False,
        submitter_capability="codewriter",
        task_tier=1,
        stake=stake,
        verifier_score=INITIAL_SCORE,
    )
    assert deltas.submitter_delta == -burn_for_rejection(1)
    assert deltas.submitter_delta < 0


def test_collusion_clique_grows_slowly_with_low_verifier_weight() -> None:
    production_threshold = 100.0
    score = INITIAL_SCORE
    rounds = 15
    for _ in range(rounds):
        score += mint_for_acceptance(task_tier=1, verifier_score=INITIAL_SCORE)
    assert score < production_threshold
    assert score < INITIAL_SCORE + rounds * BASE_MINT * 1.25


def test_decay_halves_at_half_life() -> None:
    assert math.isclose(decay_score(100.0, 180.0), 50.0, rel_tol=1e-6)
