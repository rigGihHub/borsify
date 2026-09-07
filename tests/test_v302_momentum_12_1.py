import numpy as np
import pandas as pd

from momentum_12_1 import momentum_12_1_return, momentum_12_1_score, combine_momentum
from short_term_engine import assess_short_term_case


def test_12_1_excludes_latest_month():
    # Stable rise until one month ago, then a vertical latest-month rally.
    pre = np.linspace(100, 140, 240)
    last = np.linspace(140, 210, 22)
    close = pd.Series(np.r_[pre, last])
    r = momentum_12_1_return(close)
    assert 0.25 < r < 0.5
    # It must not include the final 210 price.
    assert r < (210 / 100 - 1)


def test_12_1_requires_long_history():
    assert np.isnan(momentum_12_1_return(pd.Series(np.linspace(100, 120, 150))))


def test_long_momentum_does_not_replace_recent_timing():
    combined, text = combine_momentum(25, 85)
    assert 25 < combined < 85
    assert "senaste tiden är svag" in text


def test_short_engine_exposes_separate_momentum_evidence():
    row = {
        "Pris": 110, "SMA50": 105, "Avstånd SMA200": .05,
        "1 mån": .04, "3 mån": .12, "6 mån": .22,
        "12–1 momentum": .30, "12–1 momentum score": momentum_12_1_score(.30),
        "Dagsförändring": .01, "RSI14": 55, "Volymkvot": 1.1,
        "Risk": 30, "Omsättning MSEK/dag": 50, "Riskflaggor": "",
    }
    r = assess_short_term_case(row, {"month": 0, "3m": .02, "6m": .04})
    assert r["Short Recent Momentum"] > 50
    assert r["Short 12–1 Momentum"] > 50
    assert 0 <= r["Short Momentum"] <= 100
    assert r["Short Momentum Text"]


def test_app_version_and_ledger_freeze_new_fields():
    app = open("app.py", encoding="utf-8").read()
    ledger = open("recommendation_ledger.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert '"12–1 momentum"' in ledger
    assert '"Short 12–1 Momentum"' in ledger
