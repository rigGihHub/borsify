import numpy as np
from underfollowed_quality import assess_underfollowed_quality


def _base(**kw):
    row={
        "Analytiker antal":2,"News Flow Unique Items 30d":2,"News Flow Status":"Blandat nyhetsflöde",
        "Datatäckning":.88,"Kvalitet":82,"Risk":72,"ROE":.19,"Vinstmarginal":.14,
        "FCF yield":.045,"INVEST Score":76,"Värdering":62,"Omsättning MSEK/dag":12,
        "Report Delta negativa":0,"Report Delta positiva":2,
    }
    row.update(kw); return row


def test_strong_underfollowed_quality_requires_real_quality_and_coverage():
    r=assess_underfollowed_quality(_base(),"long")
    assert r["Underfollowed Quality nivå"] == 3


def test_missing_analyst_coverage_is_never_underfollowed():
    r=assess_underfollowed_quality(_base(**{"Analytiker antal":np.nan}),"long")
    assert r["Underfollowed Quality nivå"] == 0
    assert "kan inte verifieras" in r["Underfollowed Quality"]


def test_low_coverage_alone_does_not_qualify():
    r=assess_underfollowed_quality(_base(**{"Kvalitet":55,"Risk":50,"ROE":.07,"Vinstmarginal":.05,"FCF yield":np.nan,"INVEST Score":55}),"long")
    assert r["Underfollowed Quality nivå"] == 0


def test_fundamental_deterioration_blocks_underfollowed_finding():
    r=assess_underfollowed_quality(_base(**{"Report Delta negativa":3,"Report Delta positiva":0}),"long")
    assert r["Underfollowed Quality nivå"] == -1


def test_signal_is_long_horizon_only():
    r=assess_underfollowed_quality(_base(),"medium")
    assert r["Underfollowed Quality nivå"] == 0


def test_app_and_ranking_wire_release():
    app=open("app.py",encoding="utf-8").read()
    rank=open("horizon_rankings.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.36.0"' in app
    assert "Underfollowed Quality" in app
    assert "add_underfollowed_quality(ranked, horizon)" in app
    assert "add_underfollowed_quality(out, horizon)" in rank
    assert '"Deal Conviction Score"' in rank
    assert '"Underfollowed Quality förklaring"' in ledger
