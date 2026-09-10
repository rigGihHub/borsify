import pandas as pd

from discovery_engine import build_discovery_pool, discovery_coverage_summary


def _frame():
    rows=[]
    for i in range(12):
        rows.append({
            "Ticker": f"S{i:02d}.ST",
            "Land": "Sverige" if i < 6 else "Norge",
            "Borsify Score": 90-i,
            "Datatäckning": .90,
            "Mellan Score": 50+i,
            "Års Score": 62+(i%4),
            "Livstid Score": 55+i*2,
            "Kvalitet": 50+i*3,
            "Värdering": 80-i*2,
            "REVERSAL Score": 40+i*2,
        })
    return pd.DataFrame(rows)


def test_discovery_pool_represents_multiple_existing_lenses_without_new_score():
    df=_frame()
    out=build_discovery_pool(df,max_candidates=8)
    assert 0 < len(out) <= 8
    assert "Upptäcktslinser" in out.columns
    assert "Discovery Score" not in out.columns
    joined=" | ".join(out["Upptäcktslinser"].astype(str))
    assert "Köp nu" in joined
    assert "Livstid" in joined
    assert "Värdering" in joined


def test_discovery_pool_is_deterministic():
    df=_frame()
    a=build_discovery_pool(df,max_candidates=9)["Ticker"].tolist()
    b=build_discovery_pool(df.sample(frac=1,random_state=4),max_candidates=9)["Ticker"].tolist()
    assert a == b


def test_discovery_pool_can_surface_non_top_borsify_name_via_specialist_lens():
    df=_frame()
    # Make the lowest Borsify name uniquely strong for lifetime quality.
    idx=df.index[-1]
    df.loc[idx,"Borsify Score"]=10
    df.loc[idx,"Livstid Score"]=99
    df.loc[idx,"Kvalitet"]=99
    out=build_discovery_pool(df,max_candidates=6)
    assert df.loc[idx,"Ticker"] in set(out["Ticker"])


def test_discovery_coverage_summary_is_audit_only():
    df=_frame()
    pool=build_discovery_pool(df,max_candidates=7)
    summary=discovery_coverage_summary(df,pool)
    assert summary["universe"] == 12
    assert summary["pool"] == 7
    assert summary["countries"] >= 1
    assert isinstance(summary["lens_counts"],dict)
    assert 0 < summary["fraction"] <= 1
