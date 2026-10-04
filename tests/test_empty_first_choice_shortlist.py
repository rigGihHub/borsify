"""Exercise the production shortlist function without running Streamlit or storage.

Only candidate enrichment and daily history access are replaced. The actual
purchase filter, specialist score, first-choice gate and ranking still execute.
"""
import ast
from pathlib import Path

import pandas as pd
import pytest

from buy_now_selection import select_buy_now
from decision_tiebreaker import rank_close_daily_candidates
from first_choice_gate import add_first_choice_gate
from horizon_signals import add_action_signals
from user_score import add_user_scores
from purchase_consistency import reconcile_purchase_decisions


@pytest.fixture
def shortlist():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "build_evidence_gated_shortlist")
    namespace = {
        "pd": pd, "reconcile_purchase_decisions": reconcile_purchase_decisions,
        "build_discovery_pool": lambda frame, **_kw: frame.copy(),
        "add_user_scores": add_user_scores,
        "add_full_deal_evidence": lambda frame, _horizon: frame.copy(),
        "add_case_readiness": lambda frame, _horizon: frame.copy(),
        "select_buy_now": select_buy_now,
        "add_action_signals": add_action_signals,
        "_daily_case": lambda row, _profile: {"Dagens relevans": row["Borsify Score"]},
        "add_first_choice_gate": add_first_choice_gate,
        "rank_close_daily_candidates": rank_close_daily_candidates,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace[function.name]


def case(**overrides):
    return {
        "Ticker": "EXAMPLE.ST", "Borsify Score": 75.0, "Mellan Score": 80.0,
        "1 mån": .03, "3 mån": .06, "6 mån": .10,
        "Kvalitet": 80, "Risk": 80, "Datatäckning": .9,
        "Analysis Confidence nivå": 3, "Deal Conviction Score": 75,
        "KPI strukturerad täckning": 3, "Deep Confidence": 90,
        "Fundamental source status": "OK", "Deep source status": "OK",
        "Deal Conviction oberoende familjer": 4,
        "Rapportdatum": pd.Timestamp.now(tz="UTC").isoformat(),
        **overrides,
    }


@pytest.mark.parametrize("frame", [None, pd.DataFrame(), pd.DataFrame(columns=["Ticker", "Borsify Score"])])
def test_empty_gate_has_boolean_mask_and_preserves_columns(frame):
    gated = add_first_choice_gate(frame)
    assert gated.empty
    assert gated["Förstaval godkänd"].dtype == bool
    assert "Förstaval blockerare" in gated
    if isinstance(frame, pd.DataFrame):
        assert set(frame.columns).issubset(gated.columns)
        pd.testing.assert_index_equal(gated.index, frame.index)
    # This is the exact indexing operation that previously crashed in production.
    selected = gated[gated["Förstaval godkänd"]]
    pd.testing.assert_frame_equal(selected, gated)


@pytest.mark.parametrize("overrides", [
    {"Mellan Score": 40},  # all rejected by the real purchase filter
    {"1 mån": .35},       # all rejected by the real anti-chase filter
    {"Borsify Score": 65},  # all below the final headline-score floor
    {"Borsify Score": 92, "Investmentbolag": True, "Investmentbolag rankningstak": 60},
])
def test_valid_scan_with_no_purchase_candidate_returns_empty_shortlist(shortlist, overrides):
    frame = pd.DataFrame([case(**overrides)], index=pd.Index([17], name="candidate"))
    approved, finalists = shortlist(frame, "Balanserad")
    assert approved.empty
    assert finalists.empty
    assert "Ticker" in approved.columns
    assert finalists["Förstaval godkänd"].dtype == bool
    assert frame.loc[17, "Ticker"] == "EXAMPLE.ST"


def test_all_first_choice_blockers_leave_shortlist_empty(shortlist):
    approved, finalists = shortlist(pd.DataFrame([case(**{"Bolagsbedömning nivå": "red"})]), "Balanserad")
    assert approved.empty
    assert len(finalists) == 1
    assert not finalists["Förstaval godkänd"].any()
    assert "röd bolagsbedömning" in finalists.iloc[0]["Förstaval blockerare"]


def test_empty_shortlist_does_not_index_gate_columns(shortlist, monkeypatch):
    # Empty selections need no approval mask, including when a cached/legacy
    # gate returns an empty frame without the new gate schema.
    monkeypatch.setitem(shortlist.__globals__, "add_first_choice_gate", lambda frame: frame.copy())
    approved, finalists = shortlist(pd.DataFrame([case(**{"Borsify Score": 65})]), "Balanserad")
    assert approved.empty
    assert finalists.empty
    assert "Ticker" in approved.columns


def test_qualified_candidate_survives_and_rejected_candidates_do_not(shortlist):
    frame = pd.DataFrame([
        case(Ticker="PASS.ST"),
        case(Ticker="LOW.ST", **{"Borsify Score": 65}),
        case(Ticker="TRAP.ST", **{"Value Trap verdict": "VALUE_TRAP"}),
    ], index=[10, 20, 30])
    original = frame.copy(deep=True)
    approved, finalists = shortlist(frame, "Balanserad")
    assert approved["Ticker"].tolist() == ["PASS.ST"]
    assert approved.iloc[0]["Borsify Score"] == 75
    assert set(finalists["Ticker"]) == {"PASS.ST", "TRAP.ST"}
    pd.testing.assert_frame_equal(frame, original)
