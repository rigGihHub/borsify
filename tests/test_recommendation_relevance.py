import json
import pandas as pd

from recommendation_relevance import (
    assess_recommendation_relevance,
    previous_record_for_case,
    apply_recommendation_relevance,
)


def _prior(**overrides):
    row = {
        "record_id": "r1",
        "symbol": "BUFAB.ST",
        "horizon_type": "short",
        "profile": "Balanserad",
        "market": "Sverige",
        "entry_price": 100.0,
        "gate": "Starkt kortsiktigt case",
        "score": 70.0,
        "confidence": 80.0,
        "captured_date": "2026-08-20",
        "captured_at": "2026-08-20T12:00:00+00:00",
        "snapshot_json": json.dumps({"Forward P/E": 15.0, "FCF yield": 0.06}),
    }
    row.update(overrides)
    return row


def test_same_day_snapshot_is_excluded():
    ledger = pd.DataFrame([
        _prior(captured_date="2026-09-02", captured_at="2026-09-02T08:00:00+00:00"),
        _prior(record_id="old", captured_date="2026-09-01", captured_at="2026-09-01T08:00:00+00:00"),
    ])
    prior = previous_record_for_case(
        ledger, "BUFAB.ST", "short", "Balanserad", "Sverige", "2026-09-02"
    )
    assert prior["record_id"] == "old"


def test_price_rise_without_model_improvement_is_less_attractive():
    current = {
        "Pris": 115.0,
        "Short Alpha Gate": "Starkt kortsiktigt case",
        "Short Alpha Score": 71.0,
        "Short Vetoes": "—",
    }
    result = assess_recommendation_relevance(current, _prior(), "short")
    assert result["status"] == "Mindre attraktivt än vid signal"
    assert abs(result["price_return"] - 0.15) < 1e-12


def test_stronger_gate_and_score_is_strengthened():
    current = {
        "Pris": 103.0,
        "Short Alpha Gate": "Kortsiktigt toppcase",
        "Short Alpha Score": 78.0,
        "Short Vetoes": "—",
    }
    result = assess_recommendation_relevance(current, _prior(), "short")
    assert result["status"] == "Caset har stärkts"


def test_hard_veto_weakens_case():
    current = {
        "Pris": 101.0,
        "Short Alpha Gate": "Starkt kortsiktigt case",
        "Short Alpha Score": 72.0,
        "Short Vetoes": "falling knife",
    }
    result = assess_recommendation_relevance(current, _prior(), "short")
    assert result["status"] == "Caset har försvagats"


def test_new_recommendation_when_no_prior():
    current = {"Pris": 100.0, "Case Gate": "Starkt case", "INVEST Score": 80.0}
    result = assess_recommendation_relevance(current, None, "long")
    assert result["status"] == "Ny rekommendation"


def test_apply_adds_relevance_columns_without_changing_rows():
    frame = pd.DataFrame([{
        "Ticker": "BUFAB.ST",
        "Pris": 115.0,
        "Short Alpha Gate": "Starkt kortsiktigt case",
        "Short Alpha Score": 71.0,
        "Short Vetoes": "—",
    }])
    ledger = pd.DataFrame([_prior()])
    out = apply_recommendation_relevance(
        frame, ledger, "short", "Balanserad", "Sverige", "2026-09-02"
    )
    assert len(out) == 1
    assert out.iloc[0]["Relevans nu"] == "Mindre attraktivt än vid signal"
    assert out.iloc[0]["Referenskurs"] == 100.0


def test_valuation_change_is_context_not_automatic_price_judgment():
    current = {
        "Pris": 104.0,
        "Short Alpha Gate": "Starkt kortsiktigt case",
        "Short Alpha Score": 71.0,
        "Short Vetoes": "—",
        "Forward P/E": 18.0,
        "FCF yield": 0.04,
    }
    result = assess_recommendation_relevance(current, _prior(), "short")
    assert "Forward P/E har stigit" in result["explanation"]
    assert "FCF-yield har försämrats" in result["explanation"]
