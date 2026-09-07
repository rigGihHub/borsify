import pandas as pd

from sector_valuation import profile_for_sector, sector_aware_valuation


def _frame():
    return pd.DataFrame([
        {"Sektor":"Financial Services","P/E":12,"Forward P/E":10,"P/B":1.0,"EV/EBITDA":30,"FCF-yield":-0.20},
        {"Sektor":"Financial Services","P/E":15,"Forward P/E":13,"P/B":1.5,"EV/EBITDA":5,"FCF-yield":0.30},
        {"Sektor":"Financial Services","P/E":18,"Forward P/E":16,"P/B":2.0,"EV/EBITDA":10,"FCF-yield":0.10},
        {"Sektor":"Technology","P/E":25,"Forward P/E":20,"P/B":20,"EV/EBITDA":18,"FCF-yield":0.06},
        {"Sektor":"Technology","P/E":30,"Forward P/E":25,"P/B":3,"EV/EBITDA":22,"FCF-yield":0.04},
        {"Sektor":"Technology","P/E":40,"Forward P/E":30,"P/B":2,"EV/EBITDA":28,"FCF-yield":0.02},
    ])


def test_financials_use_financial_profile_and_ignore_fcf_as_primary_metric():
    assert profile_for_sector("Financial Services").name == "Bank/finans"
    a = sector_aware_valuation(_frame())
    assert a.iloc[0]["Värderingsprofil"] == "Bank/finans"
    assert a.iloc[0]["Värderingsmått antal"] == 3
    # Cheapest bank on P/B and earnings should rank best even though its FCF field is ugly.
    assert a.iloc[0]["Värdering"] > a.iloc[1]["Värdering"] > a.iloc[2]["Värdering"]


def test_growth_profile_does_not_use_price_to_book():
    assert profile_for_sector("Technology").name == "Tillväxt/tillgångslätt"
    a = sector_aware_valuation(_frame())
    assert a.iloc[3]["Värderingsmått antal"] == 4
    # A high P/B alone must not sink an otherwise cheaper growth-company valuation.
    assert a.iloc[3]["Värdering"] > a.iloc[5]["Värdering"]


def test_missing_metrics_reduce_coverage_instead_of_becoming_neutral_scores():
    df = pd.DataFrame([
        {"Sektor":"Industrials","P/E":10,"Forward P/E":None,"P/B":None,"EV/EBITDA":None,"FCF-yield":None},
        {"Sektor":"Industrials","P/E":20,"Forward P/E":None,"P/B":None,"EV/EBITDA":None,"FCF-yield":None},
    ])
    out = sector_aware_valuation(df)
    assert out.iloc[0]["Värderingsmått antal"] == 1
    assert out.iloc[0]["Värderingsunderlag"] == "Begränsat underlag"
    assert out.iloc[0]["Värdering täckning"] < 0.3
    assert out.iloc[0]["Värdering"] > out.iloc[1]["Värdering"]


def test_real_estate_is_explicitly_cautious_without_ffo_nav():
    p = profile_for_sector("Real Estate")
    assert p.name == "Fastigheter"
    assert "P/FFO" in p.note
