import pandas as pd
from decision_axes import assess_company_quality, add_company_quality


def test_strong_company_is_separate_from_entry_timing():
    r=assess_company_quality(pd.Series({"Kvalitet":84,"Risk":72}))
    assert r["Bolagsbedömning"] == "🟢 Mycket bra bolag"


def test_weak_company_label_does_not_depend_on_price_momentum():
    r=assess_company_quality(pd.Series({"Kvalitet":42,"Risk":35,"1 mån":-.20}))
    assert r["Bolagsbedömning nivå"] == "red"


def test_add_company_quality_adds_plain_language_axis():
    out=add_company_quality(pd.DataFrame([{"Kvalitet":72,"Risk":65}]))
    assert "Bolagsbedömning" in out.columns
    assert out.iloc[0]["Bolagsbedömning nivå"] == "green"


def test_app_exposes_company_and_entry_axes_and_release():
    app=open('app.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.37.0"' in app
    assert '**Bra bolag?**' in app
    assert '**Bra köpläge?**' in app
    assert 'table["Köpläge"] = table.get("Ingångsläge"' in app
