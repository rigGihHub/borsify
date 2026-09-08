from datetime import date

import numpy as np
import pandas as pd

from investment_company_engine import (
    add_investment_company_context,
    evaluate_investment_company,
    identify_investment_company,
)


def _universe(industry_price: float = 400.0):
    rows = [
        {"Ticker": "INDU-C.ST", "Namn": "Industrivärden C", "Pris": industry_price, "Pris SEK": industry_price, "Valuta": "SEK", "Borsify Score": 78},
        {"Ticker": "VOLV-B.ST", "Namn": "Volvo", "Borsify Score": 70},
        {"Ticker": "SAND.ST", "Namn": "Sandvik", "Borsify Score": 76},
        {"Ticker": "SHB-A.ST", "Namn": "Handelsbanken", "Borsify Score": 67},
        {"Ticker": "ESSITY-B.ST", "Namn": "Essity", "Borsify Score": 69},
        {"Ticker": "SCA-B.ST", "Namn": "SCA", "Borsify Score": 64},
        {"Ticker": "SKA-B.ST", "Namn": "Skanska", "Borsify Score": 66},
        {"Ticker": "ERIC-B.ST", "Namn": "Ericsson", "Borsify Score": 62},
        {"Ticker": "ALLEI.ST", "Namn": "Alleima", "Borsify Score": 75},
    ]
    return pd.DataFrame(rows)


def test_identifies_known_investment_company_without_guessing_nav():
    ok, name, profile = identify_investment_company("SVOL-B.ST", "Svolder", "Financial Services")
    assert ok is True
    assert name == "Svolder"
    assert profile is None


def test_industrivarden_uses_nav_discount_and_underlying_holdings():
    df = _universe(400.0)
    result = evaluate_investment_company(df.iloc[0], df, today=date(2026, 9, 7))
    assert result["Investmentbolag"] is True
    assert result["Investmentbolag namn"] == "Industrivärden"
    assert np.isclose(result["Investmentbolag substansrabatt"], 1 - 400 / 532)
    assert result["Investmentbolag innehavstäckning"] >= 0.99
    assert result["Investmentbolag direktval"] == "Investmentbolaget ser bättre ut"
    assert result["Investmentbolag rankningstak"] == 100.0


def test_premium_can_cap_daily_relevance_instead_of_creating_new_score():
    df = _universe(560.0)
    result = evaluate_investment_company(df.iloc[0], df, today=date(2026, 9, 7))
    assert result["Investmentbolag direktval"] == "Innehaven direkt kan vara bättre"
    assert result["Investmentbolag rankningstak"] <= 68.0


def test_unknown_investment_company_gets_data_gate():
    row = pd.Series({"Ticker": "SVOL-B.ST", "Namn": "Svolder", "Pris": 50, "Valuta": "SEK", "Borsify Score": 80})
    result = evaluate_investment_company(row, pd.DataFrame([row]), today=date(2026, 9, 7))
    assert result["Investmentbolag direktval"] == "Otillräcklig data"
    assert result["Investmentbolag rankningstak"] == 70.0


def test_context_is_attached_without_mutating_borsify_score():
    df = _universe(400.0)
    out = add_investment_company_context(df, today=date(2026, 9, 7))
    original = float(df.loc[df["Ticker"] == "INDU-C.ST", "Borsify Score"].iloc[0])
    current = float(out.loc[out["Ticker"] == "INDU-C.ST", "Borsify Score"].iloc[0])
    assert current == original
    assert bool(out.loc[out["Ticker"] == "INDU-C.ST", "Investmentbolag"].iloc[0]) is True
