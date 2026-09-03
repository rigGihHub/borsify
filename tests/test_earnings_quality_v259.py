import pandas as pd

from earnings_quality import (
    build_earnings_quality_metrics,
    assess_earnings_quality,
    apply_earnings_quality_gate,
)

DATES=pd.to_datetime(["2025-12-31","2024-12-31","2023-12-31","2022-12-31"])

def frame(rows):
    return pd.DataFrame(rows,index=DATES).T

def test_strong_cash_conversion_scores_well():
    income=frame({
        "Net Income":[100,90,80,70],
        "Total Revenue":[1000,900,820,760],
    })
    cash=frame({
        "Operating Cash Flow":[125,110,95,85],
        "Free Cash Flow":[95,85,72,64],
        "Change In Working Capital":[-10,-8,-7,-5],
    })
    balance=frame({
        "Accounts Receivable":[100,95,90,86],
        "Inventory":[80,77,72,68],
    })
    result=assess_earnings_quality(build_earnings_quality_metrics(income,cash,balance))
    assert result["Vinstkvalitet"] >= 55
    assert result["Vinstkvalitet status"] in {"NORMAL VINSTKVALITET","STARK VINSTKVALITET"}

def test_weak_cash_conversion_is_flagged():
    income=frame({
        "Net Income":[100,100,100,100],
        "Total Revenue":[1000,950,900,850],
    })
    cash=frame({
        "Operating Cash Flow":[30,35,40,45],
        "Free Cash Flow":[-10,10,15,20],
    })
    balance=frame({
        "Accounts Receivable":[220,170,135,100],
        "Inventory":[180,140,110,90],
    })
    result=assess_earnings_quality(build_earnings_quality_metrics(income,cash,balance))
    assert result["Vinstkvalitet status"]=="SVAG VINSTKVALITET"
    assert "negativt fritt kassaflöde" in result["Vinstkvalitet hårt stopp"]

def test_missing_statement_rows_remain_missing():
    result=build_earnings_quality_metrics(pd.DataFrame(),pd.DataFrame(),pd.DataFrame())
    assert pd.isna(result["Kassaflöde/vinst senaste"])
    assert pd.isna(result["FCF/vinst median"])

def test_weak_quality_can_downgrade_deep_case():
    case={"Djupkontroll":"Klarar djupkontroll","Vinstkvalitet status":"SVAG VINSTKVALITET"}
    result=apply_earnings_quality_gate(case)
    assert result["Djupkontroll"]=="Kräver extra kontroll"
    assert "kassaflödet" in result["Vinstkvalitet gate note"]
