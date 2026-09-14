import pandas as pd
import numpy as np

from entry_timing import assess_entry_timing


def _history(start=100.0, end=126.0, n=80):
    close=np.linspace(start,end,n)
    return pd.DataFrame({
        "High": close+1.5,
        "Low": close-1.5,
        "Close": close,
    })


def test_red_case_gets_data_derived_lower_entry_zone():
    row={
        "Pris":150.0,
        "1 mån":.34,
        "3 mån":.58,
        "Avstånd SMA200":.27,
        "RSI14":81,
        "_history":_history(),
    }
    r=assess_entry_timing(row,"medium")
    assert r["Ingångsläge nivå"] == "red"
    assert r["Bättre ingång"] != "—"
    assert r["Bättre ingång hög"] < row["Pris"]
    assert r["Bättre ingång låg"] < r["Bättre ingång hög"]
    assert r["Bättre ingång ankare"] != "—"
    assert "inte en prognos" in r["Bättre ingång skäl"]


def test_green_case_does_not_invent_waiting_price():
    row={
        "Pris":100.0,
        "1 mån":.05,
        "3 mån":.10,
        "Avstånd SMA200":.05,
        "RSI14":58,
        "_history":_history(90,100),
    }
    r=assess_entry_timing(row,"medium")
    assert r["Ingångsläge nivå"] == "green"
    assert r["Bättre ingång"] == "—"


def test_missing_price_structure_returns_no_fake_zone():
    row={"Pris":150.0,"1 mån":.34,"3 mån":.58,"RSI14":81}
    r=assess_entry_timing(row,"medium")
    assert r["Ingångsläge nivå"] == "red"
    assert r["Bättre ingång"] == "—"


def test_app_exposes_better_entry_zone_and_release():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.36.0"' in app
    assert "**Bättre ingångszon:**" in app
    assert '"Bättre ingång"' in app
    assert "inte en prognos eller garanterad köpnivå" in app
