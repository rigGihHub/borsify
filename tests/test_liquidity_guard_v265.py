import numpy as np
import pandas as pd

from liquidity_guard import (
    assess_liquidity,
    add_liquidity_guard,
    filter_execution_ready,
    DAY_HARD_MIN_TURNOVER_MSEK,
    MEDIUM_HARD_MIN_TURNOVER_MSEK,
)

def test_day_rejects_missing_turnover():
    result=assess_liquidity({"Omsättning MSEK/dag":np.nan},"day")
    assert result["Likviditet godkänd"] is False
    assert result["Likviditetskontroll"]=="FÖR LITE DATA"

def test_day_rejects_extremely_low_turnover():
    result=assess_liquidity({"Omsättning MSEK/dag":DAY_HARD_MIN_TURNOVER_MSEK-.1},"day")
    assert result["Likviditet godkänd"] is False
    assert result["Likviditetskontroll"]=="FÖR LÅG HANDEL"

def test_medium_rejects_extremely_low_turnover():
    result=assess_liquidity({"Omsättning MSEK/dag":MEDIUM_HARD_MIN_TURNOVER_MSEK-.1},"medium")
    assert result["Likviditet godkänd"] is False

def test_thinner_but_acceptable_trade_is_warning_not_block():
    result=assess_liquidity({"Omsättning MSEK/dag":5.0,"Volymkvot":1.2},"day")
    assert result["Likviditet godkänd"] is True
    assert result["Likviditetskontroll"]=="TUNNARE HANDEL"

def test_long_horizon_is_not_hard_filtered_by_short_term_liquidity():
    result=assess_liquidity({"Omsättning MSEK/dag":.2},"long")
    assert result["Likviditet godkänd"] is True
    assert result["Likviditetskontroll"]=="INTE HÅRT FILTER"

def test_filter_only_removes_short_horizon_failures():
    df=pd.DataFrame([
        {"Ticker":"A","Omsättning MSEK/dag":20.0},
        {"Ticker":"B","Omsättning MSEK/dag":.5},
    ])
    day=filter_execution_ready(add_liquidity_guard(df,"day"),"day")
    assert day["Ticker"].tolist()==["A"]
    long=filter_execution_ready(add_liquidity_guard(df,"long"),"long")
    assert set(long["Ticker"])=={"A","B"}

def test_does_not_claim_live_spread():
    result=assess_liquidity({"Omsättning MSEK/dag":20.0},"day")
    assert "kan inte mäta aktuell spread" in result["Likviditet begränsning"]
    assert "Dagsdata" in result["Datafrekvens"]
