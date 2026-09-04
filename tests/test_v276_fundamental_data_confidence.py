import pandas as pd

from fundamental_data_confidence import assess_fundamental_data_confidence
from case_quality_gate import build_case_quality_gate


def frame(date):
    return pd.DataFrame({pd.Timestamp(date): [1.0]}, index=["x"])


def test_current_complete_statements_are_strong():
    raw = {
        "income": frame("2026-06-30"), "cashflow": frame("2026-06-30"), "balance": frame("2026-06-30"),
        "quarterly_income": frame("2026-06-30"), "quarterly_cashflow": frame("2026-06-30"), "quarterly_balance": frame("2026-06-30"),
    }
    out = assess_fundamental_data_confidence(raw, {"Deep Confidence": 75}, now="2026-09-03")
    assert out["Fundamental Data status"] == "STARKT UNDERLAG"
    assert out["Fundamental Data senaste rapportperiod"] == "2026-06-30"
    assert out["Fundamental Data årsrapporter"] == 3
    assert out["Fundamental Data kvartalsrapporter"] == 3


def test_stale_statement_period_is_hard_stop():
    raw = {
        "income": frame("2025-12-31"), "cashflow": frame("2025-12-31"), "balance": frame("2025-12-31"),
        "quarterly_income": pd.DataFrame(), "quarterly_cashflow": pd.DataFrame(), "quarterly_balance": pd.DataFrame(),
    }
    out = assess_fundamental_data_confidence(raw, {"Deep Confidence": 75}, now="2026-09-03")
    assert out["Fundamental Data status"] == "STOPP"
    assert "dagar gammal" in out["Fundamental Data stopp"]


def test_missing_statement_dates_are_not_inferred():
    undated = pd.DataFrame({"not-a-date": [1.0]}, index=["x"])
    raw = {
        "income": undated, "cashflow": undated, "balance": undated,
        "quarterly_income": pd.DataFrame(), "quarterly_cashflow": pd.DataFrame(), "quarterly_balance": pd.DataFrame(),
    }
    out = assess_fundamental_data_confidence(raw, {"Deep Confidence": 70}, now="2026-09-03")
    assert out["Fundamental Data status"] == "STOPP"
    assert out["Fundamental Data senaste rapportperiod"] == "—"
    assert "kan inte verifieras" in out["Fundamental Data stopp"]


def test_fundamental_stop_vetoes_case_quality_gate():
    case = {
        "Djupkontroll": "Klarar djupkontroll", "Value Trap Risk": 10, "Deep Confidence": 80,
        "Inflection Confidence": 80, "Inflection Signal": "Positiv inflektion",
        "Mispricing Signal": "Tydlig möjlig felprissättning", "Scenario Status": "OK",
        "Scenario Verdict": "Attraktiv asymmetri", "Scenario Asymmetry": 2.5, "Scenario Confidence": 80,
        "Catalyst Signal": "Tydlig möjlig katalysator", "Catalyst Support": True, "Catalyst Confidence": 80,
        "Fundamental Data status": "STOPP", "Fundamental Data stopp": "senaste rapportperioden är för gammal",
    }
    out = build_case_quality_gate(case)
    assert out["Case Gate"] == "Ej toppcase"
    assert "fundamentala data" in out["Case Vetoes"]
