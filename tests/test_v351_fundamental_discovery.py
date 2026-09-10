import pandas as pd

from fundamental_discovery import fundamental_discovery_labels, select_fundamental_candidates
from discovery_engine import build_discovery_pool, discovery_coverage_summary


def _row(**kw):
    base = {
        "Ticker":"X.ST", "Borsify Score":50, "Omsättningstillväxt":.12,
        "Vinsttillväxt":.22, "Vinstmarginal":.12, "ROE":.18, "FCF-yield":.06,
        "Skuld/eget kapital":60, "Forward P/E":22,
        "Mellan Score":20, "Års Score":20, "Livstid Score":20,
        "Kvalitet":40, "Värdering":40, "REVERSAL Score":20,
    }
    base.update(kw)
    return base


def test_profitable_growth_and_cash_quality_are_transparent_rules():
    labels = fundamental_discovery_labels(pd.Series(_row()))
    assert "Lönsam tillväxt" in labels
    assert "Vinst växer snabbare än försäljning" in labels
    assert "Kassaflöde + kvalitet" in labels
    assert "Tillväxt till rimligt pris" in labels


def test_missing_fundamental_data_never_qualifies():
    row = _row(**{"ROE": None, "Vinstmarginal": None, "FCF-yield": None, "Vinsttillväxt": None})
    assert fundamental_discovery_labels(pd.Series(row)) == []


def test_fundamental_candidate_can_enter_despite_low_incumbent_lens_scores():
    rows=[]
    for i in range(20):
        r=_row(Ticker=f"N{i}.ST", **{"Borsify Score":90-i, "Omsättningstillväxt":0, "Vinsttillväxt":0, "Vinstmarginal":.03, "ROE":.05, "FCF-yield":.01, "Forward P/E":40,
             "Mellan Score":80-i/10, "Års Score":80-i/10, "Livstid Score":80-i/10, "Kvalitet":80-i/10, "Värdering":80-i/10, "REVERSAL Score":80-i/10})
        rows.append(r)
    special=_row(Ticker="SPECIAL.ST", **{"Borsify Score":10})
    df=pd.DataFrame(rows+[special])
    picked=select_fundamental_candidates(df, quota_per_lens=2, max_candidates=6)
    assert any(df.loc[idx,"Ticker"]=="SPECIAL.ST" for idx,_ in picked)
    pool=build_discovery_pool(df, max_candidates=10)
    assert "SPECIAL.ST" in set(pool["Ticker"])
    assert "Lönsam tillväxt" in pool.loc[pool["Ticker"].eq("SPECIAL.ST"),"Upptäcktslinser"].iloc[0]


def test_no_new_fundamental_score_is_created_and_summary_is_auditable():
    df=pd.DataFrame([_row(Ticker="A.ST"), _row(Ticker="B.ST", **{"Omsättningstillväxt":0, "Vinsttillväxt":0})])
    pool=build_discovery_pool(df, max_candidates=2)
    assert not any("Fundamental Score" in c for c in pool.columns)
    summary=discovery_coverage_summary(df,pool)
    assert "Lönsam tillväxt" in summary["lens_counts"]
