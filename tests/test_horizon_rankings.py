import numpy as np
import pandas as pd
from horizon_rankings import add_horizon_scores, top_three

def _history():
    idx=pd.date_range(end=pd.Timestamp.today().normalize(),periods=80,freq="B")
    close=np.linspace(90,100,80)
    high=close+1.2
    low=close-1.0
    high[-12]=106
    return pd.DataFrame({"Open":close-.2,"High":high,"Low":low,"Close":close},index=idx)

def sample():
    df=pd.DataFrame([
        {"Ticker":"A","Namn":"A","Dagsförändring":.03,"1 mån":.12,"3 mån":.20,"6 mån":.30,"Volymkvot":1.8,"RSI14":62,"Avstånd SMA200":.12,"Risk":80,"Kvalitet":82,"Värdering":65,"INVEST Score":80,"ROE":.22,"Vinstmarginal":.16,"Omsättningstillväxt":.10,"Datatäckning":.9},
        {"Ticker":"B","Namn":"B","Dagsförändring":-.02,"1 mån":-.05,"3 mån":-.10,"6 mån":-.05,"Volymkvot":.7,"RSI14":35,"Avstånd SMA200":-.15,"Risk":45,"Kvalitet":50,"Värdering":80,"INVEST Score":55,"ROE":.08,"Vinstmarginal":.04,"Omsättningstillväxt":0,"Datatäckning":.9},
        {"Ticker":"C","Namn":"C","Dagsförändring":.01,"1 mån":.05,"3 mån":.10,"6 mån":.18,"Volymkvot":1.1,"RSI14":58,"Avstånd SMA200":.05,"Risk":70,"Kvalitet":75,"Värdering":70,"INVEST Score":74,"ROE":.18,"Vinstmarginal":.12,"Omsättningstillväxt":.07,"Datatäckning":.8},
        {"Ticker":"D","Namn":"D","Dagsförändring":0,"1 mån":.02,"3 mån":.04,"6 mån":.08,"Volymkvot":1.0,"RSI14":55,"Avstånd SMA200":.02,"Risk":90,"Kvalitet":92,"Värdering":45,"INVEST Score":78,"ROE":.28,"Vinstmarginal":.22,"Omsättningstillväxt":.08,"Datatäckning":.95},
    ])
    df["Universe QC"]="VERIFIERAD"
    df["Universe QC Score"]=95
    df["Pris"]=100.0
    df["Prisdatum"]=pd.Timestamp.today().date().isoformat()
    df["Skuld/eget kapital"]=35
    df["Riskflaggor"]="—"
    df["_history"]=[_history() for _ in range(len(df))]
    return df

def test_all_horizon_scores_are_bounded():
    out=add_horizon_scores(sample())
    for col in ["Daytrade Score","Mellan Score","Lång Score","Livstid Score"]:
        assert out[col].between(0,100).all()

def test_daytrade_prefers_strong_momentum_liquidity_combo():
    top=top_three(sample(),"day")
    assert top.iloc[0]["Ticker"]=="A"

def test_lifetime_rewards_quality_and_robustness():
    top=top_three(sample(),"lifetime")
    assert top.iloc[0]["Ticker"] in {"A","D"}
    assert "Horisontförklaring" in top.columns

def test_top_three_has_at_most_three_rows():
    result = top_three(sample(),"medium")
    assert 0 <= len(result) <= 3
