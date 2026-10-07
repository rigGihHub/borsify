import pandas as pd
from lifetime_suitability import lifetime_blockers, filter_lifetime_suitable
from horizon_alternatives import rank_horizon_alternatives
from horizon_rankings import top_ranked
from purchase_consistency import purchase_blockers
from research_merge import merge_research


def durable(**changes):
    row = {"Ticker": "DURABLE.ST", "Bransch": "Software - Application",
           "Historik år": 4, "Historik omsättning år": 4, "Historik vinst år": 4, "Historik FCF år": 4,
           "Positiv FCF-andel": 1, "Positiv vinst-andel": 1, "Omsättning CAGR": .08,
           "Senaste FCF": 100, "Senaste vinst": 100, "Deep Confidence": 90,
           "Konkurrensfördel verifierad": True, "Konkurrensfördel källa": "https://example.com/annual-report",
           "Konkurrensfördel underlag": "Testunderlag: flerårig kundbehållning och kontraktsbundna återkommande intäkter.",
           "Konkurrensfördel datum": pd.Timestamp.now(tz="UTC").isoformat()}
    return {**row, **changes}


def test_current_profit_does_not_qualify_a_cyclical_company_for_lifetime():
    for ticker, industry in [("HAFNI.OL", "Marine Shipping"), ("OTHER.OL", "Marine Shipping"), ("FRO.OL", "Marine Shipping"), ("OIL.ST", "Oil & Gas E&P")]:
        row = durable(Ticker=ticker, Bransch=industry, **{"Borsify Score": 99, "Kvalitet": 99, "Risk": 99, "ROE": .5})
        assert "cykler" in lifetime_blockers(row)[0]
        assert rank_horizon_alternatives(pd.DataFrame([row]), "lifetime").empty
        assert top_ranked(pd.DataFrame([row]), "lifetime").empty
        assert any("cykler" in b for b in purchase_blockers(row, "lifetime"))
        assert not rank_horizon_alternatives(pd.DataFrame([row]), "medium").empty


def test_missing_history_or_competitive_evidence_is_not_backfilled_with_neutral_scores():
    assert not lifetime_blockers(durable())
    for field, value in [("Historik FCF år", 1), ("Positiv FCF-andel", .5), ("Konkurrensfördel verifierad", False),
                         ("Konkurrensfördel datum", "2020-01-01"), ("Konkurrensfördel källa", ""),
                         ("Senaste vinst", -1), ("Omsättning CAGR", float('nan'))]:
        assert lifetime_blockers(durable(**{field:value}))
    assert lifetime_blockers({"Ticker":"UNKNOWN", "Historik år": 4})


def test_research_merge_retains_separate_history_and_dated_competitive_evidence():
    source = pd.DataFrame([{"Ticker":"DURABLE.ST", "Borsify Score":80}])
    out = merge_research(source, pd.DataFrame([durable()]))
    assert out.iloc[0]["Historik FCF år"] == 4
    assert out.iloc[0]["Positiv vinst-andel"] == 1
    assert out.iloc[0]["Konkurrensfördel verifierad"]
    assert out.iloc[0]["Borsify Score"] == 80


def test_revenue_history_does_not_stand_in_for_missing_cashflow_years():
    from deep_case_engine import build_deep_metrics
    annual = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
    income = pd.DataFrame([[100, 90, 80, 70], [10, 9, 8, 7]], index=["Total Revenue", "Net Income"], columns=annual)
    cashflow = pd.DataFrame([[10]], index=["Free Cash Flow"], columns=annual[:1])
    result = build_deep_metrics(income, cashflow, pd.DataFrame())
    assert result["Historik omsättning år"] == 4
    assert result["Historik FCF år"] == 1
    assert lifetime_blockers(durable(**result))
