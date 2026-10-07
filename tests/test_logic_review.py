import math
import pandas as pd
import pytest
from deep_case_engine import _cagr
from up_and_coming import assess_up_and_coming, select_up_and_coming
from test_v438_up_and_coming import _case


def test_upcoming_cap_is_500_million_not_50_billion():
    frame = pd.DataFrame([_case(Ticker="SMALL", **{"Börsvärde BSEK": .5}), _case(Ticker="LARGE", **{"Börsvärde BSEK": 20})])
    assert select_up_and_coming(frame)["Ticker"].tolist() == ["SMALL"]
    assert not assess_up_and_coming(frame.iloc[1])["Up and coming godkänd"]


def test_profit_rebound_does_not_hide_shrinking_sales_but_candidate_remains_visible():
    row = _case(**{"Omsättningstillväxt": -.5, "Vinsttillväxt": 3})
    result = select_up_and_coming(pd.DataFrame([row]))
    assert len(result) == 1
    assert not result.iloc[0]["Up and coming godkänd"]
    assert "omsättningen växer inte" in result.iloc[0]["Up and coming blockerare"]


@pytest.mark.parametrize("field", ["Analysis Confidence nivå", "Datatäckning", "Avanza-universum"])
def test_unknown_verification_does_not_generate_green_status(field):
    assert not assess_up_and_coming(_case(**{field: float('nan')}))["Up and coming godkänd"]


def test_cagr_uses_elapsed_years_instead_of_number_of_observations():
    s = pd.Series([121., 100.], index=pd.to_datetime(["2025-12-31", "2023-12-31"]))
    assert _cagr(s) == pytest.approx(.1, abs=.0002)
    assert math.isnan(_cagr(pd.Series([121., 100.])))
