from agentswarm_platform.credibility_gamification import capability_level


def test_capability_level_thresholds() -> None:
    assert capability_level(0)["label"] == "novice"
    assert capability_level(10)["label"] == "novice"
    assert capability_level(15)["label"] == "apprentice"
    assert capability_level(25)["label"] == "journeyman"
    assert capability_level(49.9)["label"] == "journeyman"
    assert capability_level(50)["label"] == "expert"
    assert capability_level(100)["label"] == "master"


def test_capability_level_next_tier() -> None:
    novice = capability_level(10)
    assert novice["next_at"] == 15.0
    assert novice["next_label"] == "apprentice"
    master = capability_level(150)
    assert master["next_at"] is None
    assert master["next_label"] is None
