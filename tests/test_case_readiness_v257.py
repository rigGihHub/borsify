import numpy as np
import pandas as pd

from case_readiness import assess_case_readiness, add_case_readiness, filter_top_case_ready

def history(n=80):
    idx=pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="B")
    close=np.linspace(90,100,n)
    high=close+1.2
    low=close-1.0
    high[-12]=106.0
    return pd.DataFrame({"Open":close-.2,"High":high,"Low":low,"Close":close},index=idx)

def strong_medium_row():
    return {
        "Ticker":"TEST.ST",
        "Pris":100.0,
        "Prisdatum":pd.Timestamp.today().date().isoformat(),
        "Universe QC":"VERIFIERAD",
        "Datatäckning":.85,
        "1 mån":.08,
        "3 mån":.16,
        "6 mån":.22,
        "Kvalitet":72,
        "Risk":70,
        "Värdering":65,
        "Relativ styrka":72,
        "Skuld/eget kapital":40,
        "Riskflaggor":"",
        "_history":history(),
    }

def test_strong_case_can_be_top_case_ready():
    result=assess_case_readiness(strong_medium_row(),"medium")
    assert result["Case Readiness godkänd"] is True
    assert result["Case Readiness"] >= 60
    assert result["Case Readiness status"] in {"TILLRÄCKLIGT UNDERBYGGT","MYCKET VÄL UNDERBYGGT"}

def test_serious_risk_flag_blocks_even_well_scored_evidence():
    row=strong_medium_row()
    row["Riskflaggor"]="hög skuldsättning"
    result=assess_case_readiness(row,"medium")
    assert result["Case Readiness godkänd"] is False
    assert "allvarlig riskflagga" in result["Case Readiness stopp"]

def test_missing_data_is_not_filled_with_neutral_values():
    row=strong_medium_row()
    for field in ["1 mån","3 mån","6 mån","Kvalitet","Risk","Värdering","Datatäckning"]:
        row[field]=np.nan
    result=assess_case_readiness(row,"medium")
    assert result["Case Readiness"] < 60
    assert result["Case Readiness godkänd"] is False
    assert "datapunkter" in result["Case Readiness luckor"]

def test_missing_risk_history_blocks_short_case():
    row=strong_medium_row()
    row["_history"]=pd.DataFrame()
    result=assess_case_readiness(row,"medium")
    assert result["Case Readiness godkänd"] is False
    assert "riskplanen" in result["Case Readiness stopp"]

def test_filter_removes_cases_with_weak_decision_support():
    good=strong_medium_row()
    bad=strong_medium_row()
    bad["Ticker"]="BAD.ST"
    bad["Riskflaggor"]="negativ marginal"
    frame=add_case_readiness(pd.DataFrame([good,bad]),"medium")
    filtered=filter_top_case_ready(frame)
    assert filtered["Ticker"].tolist()==["TEST.ST"]

def test_readiness_is_explicitly_not_return_forecast_field():
    result=assess_case_readiness(strong_medium_row(),"medium")
    assert "expected_return" not in result
    assert "price_target" not in result
