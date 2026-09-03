import pandas as pd

from buy_quality_gate import assess_buy_gate, BUY_THRESHOLDS
from horizon_rankings import add_horizon_scores

def strong_row():
    return {
        "Ticker":"STRONG",
        "Universe QC":"VERIFIERAD",
        "Datatäckning":.90,
        "Riskflaggor":"—",
        "Dagsförändring":.025,
        "1 mån":.12,
        "3 mån":.24,
        "6 mån":.34,
        "Volymkvot":1.5,
        "RSI14":62,
        "Avstånd SMA200":.10,
        "Risk":78,
        "Kvalitet":82,
        "Värdering":72,
        "INVEST Score":76,
        "ROE":.22,
        "Vinstmarginal":.16,
        "Omsättningstillväxt":.10,
    }

def scored(row):
    return add_horizon_scores(pd.DataFrame([row])).iloc[0]

def test_v250_raises_all_buy_thresholds():
    assert BUY_THRESHOLDS == {
        "day":68.0,
        "medium":66.0,
        "long":65.0,
        "lifetime":68.0,
    }

def test_day_buy_needs_enough_short_term_data():
    row=strong_row()
    row["Volymkvot"]=None
    row["RSI14"]=None
    gate=assess_buy_gate(scored(row),"day")
    assert gate["Köpfilter godkänd"] is False
    assert "för lite relevant data" in gate["Köpfilter stopp"]

def test_long_buy_needs_better_fundamental_coverage():
    row=strong_row()
    row["Datatäckning"]=.50
    gate=assess_buy_gate(scored(row),"long")
    assert gate["Köpfilter godkänd"] is False
    assert "för lite relevant data" in gate["Köpfilter stopp"]

def test_lifetime_buy_needs_at_least_two_durable_strengths():
    row=strong_row()
    row.update({
        "Kvalitet":64,
        "Risk":60,
        "ROE":.11,
        "Vinstmarginal":.05,
        "Värdering":100,
        "Omsättningstillväxt":.12,
    })
    gate=assess_buy_gate(scored(row),"lifetime")
    assert gate["Köpfilter godkänd"] is False
    assert "uthållig kvalitet" in gate["Köpfilter stopp"]

def test_strong_candidate_still_passes_all_horizons():
    row=scored(strong_row())
    for horizon in ("day","medium","long","lifetime"):
        assert assess_buy_gate(row,horizon)["Köpfilter godkänd"] is True
