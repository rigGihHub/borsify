import numpy as np
import pandas as pd
from buy_quality_gate import assess_buy_gate, eligible_buys
from horizon_rankings import add_horizon_scores, top_three

def _history():
    idx=pd.date_range(end=pd.Timestamp.today().normalize(),periods=80,freq="B")
    close=np.linspace(90,100,80)
    high=close+1.2
    low=close-1.0
    high[-12]=106
    return pd.DataFrame({"Open":close-.2,"High":high,"Low":low,"Close":close},index=idx)

def strong_row(ticker="GOOD"):
    return {
        "Ticker": ticker,
        "Namn": ticker,
        "Universe QC": "VERIFIERAD",
        "Universe QC Score": 95,
        "Datatäckning": .9,
        "Pris": 100.0,
        "Prisdatum": pd.Timestamp.today().date().isoformat(),
        "Skuld/eget kapital": 35,
        "_history": _history(),
        "Riskflaggor": "—",
        "Dagsförändring": .025,
        "1 mån": .12,
        "3 mån": .24,
        "6 mån": .34,
        "Volymkvot": 1.5,
        "RSI14": 62,
        "Avstånd SMA200": .10,
        "Risk": 78,
        "Kvalitet": 82,
        "Värdering": 72,
        "INVEST Score": 76,
        "ROE": .22,
        "Vinstmarginal": .16,
        "Omsättningstillväxt": .10,
    }

def test_strong_candidate_passes_all_four_buy_gates():
    df=add_horizon_scores(pd.DataFrame([strong_row()]))
    for horizon in ["day","medium","long","lifetime"]:
        gate=assess_buy_gate(df.iloc[0],horizon)
        assert gate["Köpfilter godkänd"] is True
        assert gate["Köpfilter"]=="KÖPCASE"

def test_weak_candidate_is_not_filler_in_top_three():
    good=strong_row("GOOD")
    weak=strong_row("WEAK")
    weak.update({
        "Dagsförändring": -.08, "1 mån": -.25, "3 mån": -.30,
        "Volymkvot": .5, "RSI14": 30, "Avstånd SMA200": -.25,
        "Risk": 25, "Kvalitet": 25, "Värdering": 30, "INVEST Score": 30,
        "ROE": -.05, "Vinstmarginal": -.04, "Omsättningstillväxt": -.15,
        "Riskflaggor": "negativ ROE, negativ marginal, fallande lång trend",
    })
    df=pd.DataFrame([good,weak])
    for horizon in ["day","medium","long","lifetime"]:
        top=top_three(df,horizon)
        assert list(top["Ticker"])==["GOOD"]

def test_no_qualified_buy_returns_empty_list():
    row=strong_row("NOPE")
    row.update({
        "Risk": 10, "Kvalitet": 10, "Värdering": 10, "INVEST Score": 10,
        "Dagsförändring": -.09, "1 mån": -.30, "3 mån": -.40, "6 mån": -.50,
        "Volymkvot": .4, "RSI14": 25, "Avstånd SMA200": -.30,
        "ROE": -.1, "Vinstmarginal": -.1, "Omsättningstillväxt": -.2,
        "Riskflaggor": "negativ ROE, negativ marginal, hög skuldsättning, fallande lång trend",
    })
    df=pd.DataFrame([row])
    for horizon in ["day","medium","long","lifetime"]:
        assert top_three(df,horizon).empty

def test_lifetime_gate_requires_durable_quality_not_just_cheapness():
    row=strong_row()
    row["Kvalitet"]=35
    row["Värdering"]=95
    row["Risk"]=80
    df=add_horizon_scores(pd.DataFrame([row]))
    gate=assess_buy_gate(df.iloc[0],"lifetime")
    assert gate["Köpfilter godkänd"] is False
    assert "kvaliteten" in gate["Köpfilter stopp"]

def test_day_gate_rejects_extreme_overextension():
    row=strong_row()
    row["RSI14"]=86
    df=add_horizon_scores(pd.DataFrame([row]))
    gate=assess_buy_gate(df.iloc[0],"day")
    assert gate["Köpfilter godkänd"] is False
    assert "RSI" in gate["Köpfilter stopp"]
