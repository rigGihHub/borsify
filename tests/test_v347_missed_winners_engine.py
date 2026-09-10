import pandas as pd

from missed_winners_engine import build_universe_snapshot, evaluate_snapshot_cohort, missed_winner_summary


def sample_frame(n=25):
    return pd.DataFrame({
        "Ticker": [f"S{i:02d}.ST" for i in range(n)],
        "Namn": [f"Bolag {i}" for i in range(n)],
        "Pris": [100.0] * n,
        "Borsify Score": [50 + i / 2 for i in range(n)],
        "Mellan Score": [45 + i for i in range(n)],
        "Års Score": [40 + i for i in range(n)],
        "Livstid Score": [55 + i / 3 for i in range(n)],
        "Värdering": [55.0] * n,
        "Kvalitet": [60.0] * n,
        "Marknadsläge": [58.0] * n,
        "Risk": [62.0] * n,
        "Datatäckning": [0.9] * n,
    })


def test_snapshot_freezes_broad_universe_and_recommendations():
    frame = sample_frame(25)
    snap = build_universe_snapshot(
        frame, "Balanserad", "Sverige + Norge + Danmark", "2026-09-08",
        {"medium": {"S24.ST"}, "year": {"S23.ST"}, "lifetime": {"S22.ST"}},
    )
    assert len(snap) == 25
    assert int(snap.loc[snap.symbol.eq("S24.ST"), "recommended_medium"].iloc[0]) == 1
    assert int(snap.loc[snap.symbol.eq("S00.ST"), "recommended_medium"].iloc[0]) == 0
    assert "quality" in snap.columns and "coverage" in snap.columns


def test_missed_winner_requires_top_decile_and_return_hurdle():
    frame = sample_frame(25)
    snap = build_universe_snapshot(frame, "Balanserad", "Nordics", "2026-06-01", {"medium": {"S24.ST"}})
    snap["snapshot_id"] = snap["captured_date"] + "::" + snap["profile"] + "::" + snap["symbol"]
    current = pd.DataFrame({"Ticker": snap.symbol, "Pris": [100 + i for i in range(25)]})
    result = evaluate_snapshot_cohort(snap, current, "1m", "2026-07-01")
    assert not result.empty
    # S24 is the strongest return but was recommended, so it is not a miss.
    s24 = result[result.symbol.eq("S24.ST")].iloc[0]
    assert s24.was_recommended == 1
    assert s24.missed_winner == 0
    # S23 is also in the top decile and exceeds +10%, but was not recommended.
    s23 = result[result.symbol.eq("S23.ST")].iloc[0]
    assert s23.missed_winner == 1


def test_small_cohort_is_not_overinterpreted():
    frame = sample_frame(10)
    snap = build_universe_snapshot(frame, "Balanserad", "Nordics", "2026-06-01")
    snap["snapshot_id"] = snap["captured_date"] + "::" + snap["profile"] + "::" + snap["symbol"]
    current = pd.DataFrame({"Ticker": snap.symbol, "Pris": [120.0] * len(snap)})
    result = evaluate_snapshot_cohort(snap, current, "1m", "2026-07-01")
    assert result.empty


def test_missing_historical_recommendation_is_not_reconstructed():
    frame = sample_frame(25)
    snap = build_universe_snapshot(frame, "Balanserad", "Nordics", "2026-06-01", {"medium": set()})
    snap["snapshot_id"] = snap["captured_date"] + "::" + snap["profile"] + "::" + snap["symbol"]
    current = pd.DataFrame({"Ticker": snap.symbol, "Pris": [100.0] * 24 + [130.0]})
    result = evaluate_snapshot_cohort(snap, current, "1m", "2026-07-01")
    winner = result[result.symbol.eq("S24.ST")].iloc[0]
    assert winner.was_recommended == 0
    assert winner.missed_winner == 1


def test_summary_is_descriptive_not_a_new_score():
    outcomes = pd.DataFrame({"horizon": ["1m", "1m"], "missed_winner": [1, 0]})
    summary = missed_winner_summary(outcomes, "1m")
    assert summary["misses"] == 1
    assert summary["evaluated"] == 2
    assert "ändrar inte score automatiskt" in summary["text"]
