from pathlib import Path
import pandas as pd

from expectation_acceleration_engine import build_expectation_acceleration, select_expectation_acceleration_candidates
from finalist_selection import select_deep_finalist_pool


def _trend(current=1.10, d7=1.07, d30=1.05):
    return pd.DataFrame([{"current": current, "7daysAgo": d7, "30daysAgo": d30}], index=["+1y"])


def _revisions(up7=3, down7=0, up30=5, down30=1):
    return pd.DataFrame([{"upLast7days": up7, "downLast7days": down7, "upLast30days": up30, "downLast30days": down30}], index=["+1y"])


def _metrics():
    return {"Estimat tillförlitlighetsvikt": .75, "Analytiker antal": 6}


def test_acceleration_requires_recent_positive_concentration_and_confirmation():
    out = build_expectation_acceleration(_trend(), _revisions(), _metrics(), {"Fundamental förändring antal": 1})
    assert out["Förväntningsacceleration kandidat"] is True
    assert out["Förväntningsacceleration stark"] is True
    assert out["EPS förändring 7d"] > 0
    assert not any("score" in k.lower() for k in out)


def test_missing_or_negative_recent_estimates_never_get_promoted():
    missing = build_expectation_acceleration(pd.DataFrame(), _revisions(), _metrics(), {"Fundamental förändring antal": 2})
    negative = build_expectation_acceleration(_trend(current=.98, d7=1.02, d30=1.01), _revisions(), _metrics(), {"Fundamental förändring antal": 2})
    assert missing["Förväntningsacceleration kandidat"] is False
    assert negative["Förväntningsacceleration kandidat"] is False


def test_selector_is_deterministic_and_prefers_strong_confirmed_case():
    df = pd.DataFrame([
        {"Ticker": "B.ST", "Förväntningsacceleration kandidat": True, "Förväntningsacceleration stark": False, "EPS förändring 7d": .04, "Revisionsbalans 7d": 1.0, "Fundamental förändring antal": 0},
        {"Ticker": "A.ST", "Förväntningsacceleration kandidat": True, "Förväntningsacceleration stark": True, "EPS förändring 7d": .02, "Revisionsbalans 7d": .8, "Fundamental förändring antal": 2},
    ])
    out = select_expectation_acceleration_candidates(df, quota=1)
    assert out == [(1, "Förväntningsacceleration")]


def test_finalist_pool_uses_only_one_expectation_family_slot_and_acceleration_has_priority():
    base = {
        "Kvalitet": 60, "Daytrade Score": 60, "Mellan Score": 60, "Lång Score": 60, "Livstid Score": 60,
        "REVERSAL Score": 50, "Värdering": 60, "Datatäckning": 80, "Estimat Radar kandidat": False,
        "Förväntningsacceleration kandidat": False, "Förväntningsacceleration stark": False,
    }
    rows = [
        {**base, "Ticker": "INV1.ST", "INVEST Score": 95},
        {**base, "Ticker": "INV2.ST", "INVEST Score": 90},
        {**base, "Ticker": "ACC.ST", "INVEST Score": 50, "Förväntningsacceleration kandidat": True, "Förväntningsacceleration stark": True, "EPS förändring 7d": .03, "Revisionsbalans 7d": 1.0, "Fundamental förändring antal": 1},
        {**base, "Ticker": "REV.ST", "INVEST Score": 50, "Estimat Radar kandidat": True, "Estimat Radar underreaktion": True, "Estimat tillförlitlighetsvikt": .8, "EPS-revisionsbalans": .8, "EPS-estimat förändring": .08, "Analytiker antal": 8},
    ]
    out = select_deep_finalist_pool(pd.DataFrame(rows), pool_size=3)
    assert out["Ticker"].tolist() == ["INV1.ST", "INV2.ST", "ACC.ST"]
    assert out.iloc[2]["Djupurval Nyckel"] == "expectation_acceleration"


def test_v354_wiring_and_version():
    app = Path("app.py").read_text(encoding="utf-8")
    final = Path("finalist_selection.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.81.0"' in app
    assert "build_expectation_acceleration" in app
    assert "Förväntningar som accelererar" in app
    assert "select_expectation_acceleration_candidates" in final
