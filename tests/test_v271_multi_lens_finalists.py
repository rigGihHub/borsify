import pandas as pd

from finalist_selection import select_deep_finalist_pool


def _row(ticker, invest, quality, valuation, reversal, risk=70, coverage=.9):
    return {
        "Ticker": ticker,
        "INVEST Score": invest,
        "Kvalitet": quality,
        "Värdering": valuation,
        "REVERSAL Score": reversal,
        "Risk": risk,
        "Datatäckning": coverage,
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


def test_multi_lens_keeps_top_invest_but_admits_turnaround_candidate():
    rows = [
        _row("A", 92, 72, 70, 20),
        _row("B", 90, 70, 68, 22),
        _row("C", 88, 69, 67, 25),
        _row("D", 86, 68, 66, 30),
        _row("E", 60, 71, 63, 92),
        _row("F", 58, 94, 62, 35),
        _row("G", 55, 60, 95, 40),
    ]
    df = pd.DataFrame(rows)
    pool = select_deep_finalist_pool(df, pool_size=6)
    tickers = set(pool["Ticker"])
    assert {"A", "B"}.issubset(tickers)
    assert "E" in tickers
    assert "F" in tickers
    assert "G" in tickers
    assert pool["Ticker"].is_unique
    assert "Djupurval" in pool.columns


def test_weak_alternative_lenses_do_not_displace_stronger_fallbacks():
    rows = [
        _row("A", 92, 80, 80, 30),
        _row("B", 90, 78, 78, 32),
        _row("C", 88, 60, 60, 40),
        _row("D", 86, 59, 59, 42),
    ]
    df = pd.DataFrame(rows)
    pool = select_deep_finalist_pool(df, pool_size=4)
    assert set(pool["Ticker"]) == {"A", "B", "C", "D"}
    assert len(pool) == 4


def test_selector_accepts_dataframe_where_search_horizon_scores_already_exist():
    df = pd.DataFrame([
        _row("A", 90, 80, 75, 30),
        _row("B", 88, 78, 73, 35),
        _row("C", 70, 76, 80, 75),
    ])
    from horizon_rankings import add_horizon_scores
    pre_scored = add_horizon_scores(df)
    pool = select_deep_finalist_pool(pre_scored, pool_size=3)
    assert len(pool) == 3
    assert pool["Ticker"].is_unique
