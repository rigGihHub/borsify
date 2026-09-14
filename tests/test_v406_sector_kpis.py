import pandas as pd, numpy as np
from sector_kpi_engine import extract_sector_kpis

def frame(rows):
    return pd.DataFrame(rows,index=["Total Revenue","Gross Profit","Operating Income"] if len(rows)==3 else None,
                        columns=[pd.Timestamp("2026-06-30"),pd.Timestamp("2026-03-31")])

def test_software_extracts_observable_margin_but_keeps_nrr_gap():
    qi=pd.DataFrame([[120,100],[84,65],[24,15]],index=["Total Revenue","Gross Profit","Operating Income"],
                    columns=[pd.Timestamp("2026-06-30"),pd.Timestamp("2026-03-31")])
    qc=pd.DataFrame([[20,10]],index=["Free Cash Flow"],columns=qi.columns)
    r=extract_sector_kpis("Technology","Software",qi,qc,pd.DataFrame())
    assert abs(r["KPI Bruttomarginal"]-.70)<1e-9
    assert "NRR/churn" in r["KPI-specifika saknas"]
    assert "bruttomarginal" in r["KPI-specifika observerade"]

def test_retail_inventory_growth_is_observed_not_inferred():
    cols=[pd.Timestamp("2026-06-30"),pd.Timestamp("2026-03-31")]
    qb=pd.DataFrame([[120,100]],index=["Inventory"],columns=cols)
    r=extract_sector_kpis("Consumer Cyclical","Retail",pd.DataFrame(),pd.DataFrame(),qb)
    assert abs(r["KPI Lager QoQ"]-.20)<1e-9
    assert "lagerutveckling" in r["KPI-specifika observerade"]
    assert "like-for-like" in r["KPI-specifika saknas"]

def test_bank_does_not_fake_cet1_from_generic_balance_sheet():
    r=extract_sector_kpis("Financial Services","Banks",pd.DataFrame(),pd.DataFrame(),pd.DataFrame())
    assert "CET1" in r["KPI-specifika saknas"]
    assert r["KPI strukturerad täckning"]==0

def test_app_wires_sector_kpis_and_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.35.0"' in app
    assert "extract_sector_kpis(" in app
