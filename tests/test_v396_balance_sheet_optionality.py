import pandas as pd
import numpy as np

from balance_sheet_optionality import assess_balance_sheet_optionality, add_balance_sheet_optionality
from capital_allocation_insider_radar import build_capital_allocation_metrics


def _balance():
    return pd.DataFrame(
        {
            pd.Timestamp("2026-06-30"): [100.0, 160.0],
            pd.Timestamp("2025-12-31"): [120.0, 130.0],
        },
        index=["Total Debt", "Cash And Cash Equivalents"],
    )


def test_capital_allocation_exposes_latest_net_debt():
    out=build_capital_allocation_metrics(pd.DataFrame(), _balance(), {})
    assert out["Kapitalallokering nettoskuld"] == -60.0


def test_net_cash_and_fcf_can_form_strong_optionality():
    r=assess_balance_sheet_optionality({
        "Kapitalallokering nettoskuld":-500.0,
        "Kapitalallokering skuldtrend":-.20,
        "Skuld/eget kapital":20,
        "FCF-yield":.06,
        "Kapitalallokering återköpsyield":.015,
        "Kvalitet":82,
        "Risk":74,
        "INVEST Score":78,
        "Datatäckning":.82,
    },"long")
    assert r["Balance-sheet optionality nivå"] == 3
    assert r["Balance-sheet optionality nettokassa verifierad"] is True


def test_missing_cash_is_not_called_net_cash():
    r=assess_balance_sheet_optionality({
        "Skuld/eget kapital":25,
        "FCF-yield":.06,
        "Kvalitet":80,
        "Risk":70,
        "INVEST Score":75,
    },"long")
    assert r["Balance-sheet optionality nettokassa verifierad"] is False
    assert r["Balance-sheet optionality nivå"] <= 1
    assert "nettosed/skuld kan inte verifieras" in r["Balance-sheet optionality förklaring"]


def test_bad_balance_sheet_blocks_optionality():
    r=assess_balance_sheet_optionality({
        "Kapitalallokering nettoskuld":1000,
        "Kapitalallokering skuldtrend":.40,
        "Skuld/eget kapital":240,
        "FCF-yield":-.02,
        "Kvalitet":80,
        "Risk":65,
    },"long")
    assert r["Balance-sheet optionality nivå"] == -1


def test_short_horizon_gets_no_optionality_boost():
    r=assess_balance_sheet_optionality({
        "Kapitalallokering nettoskuld":-500,
        "Skuld/eget kapital":10,
        "FCF-yield":.08,
        "Kvalitet":85,
        "Risk":80,
    },"medium")
    assert r["Balance-sheet optionality nivå"] == 0


def test_dataframe_adds_fields():
    out=add_balance_sheet_optionality(pd.DataFrame([{
        "Kapitalallokering nettoskuld":-10,
        "Skuld/eget kapital":10,
        "FCF-yield":.05,
        "Kvalitet":80,
        "Risk":70,
    }]),"long")
    assert "Balance-sheet optionality" in out.columns
    assert "Balance-sheet optionality rangvärde" in out.columns


def test_release_wiring():
    app=open("app.py",encoding="utf-8").read()
    rank=open("horizon_rankings.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert "Balance-sheet optionality" in app
    assert "add_balance_sheet_optionality(ranked, horizon)" in app
    assert "add_balance_sheet_optionality(out,horizon)" in rank.replace(" ", "")
    assert '"Deal Conviction Score"' in rank
    assert '"Kapitalallokering nettoskuld"' in ledger
