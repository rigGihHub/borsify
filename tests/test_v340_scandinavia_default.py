from pathlib import Path

import pandas as pd

from market_universe import load_avanza_universe, universe_symbols


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def test_release_version_and_scandinavia_is_default_market():
    assert 'APP_VERSION = "3.81.0"' in APP
    assert '"Sverige + Norge + Danmark"' in APP
    assert 'index=list(MARKET_CONFIGS).index("Sverige + Norge + Danmark")' in APP
    # Country expansion must remain directly available in the left sidebar.
    assert '"Var ska Borsify leta?"' in APP


def test_broad_universe_is_default_for_multi_country_searches():
    assert '["Brett universum", "Snabbt kärnurval"]' in APP
    assert 'broad=(universe == "Brett universum")' in APP


def test_default_scandinavian_search_uses_entire_catalog_for_those_countries():
    catalog = load_avanza_universe(ROOT / "avanza_universe.csv")
    symbols = universe_symbols(catalog, ["Sverige", "Norge", "Danmark"], broad=True)
    expected = catalog[catalog["Land"].isin(["Sverige", "Norge", "Danmark"])]["Ticker"].nunique()
    assert len(symbols) == expected
    assert expected == 229


def test_global_expansion_can_reach_full_catalog():
    catalog = load_avanza_universe(ROOT / "avanza_universe.csv")
    symbols = universe_symbols(catalog, catalog["Land"].drop_duplicates().tolist(), broad=True)
    assert len(symbols) == len(catalog) == 876
