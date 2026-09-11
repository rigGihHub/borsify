import pandas as pd

from investment_discipline import (
    build_investment_discipline_metrics,
    assess_investment_discipline,
    apply_investment_discipline_gate,
)


def _frame(rows):
    cols = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31"])
    return pd.DataFrame(rows, columns=cols).T.T


def test_flags_assets_growing_faster_than_sales_and_worse_efficiency():
    cols = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31"])
    income = pd.DataFrame({cols[0]: [105, 8], cols[1]: [100, 12], cols[2]: [95, 14]}, index=["Total Revenue", "Operating Income"])
    cash = pd.DataFrame({cols[0]: [-30], cols[1]: [-16], cols[2]: [-12]}, index=["Capital Expenditure"])
    balance = pd.DataFrame({cols[0]: [170], cols[1]: [120], cols[2]: [100]}, index=["Total Assets"])
    result = assess_investment_discipline(build_investment_discipline_metrics(income, cash, balance), "Industrials")
    assert result["Kapitaldisciplin status"] in {"KAPITALBINDNING ÖKAR", "KRÄVER KONTROLL"}
    assert "tillgångarna växer" in result["Kapitaldisciplin varningar"]


def test_rewards_revenue_growth_without_equal_asset_growth():
    cols = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31"])
    income = pd.DataFrame({cols[0]: [140, 24], cols[1]: [115, 17], cols[2]: [100, 13]}, index=["Total Revenue", "Operating Income"])
    cash = pd.DataFrame({cols[0]: [-8], cols[1]: [-10], cols[2]: [-12]}, index=["Capital Expenditure"])
    balance = pd.DataFrame({cols[0]: [105], cols[1]: [102], cols[2]: [100]}, index=["Total Assets"])
    result = assess_investment_discipline(build_investment_discipline_metrics(income, cash, balance), "Technology")
    assert result["Kapitaldisciplin status"] in {"EFFEKTIV KAPITALANVÄNDNING", "BALANSERAD"}
    assert "omsättningen växer" in result["Kapitaldisciplin styrkor"]


def test_financials_are_not_judged_by_generic_asset_growth_rule():
    result = assess_investment_discipline({"Tillgångstillväxt senaste": 0.5, "Kapitalomsättning trend": -0.5}, "Financial Services")
    assert result["Kapitaldisciplin status"] == "BRANSCHMÅTT SAKNAS"


def test_severe_case_adds_caution_but_not_veto():
    out = apply_investment_discipline_gate({"Kapitaldisciplin status": "KAPITALBINDNING ÖKAR", "Fleråriga varningar": ""})
    assert "kapitalkrävande" in out["Fleråriga varningar"]
    assert "Case Vetoes" not in out


def test_v300_integration_and_version():
    app = open("app.py", encoding="utf-8").read()
    ledger = open("recommendation_ledger.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "build_investment_discipline_metrics" in app
    assert "assess_investment_discipline" in app
    assert '"Kapitaldisciplin status"' in ledger
