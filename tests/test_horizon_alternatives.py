import ast
import math
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from research_merge import merge_research
from horizon_alternatives import rank_horizon_alternatives
from horizon_rankings import add_horizon_scores, top_ranked


def case(ticker="CASE.ST", score=75, **extra):
    return {
        "Ticker": ticker, "Namn": ticker, "Borsify Score": score,
        "INVEST Score": 75, "Kvalitet": 80, "Risk": 75, "Värdering": 72,
        "ROE": .18, "Vinstmarginal": .15, "Omsättningstillväxt": .08,
        "1 mån": .03, "3 mån": .07, "6 mån": .10, "Dagsförändring": .01,
        "Volymkvot": 1.2, "RSI14": 60, "Avstånd SMA200": .07,
        "Datatäckning": .9, "Pris": 100, "Omsättning MSEK/dag": 10,
        "Skuld/eget kapital": .4, **extra,
    }


@pytest.mark.parametrize("horizon", ["medium", "year", "lifetime"])
def test_empty_purchase_list_still_has_ranked_observational_alternatives(horizon):
    source = pd.DataFrame([case(f"C{i}.ST", 50 + i) for i in range(5)])
    original = source.copy(deep=True)
    before = top_ranked(source, horizon, limit=10)
    assert before.empty
    out = rank_horizon_alternatives(source, horizon)
    assert out["Ticker"].tolist() == ["C4.ST", "C3.ST", "C2.ST"]
    assert set(out["Signal"]) <= {"BEVAKA", "AVVAKTA"}
    assert out["Alternativ köpstopp"].str.contains("slutbetyget når inte köpkravet").all()
    pd.testing.assert_frame_equal(source, original)
    pd.testing.assert_frame_equal(top_ranked(source, horizon, limit=10), before)


def test_specialist_final_score_controls_alternative_order_and_is_not_replaced_by_horizon_score():
    source = pd.DataFrame([
        case("CAPPED.ST", 92, Investmentbolag=True, **{"Investmentbolag rankningstak": 60}),
        case("BETTER.ST", 70),
    ])
    out = rank_horizon_alternatives(source, "year")
    assert out["Ticker"].tolist() == ["BETTER.ST", "CAPPED.ST"]
    assert out["Borsify slutbetyg"].tolist() == [70, 60]
    assert out["Borsify Score"].tolist() == [70, 60]


def test_price_rush_is_visible_and_never_relabelled_as_buy():
    out = rank_horizon_alternatives(pd.DataFrame([case(**{"1 mån": .35})]), "year")
    assert out.iloc[0]["Signal"] == "AVVAKTA"
    assert "25 %" in out.iloc[0]["Alternativ köpstopp"]


def test_missing_fundamentals_and_severe_risks_are_explained_instead_of_hidden():
    source = pd.DataFrame([{
        "Ticker": "WEAK.ST", "Borsify Score": 80,
        "Datatäckning": .2, "Riskflaggor": "hög skuldsättning",
    }])
    out = rank_horizon_alternatives(source, "lifetime")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["Signal"] == "BEVAKA"
    assert "för lite relevant data" in row["Alternativ köpstopp"]
    assert "allvarlig riskflagga" in row["Alternativ köpstopp"]
    assert "för osäkert" in row["Alternativ varför"]
    assert "hög bolagskvalitet" not in row["Alternativ varför"]


@pytest.mark.parametrize("source", [None, pd.DataFrame(), pd.DataFrame([{"Ticker": "UNKNOWN.ST"}])])
def test_no_alternative_is_fabricated_when_scores_are_missing(source):
    assert rank_horizon_alternatives(source, "year").empty


def test_existing_horizon_columns_and_duplicate_tickers_do_not_crash_or_duplicate_cards():
    source = add_horizon_scores(pd.DataFrame([case("A.ST"), case("A.ST"), case("B.ST", 72)]))
    out = rank_horizon_alternatives(source, "year")
    assert out["Ticker"].tolist() == ["A.ST", "B.ST"]
    assert rank_horizon_alternatives(source, "year", limit=1)["Ticker"].tolist() == ["A.ST"]
    assert rank_horizon_alternatives(source, "year", limit=0).empty


@pytest.fixture
def section():
    # Execute the actual selection/fallback boundary in the nested Streamlit
    # section. Stop before history writes and visual purchase-card rendering.
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_horizon_section")
    boundary = next(i for i, n in enumerate(node.body) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "history_profile" for t in n.targets))
    node.body = node.body[:boundary] + [ast.Return(value=ast.Name(id="ranked", ctx=ast.Load()))]
    tree = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    calls = []
    source = pd.DataFrame([case()])
    namespace = {
        "pd": pd, "filtered": source, "merge_research": merge_research, "deep_longlist": pd.DataFrame(), "short_longlist": pd.DataFrame(),
        "st": SimpleNamespace(markdown=lambda *_a: None, caption=lambda *_a: None),
        "top_ranked": lambda *_a, **_k: pd.DataFrame(),
        "add_full_deal_evidence": lambda frame, _h: frame.copy(),
        "render_horizon_alternatives": lambda frame, horizon: calls.append((frame, horizon)),
    }
    exec(compile(tree, "app.py", "exec"), namespace)
    return namespace["_horizon_section"], namespace, calls, source


@pytest.mark.parametrize("horizon", ["medium", "year", "lifetime"])
def test_initial_empty_selection_shows_alternatives_but_returns_no_purchase_for_history(section, horizon):
    function, _, calls, source = section
    result = function("title", "subtitle", horizon, "score")
    assert result.empty
    assert len(calls) == 1 and calls[0][0].equals(source) and calls[0][1] == horizon


@pytest.mark.parametrize("horizon,signal", [
    ("medium", "BEVAKA"), ("year", "BEVAKA"), ("lifetime", "BEVAKA PRISET"),
    ("medium", "AVVAKTA"), ("year", "AVVAKTA INGÅNG"),
])
def test_final_action_downgrade_shows_alternatives_and_returns_empty_buy_list(section, horizon, signal):
    function, namespace, calls, _ = section
    namespace["top_ranked"] = lambda *_a, **_k: pd.DataFrame([{"Signal": signal, "Ingångsläge nivå": "green"}])
    result = function("title", "subtitle", horizon, "score")
    assert result.empty
    assert len(calls) == 1


@pytest.mark.parametrize("signal", ["KÖP / ÄG LÅNGSIKTIGT", "BYGG LÅNGSIKTIGT"])
def test_valid_lifetime_purchase_actions_are_not_suppressed(section, signal):
    function, namespace, calls, _ = section
    namespace["top_ranked"] = lambda *_a, **_k: pd.DataFrame([{"Signal": signal, "Ingångsläge nivå": "green"}])
    result = function("title", "subtitle", "lifetime", "score")
    assert result["Signal"].tolist() == [signal]
    assert calls == []


def test_red_lifetime_entry_downgrades_valid_purchase_and_stays_out_of_buy_history(section):
    function, namespace, calls, _ = section
    namespace["top_ranked"] = lambda *_a, **_k: pd.DataFrame([{"Signal": "KÖP / ÄG LÅNGSIKTIGT", "Ingångsläge nivå": "red"}])
    assert function("title", "subtitle", "lifetime", "score").empty
    assert len(calls) == 1


def test_alternative_cards_show_final_score_and_observational_decision():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_horizon_alternatives")
    shown = []
    metrics = []
    display = lambda value: shown.append(str(value))
    namespace = {
        "pd": pd, "np": SimpleNamespace(isfinite=math.isfinite), "_num": lambda value: float(value) if value is not None else math.nan,
        "rank_horizon_alternatives": rank_horizon_alternatives,
        "add_full_deal_evidence": lambda frame, _h: frame,
        "render_business_context": lambda *_a, **_k: None,
        "_stock_identity": lambda row: row["Ticker"], "plain_finance_text": str,
        "st": SimpleNamespace(
            info=display, markdown=display, caption=display, write=display,
            metric=lambda label, value: metrics.append((label, value)),
            container=lambda **_k: nullcontext(), expander=lambda *_a, **_k: nullcontext(),
        ),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    namespace[node.name](pd.DataFrame([case("CAP.ST", 92, Investmentbolag=True,
                                            **{"Investmentbolag rankningstak": 60, "Direktavkastning": 2.6/140, "Direktavkastning källa": "Årlig utdelning / aktuell kurs", "Decision Brief tes": "Verifierade nyckeltal"})]), "year")
    assert metrics == [("BORSIFY SLUTBETYG", "60/100")]
    assert any("BEVAKA · inget köpbeslut" in text for text in shown)
    assert "Vad stoppar köp just nu?" in " ".join(shown)
    assert "92/100" not in " ".join(shown)
    assert "Direktavkastning: 1.86%" in " ".join(shown)
    assert "Verifierade nyckeltal" in " ".join(shown)



def test_horizon_fit_beats_shared_score_and_does_not_force_artificial_diversity():
    source = pd.DataFrame([
        case("MOMENTUM", 65, **{"1 mån": .15, "3 mån": .30, "6 mån": .45,
                                  "Kvalitet": 50, "Risk": 50, "ROE": .05, "Vinstmarginal": .02}),
        case("COMPOUNDER", 80, **{"1 mån": -.05, "3 mån": -.10, "6 mån": -.15,
                                    "Kvalitet": 95, "Risk": 90, "ROE": .25, "Vinstmarginal": .22}),
    ])
    short = rank_horizon_alternatives(source, "medium")
    lifetime = rank_horizon_alternatives(source, "lifetime")
    assert short.iloc[0]["Ticker"] == "MOMENTUM"
    assert lifetime.iloc[0]["Ticker"] == "COMPOUNDER"
    assert short.iloc[0]["Borsify slutbetyg"] == 65
    assert set(short["Ticker"]) == set(lifetime["Ticker"])
