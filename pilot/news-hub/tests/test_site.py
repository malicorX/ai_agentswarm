from pathlib import Path

PILOT_ROOT = Path(__file__).resolve().parents[1]


def test_index_has_title():
    html = (PILOT_ROOT / "index.html").read_text(encoding="utf-8")
    assert "<title>AI News Hub</title>" in html
    assert "AI News Hub" in html


def test_agentswarm_marker_present():
    html = (PILOT_ROOT / "index.html").read_text(encoding="utf-8")
    assert "<!-- agentswarm -->" in html
