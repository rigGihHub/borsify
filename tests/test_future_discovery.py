from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from future_discovery import REPORTS, assess_future_candidate, collect_future_pool, select_future_companies, screen_growth


NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def case(ticker="NEW", **changes):
    row = {"Ticker": ticker, "Fundamental hämtad": NOW.isoformat(),
           "Omsättningstillväxt": .3, "Vinstmarginal": .1, "FCF-yield": .02,
           "Skuld/eget kapital": 40, "P/E": 30}
    row.update(changes)
    return assess_future_candidate(row, NOW)


def test_discovery_admits_large_foreign_loss_making_business_outside_broker_catalog():
    row = case("NEW", **{"Avanza-universum": False, "Börsvärde BSEK": 200,
                         "Vinstmarginal": -.2, "P/E": None})
    selected = select_future_companies(pd.DataFrame([row]))
    assert len(selected) == 1
    assert "Förlust" in selected.iloc[0]["Framtid hinder"]
    assert selected.iloc[0]["Framtid köpstatus"].startswith("BEVAKA")


def test_latest_decline_overrides_older_positive_report():
    row = case("ALAB", **{"Omsättningstillväxt": -.3})
    assert row["Framtid tillväxt"] == -.3
    assert not row["_future_growth_confirmed"]
    assert "inte positiv" in row["Framtid hinder"]


def test_old_vendor_data_does_not_override_fresh_primary_report():
    row = case("ALAB", **{"Fundamental hämtad": "2026-09-01", "Omsättningstillväxt": 9})
    assert row["Framtid tillväxt"] == REPORTS["ALAB"]["growth"]
    assert "2026-08-04" in row["Framtid tillväxtkälla"]
    assert "Lönsamhet saknas" in row["Framtid hinder"]


@pytest.mark.parametrize("date", ["2026-01-01", "2027-01-01", "bad", None])
def test_stale_future_or_invalid_fetch_dates_do_not_confirm_growth(date):
    row = case(**{"Fundamental hämtad": date})
    assert row["Framtid tillväxt"] is None
    assert not row["_future_growth_confirmed"]


def test_old_research_stays_visible_but_does_not_support_current_growth():
    row = assess_future_candidate({"Ticker": "ALAB"}, datetime(2027, 8, 1, tzinfo=timezone.utc))
    assert row["Framtid tillväxt"] is None
    assert "120 dagar" in row["Framtid hinder"]
    assert "2026-08-04" == row["Framtid rapportdatum"]


def test_unknown_data_does_not_become_neutral_or_beat_confirmed_growth():
    rows = [case("KNOWN"), case("UNKNOWN", **{"Omsättningstillväxt": None})]
    selected = select_future_companies(pd.DataFrame(rows))
    assert selected.iloc[0]["Ticker"] == "KNOWN"
    assert "inte verifierad" in selected.iloc[1]["Framtid hinder"]


def test_failed_vendor_payload_is_not_trusted():
    row = case(**{"Fundamental source status": "ERROR"})
    assert row["Framtid tillväxt"] is None


def test_cash_generation_beats_higher_growth_with_losses():
    rows = [case("BURN", **{"Omsättningstillväxt": 5, "Vinstmarginal": -.3, "FCF-yield": -.1}), case("CASH")]
    assert select_future_companies(pd.DataFrame(rows)).iloc[0]["Ticker"] == "CASH"


def test_ranking_is_deterministic_deduplicated_and_has_no_second_score():
    rows = [case(f"T{i}") for i in range(8)] + [case(" t0 ")]
    selected = select_future_companies(pd.DataFrame(rows[::-1]))
    assert selected.Ticker.tolist() == ["T0", "T1", "T2", "T3", "T4"]
    assert not any("score" in col.lower() for col in selected.columns)
    assert len(select_future_companies(pd.DataFrame(rows), limit=0)) == 0


def test_collection_finds_new_symbols_and_keeps_company_identity_on_bad_payload():
    def screen(regions):
        return [{"symbol": "NEW", "shortName": "New business"}, {"symbol": "NEW"},
                {"symbol": "../BAD"}, {"symbol": "FUND", "quoteType": "ETF"}]
    def fetch(ticker):
        return {"Ticker": "WRONG", "Omsättningstillväxt": .4, "Fundamental hämtad": NOW.isoformat()}
    frame, health = collect_future_pool(fetch, screen, NOW)
    assert set(frame.Ticker) == set(REPORTS) | {"NEW"}
    assert health["candidates"] == len(REPORTS) + 1
    assert frame.loc[frame.Ticker.eq("NEW"), "Framtid tillväxt"].iloc[0] == .4


def test_source_outage_uses_dated_research_and_shows_limitations():
    def unavailable(*args):
        raise TimeoutError()
    frame, health = collect_future_pool(unavailable, unavailable, NOW)
    selected = select_future_companies(frame)
    assert len(selected) == 5
    assert len(health["errors"]) == 2 + len(REPORTS)
    assert health["screen_hits"] == 0
    assert selected["Framtid köpstatus"].eq("BEVAKA · köpläge inte prövat").all()
    assert selected["Framtid hinder"].str.contains("Värderingsstöd saknas").all()


def test_collection_is_bounded_even_if_screen_returns_too_many_results():
    symbols = []
    def fetch(ticker):
        symbols.append(ticker)
        return {}
    frame, health = collect_future_pool(fetch, lambda regions: [{"symbol": f"T{i}"} for i in range(200)], NOW)
    assert len(symbols) == len(REPORTS) + 24
    assert len(frame) == health["candidates"]


def test_empty_pool_and_fewer_than_five_do_not_invent_companies():
    assert select_future_companies(pd.DataFrame()).empty
    assert len(select_future_companies(pd.DataFrame([case()]))) == 1


def test_screen_queries_two_regions_and_has_no_earnings_gate(monkeypatch):
    import yfinance as yf
    seen = []
    def screen(query, **kwargs):
        seen.append((query.to_dict(), kwargs))
        return {"quotes": [{"symbol": "NEW"}]}
    monkeypatch.setattr(yf, "screen", screen)
    assert screen_growth(("us", "ca")) == [{"symbol": "NEW"}]
    query, options = seen[0]
    assert "quarterlyrevenuegrowth" in str(query)
    assert "epsgrowth" not in str(query)
    assert options["size"] == 24
    assert options["sortField"] == "eodvolume"  # documented Yahoo equity-screen ordering
    assert "session" not in options  # never replace yfinance's process-wide session


def test_direct_route_precedes_market_scan_and_has_separate_refresh():
    app = (Path(__file__).parents[1] / "app.py").read_text()
    main = app[app.index("def main()") :]
    assert main.index("render_future_discovery()") < main.index("universe_df = load_universe_file()")
    assert "fetch_future_discovery.clear()" in app
    assert "🔬 Mikrobolag · högst 500 miljoner SEK" in app


def test_future_view_renders_five_attributed_cards_during_source_outage():
    import ast
    from streamlit.testing.v1 import AppTest

    source = (Path(__file__).parents[1] / "app.py").read_text()
    tree = ast.parse(source)
    render = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_future_discovery")
    code = """import streamlit as st
import pandas as pd
from urllib.parse import quote
from datetime import datetime, timezone
from future_discovery import collect_future_pool, select_future_companies
@st.cache_data(show_spinner=False)
def fetch_future_discovery():
    def unavailable(*args):
        raise TimeoutError()
    return collect_future_pool(unavailable, unavailable, datetime(2026, 10, 15, tzinfo=timezone.utc))
""" + ast.get_source_segment(source, render) + "\nrender_future_discovery()\n"
    app = AppTest.from_string(code).run(timeout=10)
    assert not app.exception
    cards = [item.value for item in app.markdown if item.value.startswith("### ")]
    assert len(cards) == 5
    assert any("Att granska:" in item.value for item in app.warning)
    assert any("Bolagets rapport, publicerad" in item.value for item in app.markdown)
    app.button[0].click().run(timeout=10)
    assert not app.exception
