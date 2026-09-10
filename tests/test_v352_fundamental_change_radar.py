import pandas as pd

from fundamental_change_radar import add_fundamental_change_radar, select_change_radar_candidates
from discovery_engine import build_discovery_pool


def _current():
    return pd.DataFrame([
        {"Ticker":"AAA.ST","Namn":"A","Omsättningstillväxt":.12,"Vinsttillväxt":.24,"Vinstmarginal":.14,"ROE":.18,"Kvalitet":70,"Risk":70,"Borsify Score":50,"Datatäckning":.9,"Värdering":50,"Marknadsläge":50,"REVERSAL Score":40},
        {"Ticker":"BBB.ST","Namn":"B","Omsättningstillväxt":.04,"Vinsttillväxt":.05,"Vinstmarginal":.08,"ROE":.12,"Kvalitet":60,"Risk":60,"Borsify Score":90,"Datatäckning":.9,"Värdering":80,"Marknadsläge":80,"REVERSAL Score":70},
    ])


def test_detects_material_change_from_older_frozen_snapshot_only():
    hist = pd.DataFrame([
        {"symbol":"AAA.ST","captured_date":"2026-09-01","revenue_growth":.03,"earnings_growth":.08,"profit_margin":.10,"roe":.14},
        # Same-day row must never become its own reference.
        {"symbol":"AAA.ST","captured_date":"2026-09-08","revenue_growth":.12,"earnings_growth":.24,"profit_margin":.14,"roe":.18},
    ])
    out = add_fundamental_change_radar(_current(), hist, "2026-09-08")
    row = out[out.Ticker.eq("AAA.ST")].iloc[0]
    assert row["Fundamental förändring antal"] >= 2
    assert row["Fundamental jämförelsedatum"] == "2026-09-01"
    assert "Vinst accelererar" in row["Fundamental förändring detalj"]


def test_missing_old_fields_are_not_backfilled_or_inferred():
    hist = pd.DataFrame([{"symbol":"AAA.ST","captured_date":"2026-09-01"}])
    out = add_fundamental_change_radar(_current(), hist, "2026-09-08")
    row = out[out.Ticker.eq("AAA.ST")].iloc[0]
    assert row["Fundamental förändring antal"] == 0
    assert row["Fundamental förändring"] == "Ingen tydlig ny förbättring"


def test_radar_can_reserve_discovery_doorway_without_new_score():
    hist = pd.DataFrame([{"symbol":"AAA.ST","captured_date":"2026-09-01","revenue_growth":.03,"earnings_growth":.08,"profit_margin":.10,"roe":.14}])
    annotated = add_fundamental_change_radar(_current(), hist, "2026-09-08")
    selected = select_change_radar_candidates(annotated, quota=1)
    assert selected and selected[0][0] == annotated.index[0]
    pool = build_discovery_pool(annotated, max_candidates=2)
    assert "Fundamental förändring" in pool.loc[annotated.index[0], "Upptäcktslinser"]
    assert "Fundamental Change Score" not in pool.columns


def test_no_history_means_no_positive_change_signal():
    out = add_fundamental_change_radar(_current(), pd.DataFrame(), "2026-09-08")
    assert (out["Fundamental förändring antal"] == 0).all()
    assert set(out["Fundamental förändring"]) == {"Ingen jämförbar historik"}
