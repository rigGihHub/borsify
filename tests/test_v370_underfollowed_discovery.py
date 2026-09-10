from pathlib import Path

import numpy as np
import pandas as pd

from underfollowed_discovery import add_underfollowed_discovery, select_underfollowed_candidates, underfollowed_assessment
from discovery_engine import build_discovery_pool


def _row(**overrides):
    base = {
        "Ticker": "TEST.ST", "Namn": "Test", "Land": "Sverige",
        "Analytiker antal": 2, "Fundamental förändring antal": 2,
        "Fundamental förändring detalj": "Försäljning accelererar; Marginal förbättras",
        "Kvalitet": 70, "Risk": 65, "Borsify Score": 60,
        "Mellan Score": 60, "Års Score": 60, "Livstid Score": 60,
        "Omsättningstillväxt": .12, "Vinsttillväxt": .18, "Vinstmarginal": .11,
        "ROE": .16, "FCF-yield": .05, "Skuld/eget kapital": 50, "Forward P/E": 20,
    }
    base.update(overrides)
    return base


def test_low_coverage_never_qualifies_without_verified_fundamental_change():
    a = underfollowed_assessment(_row(**{"Fundamental förändring antal": 0}))
    assert a["Underfollowed kandidat"] is False
    assert "Få analytiker räcker inte" in a["Underfollowed förklaring"]


def test_missing_analyst_coverage_is_not_treated_as_underfollowed():
    a = underfollowed_assessment(_row(**{"Analytiker antal": np.nan}))
    assert a["Underfollowed kandidat"] is False
    assert a["Underfollowed status"] == "Analytikertäckning saknas"


def test_nordic_improver_with_observed_low_coverage_qualifies():
    a = underfollowed_assessment(_row())
    assert a["Underfollowed kandidat"] is True
    assert a["Underfollowed status"] == "Underfollowed fundamental förbättring"


def test_high_coverage_does_not_qualify_even_when_fundamentals_improve():
    a = underfollowed_assessment(_row(**{"Analytiker antal": 8}))
    assert a["Underfollowed kandidat"] is False
    assert a["Underfollowed status"] == "Tillräckligt bevakad"


def test_selection_does_not_rank_by_fewer_analysts():
    df = pd.DataFrame([
        _row(Ticker="A.ST", **{"Analytiker antal": 1, "Fundamental förändring antal": 1, "Kvalitet": 65}),
        _row(Ticker="B.ST", **{"Analytiker antal": 3, "Fundamental förändring antal": 2, "Kvalitet": 75}),
    ])
    chosen = select_underfollowed_candidates(df, quota=1)
    assert chosen[0][0] == 1
    assert chosen[0][1] == "Underfollowed förbättring"


def test_discovery_pool_exposes_underfollowed_reason():
    df = pd.DataFrame([_row(Ticker="UF.ST")])
    pool = build_discovery_pool(df, max_candidates=1)
    assert "Underfollowed kandidat" in pool.columns
    assert bool(pool.iloc[0]["Underfollowed kandidat"])
    assert "Underfollowed förbättring" in pool.iloc[0]["Upptäcktslinser"]


def test_release_version_and_ui_are_wired():
    app = Path("app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.73.0"' in app
    assert "Underfollowed – förbättras innan analytikerna hunnit bli många" in app
    assert "bq_underfollowed_discovery" in app
