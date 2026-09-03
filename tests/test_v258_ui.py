from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_258_or_newer():
    assert 'APP_VERSION = "2.57.0"' not in APP

def test_fundamental_change_ui_is_plain_and_separates_observed_from_estimates():
    assert "**Vad förändras i själva bolaget?**" in APP
    assert "observerad försäljning, marginal, vinst, kassaflöde och skuld" in APP
    assert "separat från analytikernas prognoser" in APP
    assert "Konflikt mellan bolagsdata och analytiker" in APP
