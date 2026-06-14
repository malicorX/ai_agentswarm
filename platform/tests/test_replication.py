from agentswarm_platform.replication import evaluate_quorum


def test_quorum_met_when_two_of_three_agree() -> None:
    submissions = [
        {"result": {"label": "tech"}},
        {"result": {"label": "tech"}},
    ]
    evaluation = evaluate_quorum(
        task_type="classifier.label",
        submissions=submissions,
        quorum=2,
        slots=3,
    )
    assert evaluation.status == "quorum_met"
    assert evaluation.winning_result == {"label": "tech"}


def test_disputed_when_all_slots_split() -> None:
    submissions = [
        {"result": {"label": "tech"}},
        {"result": {"label": "politics"}},
        {"result": {"label": "sports"}},
    ]
    evaluation = evaluate_quorum(
        task_type="classifier.label",
        submissions=submissions,
        quorum=2,
        slots=3,
    )
    assert evaluation.status == "disputed"
    assert evaluation.winning_result is None


def test_pending_until_enough_submissions() -> None:
    evaluation = evaluate_quorum(
        task_type="classifier.label",
        submissions=[{"result": {"label": "tech"}}],
        quorum=2,
        slots=3,
    )
    assert evaluation.status == "pending"
