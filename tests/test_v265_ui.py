from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_265_or_newer():
    assert 'APP_VERSION = "2.64.0"' not in APP

def test_liquidity_is_visible_and_plain_swedish():
    assert "**Går aktien rimligt att handla?**" in APP
    assert "Borsify använder dagsdata här – inte realtid" in APP
    assert "Aktuell spread och orderboksdjup kan därför inte verifieras" in APP

def test_one_to_two_day_view_does_not_claim_intraday_signal():
    assert "inte en realtids- eller intradagssignal" in APP
