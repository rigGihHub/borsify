import json
import pandas as pd

from finalist_selection import select_deep_finalist_pool
from recommendation_ledger import build_recommendation_records, deep_selection_outcome_summary


def _row(ticker, invest, quality, valuation, reversal):
    return {
        "Ticker": ticker, "Namn": ticker, "Pris": 100.0, "Valuta": "SEK",
        "INVEST Score": invest, "Kvalitet": quality, "Värdering": valuation,
        "REVERSAL Score": reversal, "Risk": 70, "Datatäckning": .9,
        "ROE": .15, "Vinstmarginal": .12, "Omsättningstillväxt": .08,
        "Dagsförändring": 0.0, "1 mån": 0.0, "3 mån": 0.0, "6 mån": 0.0,
        "Volymkvot": 1.0, "RSI14": 50, "Avstånd SMA200": 0.0,
    }


def test_selection_freezes_primary_path_and_all_strong_lenses():
    df = pd.DataFrame([
        _row("A", 92, 80, 80, 20),
        _row("B", 90, 70, 68, 22),
        _row("C", 60, 71, 63, 92),
        _row("D", 58, 94, 62, 35),
    ])
    pool = select_deep_finalist_pool(df, pool_size=4)
    assert {"Djupurval", "Djupurval Nyckel", "Djupurval Linser", "Djupurval Linser text"}.issubset(pool.columns)
    a = pool.loc[pool["Ticker"] == "A"].iloc[0]
    assert a["Djupurval Nyckel"] == "invest"
    assert "invest" in a["Djupurval Linser"]
    assert "quality" in a["Djupurval Linser"]
    c = pool.loc[pool["Ticker"] == "C"].iloc[0]
    assert "reversal" in c["Djupurval Linser"]


def test_long_recommendation_snapshot_persists_selection_audit_metadata():
    df = pd.DataFrame([_row("A", 92, 80, 80, 20)])
    pool = select_deep_finalist_pool(df, pool_size=1)
    records = build_recommendation_records(pool, "long", "2.72.0", "Balanserad", "Sverige")
    assert len(records) == 1
    snap = json.loads(records[0]["snapshot_json"])
    assert snap["Djupurval Nyckel"] == "invest"
    assert "Djupurval Linser" in snap


def test_outcome_summary_groups_by_frozen_selection_path():
    recs = pd.DataFrame([
        {"record_id": "1", "snapshot_json": json.dumps({"Djupurval Nyckel": "invest"})},
        {"record_id": "2", "snapshot_json": json.dumps({"Djupurval Nyckel": "reversal"})},
        {"record_id": "3", "snapshot_json": json.dumps({"Djupurval Nyckel": "invest"})},
    ])
    outs = pd.DataFrame([
        {"record_id": "1", "horizon": "1y", "return_pct": .20},
        {"record_id": "2", "horizon": "1y", "return_pct": -.10},
        {"record_id": "3", "horizon": "1y", "return_pct": .10},
    ])
    summary = deep_selection_outcome_summary(recs, outs, horizon="1y")
    invest = summary.loc[summary["selection_path"] == "invest"].iloc[0]
    assert invest["evaluated"] == 2
    assert abs(invest["positive_rate"] - 1.0) < 1e-9
    assert abs(invest["mean_return"] - .15) < 1e-9
