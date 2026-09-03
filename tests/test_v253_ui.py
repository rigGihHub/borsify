from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_253_or_newer():
    assert 'APP_VERSION = "2.52.0"' not in APP

def test_risk_reward_is_visible_in_plain_swedish():
    assert "**Risk jämfört med möjlig uppsida**" in APP
    assert "Rimligt köpområde enligt modellen" in APP
    assert "Analysen anses fel under ungefär" in APP
    assert "Möjlig uppsida per riskenhet" in APP
