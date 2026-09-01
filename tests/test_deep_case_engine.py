import numpy as np
import pandas as pd

from deep_case_engine import build_deep_metrics, value_trap_risk, evidence_confidence, assess_deep_case, deep_rank_key


def _statements():
    cols = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
    income = pd.DataFrame(
        [
            [140, 125, 112, 100],
            [22, 17, 12, 8],
            [17, 13, 9, 6],
        ],
        index=["Total Revenue", "Operating Income", "Net Income"],
        columns=cols,
    )
    cash = pd.DataFrame([[16, 12, 9, 5]], index=["Free Cash Flow"], columns=cols)
    balance = pd.DataFrame(
        [
            [25, 30, 35, 40],
            [10, 9, 8, 7],
        ],
        index=["Total Debt", "Cash And Cash Equivalents"],
        columns=cols,
    )
    return income, cash, balance


def test_build_deep_metrics_detects_positive_inflection():
    income, cash, balance = _statements()
    m = build_deep_metrics(income, cash, balance)
    assert m["Historik år"] == 4
    assert m["Omsättning CAGR"] > 0.10
    assert m["FCF CAGR"] > 0.40
    assert m["Rörelsemarginal trend"] > 0.07
    assert m["Skuldförändring"] < -0.30
    assert m["Positiv FCF-andel"] == 1.0


def test_value_trap_risk_penalizes_deterioration():
    metrics = {
        "Senaste FCF": -10,
        "Positiv FCF-andel": 0.25,
        "Omsättning CAGR": -0.08,
        "Vinstförändring": -0.60,
        "FCF-förändring": -0.50,
        "Rörelsemarginal trend": -0.08,
        "Skuldförändring": 0.60,
    }
    snapshot = {"Skuld/eget kapital": 320, "Vinstmarginal": -0.05, "ROE": -0.10}
    risk, reasons = value_trap_risk(metrics, snapshot)
    assert risk == 100
    assert len(reasons) >= 6


def test_confidence_is_capped_with_thin_history():
    metrics = {"Historik år": 2, "Omsättning CAGR": 0.1, "Vinstförändring": 0.2}
    snapshot = {"P/E": 15, "Forward P/E": 14, "FCF-yield": 0.05, "ROE": 0.15, "Vinstmarginal": 0.1, "Skuld/eget kapital": 40}
    score, notes = evidence_confidence(metrics, snapshot)
    assert score <= 58
    assert any("tre års" in x for x in notes)


def test_good_history_can_pass_deep_check():
    income, cash, balance = _statements()
    metrics = build_deep_metrics(income, cash, balance)
    snapshot = {
        "Värdering": 72, "P/E": 14, "Forward P/E": 13, "FCF-yield": 0.06,
        "ROE": 0.18, "Vinstmarginal": 0.12, "Skuld/eget kapital": 45,
    }
    result = assess_deep_case(metrics, snapshot)
    assert result["Value Trap Risk"] < 25
    assert result["Deep Confidence"] >= 70
    assert result["Djupkontroll"] == "Klarar djupkontroll"
    assert "omsättningen" in result["Varför marknaden kan ha fel"].lower()


def test_gate_first_ranking_beats_raw_invest_score():
    good = {"Djupkontroll": "Klarar djupkontroll", "Value Trap Risk": 10, "Deep Confidence": 80, "INVEST Score": 70}
    bad = {"Djupkontroll": "Hög value-trap-risk", "Value Trap Risk": 55, "Deep Confidence": 90, "INVEST Score": 95}
    assert deep_rank_key(good) > deep_rank_key(bad)
