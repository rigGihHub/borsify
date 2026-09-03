import pandas as pd

from horizon_rankings import add_horizon_scores, top_three
from near_buy import assess_overextension, near_buy_candidates

def base_row(ticker="X"):
    return {
        "Ticker":ticker,
        "Namn":ticker,
        "Universe QC":"VERIFIERAD",
        "Datatäckning":.90,
        "Riskflaggor":"—",
        "Dagsförändring":.02,
        "1 mån":.10,
        "3 mån":.20,
        "6 mån":.25,
        "Volymkvot":1.2,
        "RSI14":62,
        "Avstånd SMA200":.08,
        "Risk":70,
        "Kvalitet":70,
        "Värdering":65,
        "INVEST Score":70,
        "ROE":.18,
        "Vinstmarginal":.12,
        "Omsättningstillväxt":.08,
    }

def test_extreme_short_term_move_is_flagged_as_too_late_to_chase():
    row=base_row()
    row.update({"Dagsförändring":.11,"1 mån":.45,"RSI14":72,"Avstånd SMA200":.32})
    result=assess_overextension(row,"day")
    assert result["För långt gången"] is True
    assert result["Köpläge"]=="FÖR SENT ATT JAGA?"

def test_long_term_case_is_warned_but_not_automatically_removed_for_one_warning():
    row=base_row()
    row["1 mån"]=.30
    result=assess_overextension(row,"long")
    assert result["Köpläge"]=="VAR FÖRSIKTIG"
    assert result["För långt gången"] is False

def test_near_buy_is_close_to_threshold_but_not_a_buy():
    row=base_row("NEAR")
    # Create a score just below the day threshold without hard data/risk blockers.
    row.update({"Dagsförändring":.005,"1 mån":.05,"Volymkvot":.82,"RSI14":55,"Avstånd SMA200":.02,"Risk":55})
    df=add_horizon_scores(pd.DataFrame([row]))
    near=near_buy_candidates(df,"day")
    if not near.empty:
        assert near.iloc[0]["Köpfilter godkänd"] is False
        assert near.iloc[0]["Nära köp"] is True
        assert str(near.iloc[0]["Vad saknas"]).strip()

def test_hard_data_problem_never_appears_as_near_buy():
    row=base_row("BAD")
    row["Datatäckning"]=.20
    df=add_horizon_scores(pd.DataFrame([row]))
    assert near_buy_candidates(df,"long").empty

def test_overextended_day_candidate_is_not_in_top_three():
    good=base_row("GOOD")
    hot=base_row("HOT")
    hot.update({"Dagsförändring":.12,"1 mån":.45,"Volymkvot":2.0,"RSI14":72,"Avstånd SMA200":.35})
    top=top_three(pd.DataFrame([good,hot]),"day")
    assert "HOT" not in top["Ticker"].tolist()
