import numpy as np
import pandas as pd

from inflection_engine import build_inflection_metrics, assess_inflection, apply_inflection_gate

DATES=pd.to_datetime([
    "2026-06-30","2026-03-31","2025-12-31","2025-09-30",
    "2025-06-30","2025-03-31","2024-12-31","2024-09-30",
])

def frame(rows):
    return pd.DataFrame(rows,index=DATES).T

def test_build_metrics_includes_balance_sheet_direction_and_consistency():
    income=frame({
        "Total Revenue":[130,122,116,110,105,102,100,98],
        "Operating Income":[20,17,15,13,11,10,9,8],
        "Net Income":[14,12,11,9,8,7,6,5],
    })
    cash=frame({"Free Cash Flow":[15,13,12,10,8,7,6,5]})
    balance=frame({
        "Total Debt":[60,62,64,66,75,76,78,80],
        "Cash And Cash Equivalents":[20,19,18,17,15,14,13,12],
    })
    m=build_inflection_metrics(income,cash,quarterly_balance=balance)
    assert m["Skuld YoY senaste kvartal"] < 0
    assert m["Nettoskuld YoY senaste kvartal"] < 0
    assert m["Andel senaste kvartal med positiv omsättning YoY"] >= .75
    assert m["Andel senaste kvartal med positiv FCF"] == 1.0

def test_broad_operating_improvement_is_identified():
    metrics={
        "Omsättning YoY senaste kvartal":.20,
        "Omsättning acceleration":.08,
        "Marginal YoY förändring":.04,
        "FCF YoY senaste kvartal":.35,
        "Vinst YoY senaste kvartal":.30,
        "Nettoskuld YoY senaste kvartal":-.20,
        "Andel senaste kvartal med positiv omsättning YoY":1.0,
        "Andel senaste kvartal med positiv FCF":1.0,
        "EPS-estimat förändring":.03,
        "EPS-revisionsbalans":.5,
        "Senaste EPS-överraskning":.08,
    }
    result=assess_inflection(metrics)
    assert result["Operativ förändring"]=="Bred fundamental förbättring"
    assert result["Operativa förbättringar antal"] >= 3
    assert result["Inflection Signal"] in {"Positiv inflektion","Tidiga förbättringstecken"}

def test_broad_operating_deterioration_cannot_be_hidden_by_positive_estimates():
    metrics={
        "Omsättning YoY senaste kvartal":-.10,
        "Omsättning acceleration":-.10,
        "Marginal YoY förändring":-.04,
        "FCF YoY senaste kvartal":-.40,
        "Vinst YoY senaste kvartal":-.35,
        "Nettoskuld YoY senaste kvartal":.30,
        "Andel senaste kvartal med positiv omsättning YoY":.0,
        "Andel senaste kvartal med positiv FCF":.25,
        "EPS-estimat förändring":.06,
        "EPS-revisionsbalans":.6,
        "Senaste EPS-överraskning":.06,
    }
    result=assess_inflection(metrics)
    assert result["Operativ förändring"]=="Bred fundamental försämring"
    assert result["Inflection Signal"]=="Tydlig försämring"
    assert "motsatt håll" in result["Förändringskonflikt"]

def test_broad_deterioration_downgrades_deep_case():
    case={
        "Djupkontroll":"Klarar djupkontroll",
        "Inflection Signal":"Tydlig försämring",
        "Operativ förändring":"Bred fundamental försämring",
        "EPS-estimat förändring":.01,
    }
    result=apply_inflection_gate(case)
    assert result["Djupkontroll"]=="Kräver extra kontroll"
    assert "flera observerade delar" in result["Inflection Gate Note"]

def test_missing_balance_data_stays_missing():
    income=frame({"Total Revenue":[130,122,116,110,105,102,100,98]})
    m=build_inflection_metrics(income,pd.DataFrame())
    assert np.isnan(m["Skuld YoY senaste kvartal"])
    assert np.isnan(m["Nettoskuld YoY senaste kvartal"])
