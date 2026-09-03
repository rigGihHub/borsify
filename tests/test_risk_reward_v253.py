import numpy as np
import pandas as pd

from risk_reward import build_risk_reward, risk_reward_rank_value

def make_history(n=80):
    idx=pd.date_range("2026-01-01", periods=n, freq="B")
    close=np.linspace(90,100,n)
    # Create prior traded highs above the latest close so targets are observed levels.
    high=close+1.0
    low=close-1.0
    if n >= 12:
        high[-12]=104.0
    if n >= 35:
        high[-35]=108.0
    return pd.DataFrame({
        "Open":close-.2,
        "High":high,
        "Low":low,
        "Close":close,
    }, index=idx)

def test_risk_reward_uses_only_existing_history_levels():
    row={"Pris":100.0,"_history":make_history()}
    plan=build_risk_reward(row,"day")
    assert plan["RR status"] in {"ATTRAKTIVT","GODKÄNT","SVAGT","DÅLIGT"}
    assert plan["Stop"] < 100
    assert plan["Mål 1"] > 100
    assert plan["Entry låg"] == 100
    assert plan["Entry hög"] >= 100
    assert plan["RR 1"] > 0

def test_no_prior_high_means_no_invented_target():
    hist=make_history()
    hist["High"]=np.minimum(hist["High"],99.5)
    hist["Low"]=np.minimum(hist["Low"],98.5)
    hist["Close"]=np.minimum(hist["Close"],99.0)
    row={"Pris":100.0,"_history":hist}
    plan=build_risk_reward(row,"day")
    assert plan["RR status"]=="INGEN TYDLIG MÅLNIVÅ"
    assert "Mål 1" not in plan

def test_insufficient_history_is_explicit():
    row={"Pris":100.0,"_history":make_history(10)}
    plan=build_risk_reward(row,"medium")
    assert plan["RR status"]=="FÖR LITE DATA"

def test_long_horizon_does_not_fake_trade_levels():
    plan=build_risk_reward({"Pris":100.0,"_history":make_history()},"long")
    assert plan["RR status"]=="EJ TILLÄMPLIGT"
    assert "Entry låg" not in plan

def test_rank_value_is_secondary_numeric_metric():
    assert risk_reward_rank_value({"RR 1":2.4}) == 2.4
    assert risk_reward_rank_value({"RR status":"FÖR LITE DATA"}) == -1.0
