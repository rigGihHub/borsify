import numpy as np
import pandas as pd
import pytest

from inflection_engine import build_inflection_metrics, assess_inflection, apply_inflection_gate, inflection_rank_value


def _quarters(values, row):
    cols = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31"])
    return pd.DataFrame([values], index=[row], columns=cols)


def test_positive_inflection_detects_acceleration_margin_and_revisions():
    cols = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31"])
    income = pd.DataFrame(
        [
            [130, 112, 108, 103, 100, 98],
            [26, 18, 17, 15, 14, 13],
            [20, 14, 13, 11, 10, 9],
        ],
        index=["Total Revenue", "Operating Income", "Net Income"],
        columns=cols,
    )
    cashflow = pd.DataFrame([[24, 17, 15, 13, 12, 11]], index=["Free Cash Flow"], columns=cols)
    eps_trend = pd.DataFrame(
        {"current": [12.0], "30daysAgo": [10.0], "60daysAgo": [9.8], "90daysAgo": [9.5]},
        index=["+1y"],
    )
    revisions = pd.DataFrame({"upLast30days": [5], "downLast30days": [1]}, index=["+1y"])
    earnings_history = pd.DataFrame({"surprisePercent": [0.08]}, index=pd.to_datetime(["2026-07-20"]))

    metrics = build_inflection_metrics(income, cashflow, eps_trend, revisions, earnings_history)
    result = assess_inflection(metrics)

    assert metrics["EPS-estimat förändring"] == pytest.approx(0.2)
    assert metrics["Omsättning acceleration"] > 0
    assert metrics["Marginal YoY förändring"] > 0
    assert result["Inflection Signal"] == "Positiv inflektion"
    assert result["Inflection Score"] >= 72
    assert "EPS-estimat" in result["Varför nu"]


def test_negative_revisions_are_harder_to_offset_and_can_downgrade_gate():
    metrics = {
        "EPS-estimat förändring": -0.10,
        "EPS-revisionsbalans": -0.8,
        "Omsättning YoY senaste kvartal": 0.05,
        "Omsättning acceleration": 0.01,
        "Marginal YoY förändring": -0.04,
        "Marginal QoQ förändring": -0.01,
        "FCF YoY senaste kvartal": 0.10,
        "Vinst YoY senaste kvartal": -0.30,
        "Senaste EPS-överraskning": -0.08,
    }
    assessed = assess_inflection(metrics)
    assert assessed["Inflection Signal"] == "Tydlig försämring"
    assert assessed["Inflection Score"] <= 35

    case = {"Djupkontroll": "Klarar djupkontroll", **assessed}
    gated = apply_inflection_gate(case)
    assert gated["Djupkontroll"] == "Kräver extra kontroll"
    assert "sänktes" in gated["Inflection Gate Note"]


def test_positive_inflection_cannot_rescue_value_trap_gate():
    case = {
        "Djupkontroll": "Hög value-trap-risk",
        "Inflection Signal": "Positiv inflektion",
        "EPS-estimat förändring": 0.15,
    }
    assert apply_inflection_gate(case)["Djupkontroll"] == "Hög value-trap-risk"


def test_missing_analyst_data_stays_missing_but_quarterly_data_can_still_help():
    cols = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31"])
    income = pd.DataFrame(
        [[120, 108, 104, 101, 100, 98], [22, 18, 17, 16, 15, 14]],
        index=["Total Revenue", "Operating Income"], columns=cols,
    )
    metrics = build_inflection_metrics(income, pd.DataFrame())
    assert np.isnan(metrics["EPS-estimat förändring"])
    result = assess_inflection(metrics)
    assert result["Inflection Evidence Count"] >= 2
    assert "EPS-estimat" not in result["Positiva förändringar"]


def test_rank_value_prefers_positive_inflection():
    assert inflection_rank_value({"Inflection Signal": "Positiv inflektion"}) > inflection_rank_value({"Inflection Signal": "Neutral / oklar förändring"})
    assert inflection_rank_value({"Inflection Signal": "Neutral / oklar förändring"}) > inflection_rank_value({"Inflection Signal": "Tydlig försämring"})
