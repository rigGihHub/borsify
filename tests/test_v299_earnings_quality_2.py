import pandas as pd
from pathlib import Path

from earnings_quality import build_earnings_quality_metrics, assess_earnings_quality

DATES = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])

def frame(rows):
    return pd.DataFrame(rows, index=DATES).T


def test_cash_flow_accrual_ratio_uses_average_assets():
    income = frame({"Net Income": [150, 100, 90, 80], "Total Revenue": [1000, 900, 820, 760]})
    cash = frame({"Operating Cash Flow": [80, 95, 92, 85], "Free Cash Flow": [60, 70, 65, 60]})
    balance = frame({"Total Assets": [1000, 900, 850, 800]})
    m = build_earnings_quality_metrics(income, cash, balance)
    # (150 - 80) / average(1000, 900)
    assert round(m["Accruals/tillgångar senaste"], 6) == round(70 / 950, 6)


def test_high_positive_accruals_raise_warning():
    income = frame({"Net Income": [220, 200, 180, 160], "Total Revenue": [1000, 900, 820, 760]})
    cash = frame({"Operating Cash Flow": [60, 70, 75, 80], "Free Cash Flow": [40, 45, 50, 55]})
    balance = frame({"Total Assets": [900, 820, 750, 700]})
    r = assess_earnings_quality(build_earnings_quality_metrics(income, cash, balance))
    assert r["Periodiseringsrisk status"] == "FÖRHÖJD RISK"
    assert "saknar stöd" in r["Vinstkvalitet varningar"]


def test_profit_growth_outpacing_cash_is_flagged():
    income = frame({"Net Income": [150, 100, 95, 90], "Total Revenue": [1000, 900, 850, 800]})
    cash = frame({"Operating Cash Flow": [100, 100, 95, 90], "Free Cash Flow": [80, 78, 75, 70]})
    balance = frame({"Total Assets": [1000, 950, 900, 850]})
    r = assess_earnings_quality(build_earnings_quality_metrics(income, cash, balance))
    assert r["Vinst minus OCF tillväxtgap"] >= 0.49
    assert "vinsten växer klart snabbare" in r["Vinstkvalitet varningar"]


def test_missing_assets_do_not_invent_accruals():
    income = frame({"Net Income": [100, 90, 80, 70]})
    cash = frame({"Operating Cash Flow": [110, 100, 90, 80]})
    r = build_earnings_quality_metrics(income, cash, pd.DataFrame())
    assert pd.isna(r["Accruals/tillgångar senaste"])
    assert pd.isna(r["Accruals/tillgångar median"])


def test_v299_ui_and_version_are_present():
    app = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.26.0"' in app
    assert "Bokförd vinst utan kassastöd / tillgångar" in app
    assert "vinsten växer snabbare än pengarna" in app


def test_v299_point_in_time_ledger_freezes_new_quality_fields():
    ledger = (Path(__file__).resolve().parents[1] / "recommendation_ledger.py").read_text(encoding="utf-8")
    assert '"Accruals/tillgångar senaste"' in ledger
    assert '"Vinst minus OCF tillväxtgap"' in ledger
    assert '"Periodiseringsrisk status"' in ledger
