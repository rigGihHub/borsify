from pathlib import Path
from market_universe import load_avanza_universe, universe_symbols, coverage_table, breadth_summary

ROOT=Path(__file__).resolve().parents[1]

def test_catalog_is_large_and_multimarket():
    df=load_avanza_universe(ROOT/"avanza_universe.csv")
    s=breadth_summary(df)
    assert s["countries"]==15
    assert s["total"]>=500
    assert s["extended"]>0

def test_core_mode_is_subset_of_broad():
    df=load_avanza_universe(ROOT/"avanza_universe.csv")
    core=set(universe_symbols(df,["USA"],broad=False))
    broad=set(universe_symbols(df,["USA"],broad=True))
    assert core
    assert core < broad

def test_country_filter_works():
    df=load_avanza_universe(ROOT/"avanza_universe.csv")
    syms=universe_symbols(df,["Schweiz"],broad=True)
    assert syms
    assert all(s.endswith(".SW") for s in syms)

def test_coverage_table_counts_catalog():
    df=load_avanza_universe(ROOT/"avanza_universe.csv")
    table=coverage_table(df)
    assert table["Totalt"].sum()==len(df)
