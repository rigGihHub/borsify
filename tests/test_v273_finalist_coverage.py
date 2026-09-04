import pandas as pd

from finalist_coverage import (
    aggregate_finalist_coverage,
    evaluate_finalist_pool_coverage,
    finalist_pool_recommendation,
)


def _row(ticker, invest, quality=60, valuation=60, reversal=20):
    return {
        "Ticker": ticker,
        "INVEST Score": invest,
        "Kvalitet": quality,
        "Värdering": valuation,
        "REVERSAL Score": reversal,
        "Risk": 70,
        "Datatäckning": .9,
        "ROE": .15,
        "Vinstmarginal": .12,
        "Omsättningstillväxt": .08,
        "Dagsförändring": 0.0,
        "1 mån": 0.0,
        "3 mån": 0.0,
        "6 mån": 0.0,
        "Volymkvot": 1.0,
        "RSI14": 50,
        "Avstånd SMA200": 0.0,
    }


def test_coverage_compares_nested_pool_sizes_to_one_deep_reference():
    shallow = pd.DataFrame([
        _row("A", 95, 80, 75, 20),
        _row("B", 93, 78, 72, 20),
        _row("C", 88, 60, 60, 20),
        _row("D", 84, 60, 60, 20),
        _row("E", 60, 95, 60, 20),
        _row("F", 58, 60, 95, 20),
        _row("G", 55, 60, 60, 95),
        _row("H", 52, 60, 60, 20),
        _row("I", 50, 60, 60, 20),
        _row("J", 48, 60, 60, 20),
    ])
    # Imagine one 10-name deep run later found these to be strongest.
    deep_reference = pd.DataFrame({"Ticker": ["A", "E", "G", "F", "C", "B", "D", "H", "I", "J"]})
    out = evaluate_finalist_pool_coverage(shallow, deep_reference, pool_sizes=(4, 6, 8, 10), target_limit=5)
    assert out["pool_size"].tolist() == [4, 6, 8, 10]
    assert out.loc[out["pool_size"] == 10, "target_coverage"].iloc[0] == 1.0
    assert out.loc[out["pool_size"] == 4, "target_coverage"].iloc[0] <= out.loc[out["pool_size"] == 6, "target_coverage"].iloc[0]
    assert out.loc[out["pool_size"] == 8, "extra_deep_calls_vs_6"].iloc[0] == 2
    assert out.loc[out["pool_size"] == 10, "extra_deep_calls_vs_6"].iloc[0] == 4


def test_coverage_evaluation_does_not_need_network_or_deep_fetcher():
    shallow = pd.DataFrame([_row("A", 90), _row("B", 80), _row("C", 70)])
    deep_reference = pd.DataFrame({"Ticker": ["B", "A", "C"]})
    out = evaluate_finalist_pool_coverage(shallow, deep_reference, pool_sizes=(2, 3), target_limit=2)
    assert set(out.columns) >= {"target_coverage", "missed_targets", "extra_deep_calls_vs_6"}
    assert out.loc[out["pool_size"] == 3, "target_coverage"].iloc[0] == 1.0


def test_aggregate_requires_multiple_strong_runs_before_recommendation():
    rows = []
    for run in range(5):
        rows.extend([
            {"run_id": run, "pool_size": 6, "target_coverage": .80, "extra_deep_calls_vs_6": 0},
            {"run_id": run, "pool_size": 8, "target_coverage": 1.00, "extra_deep_calls_vs_6": 2},
            {"run_id": run, "pool_size": 10, "target_coverage": 1.00, "extra_deep_calls_vs_6": 4},
        ])
    aggregate = aggregate_finalist_coverage(pd.DataFrame(rows))
    six = aggregate.loc[aggregate["pool_size"] == 6].iloc[0]
    eight = aggregate.loc[aggregate["pool_size"] == 8].iloc[0]
    assert not bool(six["passes_retention_gate"])
    assert bool(eight["passes_retention_gate"])
    rec = finalist_pool_recommendation(aggregate, current_pool_size=6)
    assert rec["recommended_pool_size"] == 8
    assert rec["status"] == "consider_larger"


def test_one_good_run_never_changes_pool_size():
    aggregate = aggregate_finalist_coverage(pd.DataFrame([
        {"pool_size": 8, "target_coverage": 1.0, "extra_deep_calls_vs_6": 2},
    ]))
    rec = finalist_pool_recommendation(aggregate, current_pool_size=6)
    assert rec["recommended_pool_size"] == 6
    assert rec["status"] in {"keep_current", "collect_more_runs"}
